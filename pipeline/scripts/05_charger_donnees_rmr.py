#!/usr/bin/env python3
"""Phase 1 — langue maternelle et PLOP de tous les territoires d'une RMR.

Charge la RMR, ses secteurs de recensement et ses aires de diffusion, puis
contrôle la cohérence : chaque territoire se recompose, et les aires redonnent
leurs secteurs, qui redonnent la RMR.

    python pipeline/scripts/05_charger_donnees_rmr.py [code_rmr] [--tout]

Les territoires sont ceux que 04_charger_limites_rmr.py a créés. Un territoire
qui a déjà ses observations est sauté : relancer le script reprend là où il
s'était arrêté. --tout recharge tout.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders
from atlas.connectors.statcan_sdmx import StatCanSdmx

AXES = ["CA.langue_maternelle", "CA.plop"]
NIVEAUX = ["CA.CMACA", "CA.CT", "CA.DA"]
ESSAIS = 4

# Statistique Canada arrondit chaque case au multiple de 5, au hasard, vers le
# haut ou vers le bas : l'erreur d'une case est inférieure à 5. Un total et ses
# k postes, arrondis séparément, peuvent donc s'écarter d'au plus 5 × k (les
# écarts étant eux-mêmes multiples de 5). Au-delà, l'écart est une anomalie de
# la source, signalée ; au-delà du double, il ne peut venir que d'une erreur de
# correspondance ou de rattachement, et le contrôle échoue.
ARRONDI = 5


def territoires(con, rmr: str, niveau: str) -> list[str]:
    return [r[0] for r in con.execute("""
        SELECT id FROM territoire
        WHERE niveau_code = ? AND (id = ? OR parent_id = ?
              OR parent_id IN (SELECT id FROM territoire WHERE parent_id = ?))
        ORDER BY id""", [niveau, rmr, rmr, rmr]).fetchall()]


def a_charger(con, ids: list[str]) -> list[str]:
    """Territoires auxquels il manque au moins un axe."""
    complets = {r[0] for r in con.execute("""
        SELECT territoire_id FROM observation
        WHERE territoire_id IN (SELECT unnest(?)) AND axe_code IN (SELECT unnest(?))
        GROUP BY territoire_id HAVING count(DISTINCT axe_code) = ?""",
        [ids, AXES, len(AXES)]).fetchall()}
    return [i for i in ids if i not in complets]


def charger(con, sdmx: StatCanSdmx, rmr: str, tout: bool) -> None:
    codes = sorted({c for axe in AXES for c in loaders._correspondance(con, axe, 2021)}
                   | {loaders.CARACTERISTIQUE_POPULATION}, key=int)
    for niveau in NIVEAUX:
        ids = territoires(con, rmr, niveau)
        restants = ids if tout else a_charger(con, ids)
        lots = sdmx.lots(restants, codes)
        print(f"{niveau:<9} {len(ids):>5} territoires, {len(restants)} à charger, "
              f"{len(lots)} requête(s)")
        for i, lot in enumerate(lots, 1):
            debut = time.monotonic()
            for essai in range(1, ESSAIS + 1):
                try:
                    # Un lot par transaction : une coupure n'en perd qu'un, et
                    # la reprise le recharge.
                    con.begin()
                    loaders.charger_observations_lot(
                        con, sdmx, niveau_code=niveau, dguids=lot, axes=AXES)
                    con.commit()
                    break
                except (requests.ConnectionError, requests.Timeout,
                        requests.HTTPError) as e:
                    con.rollback()
                    if essai == ESSAIS:
                        raise
                    attente = 15 * essai
                    print(f"    lot {i} : {type(e).__name__}, nouvel essai dans {attente} s")
                    time.sleep(attente)
            print(f"    lot {i}/{len(lots)} : {len(lot)} territoires, "
                  f"{time.monotonic() - debut:.0f} s", flush=True)


def controler(con, rmr: str) -> bool:
    ok = True
    print("\n--- territoires sans observation ---")
    for niveau in NIVEAUX:
        manquants = len(a_charger(con, territoires(con, rmr, niveau)))
        ok &= manquants == 0
        print(f"  {niveau:<9} {manquants}")

    # Chaque territoire se recompose : total de l'axe = somme des postes de
    # premier niveau, à l'arrondi près (voir ARRONDI).
    print("\n--- recomposition interne (total = somme des postes de niveau 1) ---")
    for axe in AXES:
        lignes = con.execute("""
            WITH t AS (
                SELECT o.territoire_id, any_value(o.total_reference) AS total,
                       sum(o.effectif) FILTER (WHERE l.profondeur = 1) AS somme,
                       count(*) FILTER (WHERE l.profondeur = 1) AS k
                FROM observation o JOIN langue l ON l.code = o.langue_code
                WHERE o.axe_code = ? AND o.territoire_id IN (SELECT unnest(?))
                GROUP BY o.territoire_id)
            SELECT territoire_id, total, somme, k FROM t""", [axe, tous(con, rmr)]).fetchall()
        supprimes = sum(1 for _, t, _, _ in lignes if t is None)
        mesurables = [(i, t - s, k) for i, t, s, k in lignes if t is not None and s is not None]
        exacts = sum(1 for _, e, _ in mesurables if e == 0)
        anomalies = [(i, e) for i, e, k in mesurables if ARRONDI * k < abs(e) <= 2 * ARRONDI * k]
        erreurs = [(i, e) for i, e, k in mesurables if abs(e) > 2 * ARRONDI * k]
        ok &= not erreurs
        print(f"  {axe:<22} {len(lignes)} territoires : {exacts} exacts, "
              f"{len(mesurables) - exacts - len(anomalies) - len(erreurs)} dans la marge "
              f"de l'arrondi, {len(anomalies)} anomalies de la source, {len(erreurs)} erreurs ; "
              f"{supprimes} à total supprimé")
        for i, e in (anomalies + erreurs)[:5]:
            print(f"    {i}  total − somme = {e:+.0f}")

    # Emboîtement : la somme des enfants redonne le parent, à l'arrondi près.
    # Statistique Canada arrondit chaque effectif au multiple de 5, au hasard :
    # la somme de n aires s'écarte donc du secteur, arrondi indépendamment, de
    # quelques unités par aire. Un écart systématique ou massif signalerait en
    # revanche une aire mal rattachée ou manquante.
    print("\n--- emboîtement des totaux (somme des enfants − parent) ---")
    for axe in AXES:
        for niveau_enfant, libelle in (("CA.DA", "aires → secteurs"),
                                       ("CA.CT", "secteurs → RMR")):
            lignes = con.execute("""
                WITH tot AS (
                    SELECT territoire_id, total_reference AS total FROM observation
                    WHERE axe_code = ? AND langue_code = (
                        SELECT langue_code FROM variable_source
                        WHERE axe_code = ? AND est_total LIMIT 1))
                SELECT p.id, pt.total, sum(et.total), count(*),
                       count(*) FILTER (WHERE et.total IS NULL)
                FROM territoire e
                JOIN territoire p ON p.id = e.parent_id
                LEFT JOIN tot et ON et.territoire_id = e.id
                LEFT JOIN tot pt ON pt.territoire_id = p.id
                WHERE e.niveau_code = ? AND e.id IN (SELECT unnest(?))
                GROUP BY p.id, pt.total""", [axe, axe, niveau_enfant, tous(con, rmr)]).fetchall()
            diffs = [s - t for _, t, s, _, _ in lignes if t is not None and s is not None]
            enfants_supprimes = sum(r[4] for r in lignes)
            rel = [abs(s - t) / t for _, t, s, _, _ in lignes if t and s is not None]
            # Borne de l'arrondi, pour les parents dont aucun enfant n'est
            # supprimé : n enfants et le parent, arrondis séparément.
            hors_marge = [p for p, t, s, n, sup in lignes
                          if t is not None and s is not None and not sup
                          and abs(s - t) > ARRONDI * n]
            ok &= not hors_marge
            print(f"  {axe:<22} {libelle:<17} {len(lignes)} parents : "
                  f"écart médian {statistics.median(diffs):+.0f}, "
                  f"max {max(diffs, key=abs):+.0f} ({max(rel):.1%}), "
                  f"somme {sum(diffs):+.0f} ; hors marge de l'arrondi : {len(hors_marge)} ; "
                  f"enfants à total supprimé : {enfants_supprimes}")

    print("\n--- fiabilité des aires de diffusion ---")
    seuil = json.loads((config.RACINE / "config" / "carte.json").read_text(
        encoding="utf-8"))["seuil_faible_population"]["valeur"]
    das = territoires(con, rmr, "CA.DA")
    faibles, tnr25, sans_pop = con.execute("""
        SELECT count(*) FILTER (WHERE population < ?),
               count(*) FILTER (WHERE tnr_questionnaire_abrege > 25),
               count(*) FILTER (WHERE population IS NULL)
        FROM territoire WHERE id IN (SELECT unnest(?))""", [seuil, das]).fetchone()
    print(f"  {len(das)} aires ; population < {seuil} : {faibles} ; "
          f"non-réponse > 25 % : {tnr25} ; population inconnue : {sans_pop}")

    orphelines = con.execute(
        "SELECT count(*) FROM observation WHERE extraction_id IS NULL").fetchone()[0]
    ok &= orphelines == 0
    print(f"  observations sans provenance : {orphelines}")
    return ok


def tous(con, rmr: str) -> list[str]:
    return [i for n in NIVEAUX for i in territoires(con, rmr, n)]


def main(*args: str) -> int:
    tout = "--tout" in args
    positionnels = [a for a in args if not a.startswith("--")]
    code_rmr = positionnels[0] if positionnels else "462"

    config.charger_env()
    con = db.ouvrir()
    rmr = loaders.dguid("CA.CMACA", code_rmr)
    if not territoires(con, rmr, "CA.DA"):
        print(f"aucune aire de diffusion pour la RMR {code_rmr} : "
              "lancer 04_charger_limites_rmr.py d'abord")
        return 1

    sdmx = StatCanSdmx()
    if not con.execute("SELECT count(*) FROM variable_source").fetchone()[0]:
        loaders.charger_classifications(con, sdmx)

    debut = time.monotonic()
    charger(con, sdmx, rmr, tout)
    print(f"chargement : {time.monotonic() - debut:.0f} s")

    ok = controler(con, rmr)
    con.close()
    print(f"\n{'données chargées et cohérentes' if ok else 'ÉCHEC des vérifications'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
