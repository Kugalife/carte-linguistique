"""Indicateurs affichés par la carte, calculés selon config/carte.json.

La carte n'invente rien : chaque couleur vient d'ici, et chaque règle d'ici vient
du fichier de réglages (voir docs/decisions/0004). Le site ne fait qu'afficher.

Trois indicateurs par territoire, un par carte ou variante :

  lm   langue maternelle, toutes langues
  no   langue maternelle sans le français ni l'anglais, avec deux intensités :
       part de la population (nofp) ou part parmi les allophones (noal)
  plop première langue officielle parlée

Pour chacun : la langue dominante, sa clé de couleur, son effectif, sa part et
son palier d'intensité (0 = le plus clair).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property

import duckdb

from . import config

# Dénominateur « allophones » : les réponses uniques en langue non officielle.
POSTE_ALLOPHONES = "ca.langue.langues-non-officielles"
EGALITE = "egalite"
AUTRES = "autres"


@dataclass
class Reglages:
    brut: dict

    @classmethod
    def lire(cls) -> "Reglages":
        chemin = config.RACINE / "config" / "carte.json"
        return cls(json.loads(chemin.read_text(encoding="utf-8")))

    def valeur(self, cle: str):
        return self.brut[cle]["valeur"]

    @cached_property
    def couleurs(self) -> dict[str, str]:
        """Code de langue → couleur, pour les langues qui en ont une (deux axes)."""
        couleurs = {c["langue"]: c["couleur"] for c in self.brut["palette"]["couleurs"]}
        couleurs |= {k: v for k, v in self.brut["palette"]["plop"].items()
                     if not k.startswith("_")}
        return couleurs

    @property
    def paliers(self) -> list[float]:
        return self.valeur("paliers_intensite")

    def paliers_sans_officielles(self, denominateur: str) -> list[float]:
        return self.brut["sans_francais_anglais"]["denominateurs"][denominateur]["paliers"]


def _types_candidats(reglages: Reglages) -> list[str]:
    """Types de postes qui peuvent être « la langue dominante »."""
    types = ["langue"]
    if reglages.valeur("reponses_multiples") == "categorie_candidate":
        types.append("multiple")
    return types


def dominance(
    con: duckdb.DuckDBPyConnection,
    territoires: list[str],
    *,
    axe_code: str,
    sans_officielles: bool = False,
    reglages: Reglages | None = None,
) -> dict[str, dict]:
    """Langue dominante de chaque territoire, avec son effectif et sa part.

    Renvoie {territoire_id: {langue, effectif, total, allophones}} ; langue vaut
    EGALITE si plusieurs langues partagent le premier rang (règle stricte :
    effectifs identiques), None si aucune langue candidate n'a d'effectif.
    Un territoire à total supprimé est absent du résultat.
    """
    reglages = reglages or Reglages.lire()
    if reglages.valeur("reponses_multiples") == "reparties_explicitement":
        raise NotImplementedError("répartition explicite des réponses multiples")
    if reglages.valeur("egalite") != "stricte":
        raise NotImplementedError(f"règle d'égalité {reglages.valeur('egalite')!r}")

    filtre_off = "AND coalesce(l.officielle_pays, '') <> 'CA'" if sans_officielles else ""
    lignes = con.execute(f"""
        WITH cand AS (
            SELECT o.territoire_id, o.langue_code, o.effectif, o.total_reference,
                   max(o.effectif) OVER (PARTITION BY o.territoire_id) AS maxi
            FROM observation o JOIN langue l ON l.code = o.langue_code
            WHERE o.axe_code = ? AND o.territoire_id IN (SELECT unnest(?))
              AND l.type_noeud IN (SELECT unnest(?)) {filtre_off}
              AND o.total_reference IS NOT NULL),
        allo AS (
            SELECT territoire_id, effectif AS allophones FROM observation
            WHERE axe_code = ? AND langue_code = ?)
        SELECT c.territoire_id, any_value(c.total_reference),
               CASE WHEN max(c.maxi) IS NULL OR max(c.maxi) = 0 THEN NULL
                    WHEN count(*) FILTER (WHERE c.effectif = c.maxi) > 1 THEN ?
                    ELSE any_value(c.langue_code) FILTER (WHERE c.effectif = c.maxi) END,
               max(c.maxi), any_value(a.allophones)
        FROM cand c LEFT JOIN allo a USING (territoire_id)
        GROUP BY c.territoire_id""",
        [axe_code, territoires, _types_candidats(reglages),
         axe_code, POSTE_ALLOPHONES, EGALITE]).fetchall()
    return {
        tid: {"langue": langue if maxi else None, "effectif": maxi or 0,
              "total": total, "allophones": allo}
        for tid, total, langue, maxi, allo in lignes
    }


def palier(part: float | None, paliers_pct: list[float]) -> int | None:
    """0 = sous le premier palier, len(paliers) = au-dessus du dernier."""
    if part is None:
        return None
    return sum(1 for p in paliers_pct if part * 100 >= p)


def cle_couleur(langue: str | None, reglages: Reglages) -> str | None:
    """Clé de couleur d'une langue : son code si elle a une couleur, sinon AUTRES."""
    if langue is None or langue == EGALITE:
        return langue
    return langue if langue in reglages.couleurs else AUTRES


def proprietes(
    con: duckdb.DuckDBPyConnection,
    territoires: list[str],
    reglages: Reglages | None = None,
) -> dict[str, dict]:
    """Propriétés de chaque territoire pour les tuiles de la carte.

    Clés courtes : elles sont répétées dans chaque entité des tuiles.
    """
    reglages = reglages or Reglages.lire()
    lm = dominance(con, territoires, axe_code="CA.langue_maternelle", reglages=reglages)
    no = dominance(con, territoires, axe_code="CA.langue_maternelle",
                   sans_officielles=True, reglages=reglages)
    plop = dominance(con, territoires, axe_code="CA.plop", reglages=reglages)
    seuil = reglages.valeur("seuil_faible_population")

    info = {tid: (pop,) for tid, pop in con.execute(
        "SELECT id, population FROM territoire WHERE id IN (SELECT unnest(?))",
        [territoires]).fetchall()}

    def bloc(prefixe: str, d: dict | None, paliers: list[float], denom: str = "total") -> dict:
        if d is None or d["langue"] is None:
            return {f"{prefixe}_l": None, f"{prefixe}_c": None, f"{prefixe}_e": None,
                    f"{prefixe}_p": None, f"{prefixe}_i": None}
        base = d[denom]
        part = d["effectif"] / base if base else None
        return {
            f"{prefixe}_l": d["langue"],
            f"{prefixe}_c": cle_couleur(d["langue"], reglages),
            f"{prefixe}_e": d["effectif"],
            f"{prefixe}_p": round(part, 4) if part is not None else None,
            f"{prefixe}_i": palier(part, paliers),
        }

    out = {}
    for tid in territoires:
        pop = info.get(tid, (None,))[0]
        p = {
            "id": tid,
            "pop": pop,
            # Faible population : hachures. Total supprimé : motif « non disponible ».
            "fp": pop is not None and pop < seuil,
            "nd": tid not in lm,
        }
        p |= bloc("lm", lm.get(tid), reglages.paliers)
        p |= bloc("plop", plop.get(tid), reglages.paliers)
        d = no.get(tid)
        p |= {k.replace("no_p", "nofp_p").replace("no_i", "nofp_i"): v for k, v in
              bloc("no", d, reglages.paliers_sans_officielles("population")).items()}
        alloph = bloc("noal", d, reglages.paliers_sans_officielles("allophones"), "allophones")
        p["noal_p"], p["noal_i"] = alloph["noal_p"], alloph["noal_i"]
        out[tid] = p
    return out
