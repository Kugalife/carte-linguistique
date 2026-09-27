#!/usr/bin/env python3
"""Langue maternelle et PLOP de tous les territoires d'une province.

Charge la province et tous ses niveaux (régions économiques, divisions et
subdivisions de recensement, RMR et agglomérations, secteurs, aires de
diffusion), puis contrôle la cohérence : chaque territoire se recompose, et
chaque niveau redonne celui qui l'englobe (décision 0006).

    python pipeline/scripts/05_charger_donnees.py [code_province] [--tout]

Les territoires sont ceux que 04_charger_limites.py a créés. Un territoire qui
a déjà ses observations est sauté : relancer le script reprend là où il s'était
arrêté. --tout recharge tout. Québec : environ 85 requêtes, une heure.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import duckdb
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders
from atlas.connectors.statcan_limites import StatCanLimites
from atlas.connectors.statcan_sdmx import StatCanSdmx

AXES = ["CA.langue_maternelle", "CA.plop"]
NIVEAUX = loaders.NIVEAUX_PROVINCE
ESSAIS = 4

# Statistique Canada arrondit chaque case au multiple de 5, au hasard, vers le
# haut ou vers le bas : l'erreur d'une case est inférieure à 5. Un total et ses
# k postes, arrondis séparément, peuvent donc s'écarter d'au plus 5 × k (les
# écarts étant eux-mêmes multiples de 5). Au-delà, l'écart est une anomalie de
# la source, signalée ; au-delà du double, il ne peut venir que d'une erreur de
# correspondance ou de rattachement, et le contrôle échoue.
ARRONDI = 5
# Emboîtement : arrondi « au multiple de 5 et, dans certains cas, de 10 », et
# part du total au-delà de laquelle un écart trahit un territoire manquant.
ARRONDI_EMBOITEMENT = 10
SEUIL_ERREUR = 0.01

# (niveau enfant, niveau englobant, relation) : voir 04_charger_limites.py.
EMBOITEMENTS = [
    ("CA.ER", "CA.PR", "parent"),
    ("CA.CD", "CA.ER", "parent"),
    ("CA.CSD", "CA.CD", "parent"),
    ("CA.DA", "CA.CSD", "parent"),
    ("CA.CT", "CA.CMACA", "parent"),
    ("CA.DA", "CA.CT", "inclusion"),
    ("CA.CSD", "CA.CMACA", "inclusion"),
]


def rmr_interprovinciales() -> list[str]:
    """RMR dont le fichier de limites compte plusieurs parties provinciales."""
    con = duckdb.connect()
    db.charger_spatial(con)
    couche = StatCanLimites().fichier("CA.CMACA").couche
    return [r[0] for r in con.execute(f"""
        SELECT any_value(DGUID) FROM ST_Read('{couche}')
        GROUP BY CMAUID HAVING count(DISTINCT PRUID) > 1""").fetchall()]


def territoires(con, province: str, niveau: str) -> list[str]:
    """Territoires d'un niveau dans la province : tous descendent d'elle par parent_id."""
    return [r[0] for r in con.execute("""
        WITH RECURSIVE d(id) AS (
            SELECT ? UNION ALL
            SELECT t.id FROM territoire t JOIN d ON t.parent_id = d.id)
        SELECT t.id FROM territoire t JOIN d USING (id)
        WHERE t.niveau_code = ? ORDER BY t.id""", [province, niveau]).fetchall()]


def a_charger(con, ids: list[str]) -> list[str]:
    """Territoires auxquels il manque au moins un axe."""
    complets = {r[0] for r in con.execute("""
        SELECT territoire_id FROM observation
        WHERE territoire_id IN (SELECT unnest(?)) AND axe_code IN (SELECT unnest(?))
        GROUP BY territoire_id HAVING count(DISTINCT axe_code) = ?""",
        [ids, AXES, len(AXES)]).fetchall()}
    return [i for i in ids if i not in complets]


def charger(con, sdmx: StatCanSdmx, province: str, tout: bool) -> None:
    codes = sorted({c for axe in AXES for c in loaders._correspondance(con, axe, 2021)}
                   | {loaders.CARACTERISTIQUE_POPULATION}, key=int)
    for niveau in NIVEAUX:
        ids = territoires(con, province, niveau)
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


def controler(con, province: str) -> bool:
    ok = True
    print("\n--- territoires sans observation ---")
    for niveau in NIVEAUX:
        manquants = len(a_charger(con, territoires(con, province, niveau)))
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
            SELECT territoire_id, total, somme, k FROM t""", [axe, tous(con, province)]).fetchall()
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

    # Emboîtement : la somme des enfants redonne l'englobant, à l'arrondi près.
    # Statistique Canada arrondit chaque effectif au hasard « au multiple de 5 et,
    # dans certains cas, de 10 » : n enfants et l'englobant, arrondis séparément,
    # s'écartent d'au plus 10 × (n + 1). Au-delà, l'écart est une anomalie de la
    # source, signalée (observé : division 2423, −55 sur 580 750). Il n'est une
    # erreur que s'il dépasse aussi 1 % du total : c'est l'ordre de grandeur d'un
    # territoire manquant ou mal rattaché. Les RMR à cheval sur deux provinces
    # sont exclues : leur total couvre la RMR entière, leurs enfants chargés
    # seulement la province.
    print("\n--- emboîtement des totaux (somme des enfants − englobant) ---")
    interprovinciales = rmr_interprovinciales()
    ids = tous(con, province)
    for enfant, englobant, relation in EMBOITEMENTS:
        lien = ("SELECT id AS e_id, parent_id AS p_id FROM territoire WHERE niveau_code = ?"
                if relation == "parent" else
                "SELECT i.territoire_id AS e_id, i.englobant_id AS p_id FROM territoire_inclusion i "
                "JOIN territoire e ON e.id = i.territoire_id WHERE e.niveau_code = ?")
        for axe in AXES:
            lignes = con.execute(f"""
                WITH tot AS (
                    SELECT territoire_id, total_reference AS total FROM observation
                    WHERE axe_code = ? AND langue_code = (
                        SELECT langue_code FROM variable_source
                        WHERE axe_code = ? AND est_total LIMIT 1)),
                lien AS ({lien})
                SELECT l.p_id, pt.total, sum(et.total), count(*),
                       count(*) FILTER (WHERE et.total IS NULL)
                FROM lien l
                JOIN territoire p ON p.id = l.p_id AND p.niveau_code = ?
                LEFT JOIN tot et ON et.territoire_id = l.e_id
                LEFT JOIN tot pt ON pt.territoire_id = l.p_id
                WHERE l.e_id IN (SELECT unnest(?)) AND l.p_id NOT IN (SELECT unnest(?))
                GROUP BY l.p_id, pt.total""",
                [axe, axe, enfant, englobant, ids, interprovinciales or [""]]).fetchall()
            diffs = [s - t for _, t, s, _, _ in lignes if t is not None and s is not None]
            if not diffs:
                continue
            hors_marge = [(p, s - t) for p, t, s, n, sup in lignes
                          if t is not None and s is not None and not sup
                          and abs(s - t) > ARRONDI_EMBOITEMENT * (n + 1)]
            erreurs = [(p, e) for p, e in hors_marge
                       if abs(e) > SEUIL_ERREUR * dict((r[0], r[1]) for r in lignes)[p]]
            ok &= not erreurs
            rel = max((abs(s - t) / t for _, t, s, _, _ in lignes if t and s is not None), default=0)
            print(f"  {axe:<22} {enfant.split('.')[1]:>5} → {englobant.split('.')[1]:<6} "
                  f"{len(lignes):>5} englobants : écart médian {statistics.median(diffs):+.0f}, "
                  f"max {max(diffs, key=abs):+.0f} ({rel:.1%}) ; "
                  f"anomalies de la source : {len(hors_marge) - len(erreurs)}, erreurs : {len(erreurs)}")
            for p, e in hors_marge[:3]:
                print(f"      {p}  {e:+.0f}")
    if interprovinciales:
        print(f"  (RMR interprovinciales exclues : {', '.join(interprovinciales)})")

    print("\n--- fiabilité des aires de diffusion ---")
    seuil = json.loads((config.RACINE / "config" / "carte.json").read_text(
        encoding="utf-8"))["seuil_faible_population"]["valeur"]
    das = territoires(con, province, "CA.DA")
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


def tous(con, province: str) -> list[str]:
    return [i for n in NIVEAUX for i in territoires(con, province, n)]


def main(*args: str) -> int:
    tout = "--tout" in args
    positionnels = [a for a in args if not a.startswith("--")]
    code_pr = positionnels[0] if positionnels else "24"

    config.charger_env()
    con = db.ouvrir()
    province = loaders.dguid("CA.PR", code_pr)
    if not territoires(con, province, "CA.DA"):
        print(f"aucune aire de diffusion pour la province {code_pr} : "
              "lancer 04_charger_limites.py d'abord")
        return 1

    sdmx = StatCanSdmx()
    if not con.execute("SELECT count(*) FROM variable_source").fetchone()[0]:
        loaders.charger_classifications(con, sdmx)

    debut = time.monotonic()
    charger(con, sdmx, province, tout)
    print(f"chargement : {time.monotonic() - debut:.0f} s")

    ok = controler(con, province)
    con.close()
    print(f"\n{'données chargées et cohérentes' if ok else 'ÉCHEC des vérifications'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
