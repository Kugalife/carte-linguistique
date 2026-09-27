#!/usr/bin/env python3
"""Limites cartographiques d'une province, tous niveaux.

Crée les régions économiques, divisions et subdivisions de recensement, RMR et
agglomérations, secteurs et aires de diffusion d'une province, pose leurs
géométries et vérifie leurs emboîtements (décision 0006).

    python pipeline/scripts/04_charger_limites.py [code_province]

Par défaut : 24, Québec. Le premier lancement télécharge environ 800 Mo de
fichiers de limites nationaux, conservés sous data/raw/statcan_limites/.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders
from atlas.connectors.statcan_limites import StatCanLimites

# Les superficies publiées sont arrondies à 4 décimales (km²) : la somme de n
# enfants peut s'écarter du parent de n × 0,00005 km². On tolère le double.
ARRONDI_KM2 = 0.0001

# (niveau enfant, niveau englobant, relation) : chaque emboîtement contrôlé.
EMBOITEMENTS = [
    ("CA.ER", "CA.PR", "parent"),
    ("CA.CD", "CA.ER", "parent"),
    ("CA.CSD", "CA.CD", "parent"),
    ("CA.DA", "CA.CSD", "parent"),
    ("CA.CT", "CA.CMACA", "parent"),
    ("CA.DA", "CA.CT", "inclusion"),
    ("CA.CSD", "CA.CMACA", "inclusion"),
]


def main(*args: str) -> int:
    code_pr = args[0] if args else "24"
    config.charger_env()
    con = db.ouvrir()
    print(f"base : {config.chemin_db()}")

    n = loaders.charger_limites_province(con, StatCanLimites(), code_province=code_pr)
    print("territoires : " + ", ".join(f"{k.split('.')[1]} {v}" for k, v in n.items()) + "\n")

    ok = True
    print("--- rattachements ---")
    # Chaque territoire de la chaîne administrative a un parent, et un seul
    # territoire contient son point intérieur.
    for enfant, table in (("CA.ER", "_er"), ("CA.CD", "_cd"), ("CA.CSD", "_csd"),
                          ("CA.DA", "_da"), ("CA.CT", "_ct")):
        orphelins = con.execute(f"SELECT count(*) FROM {table} WHERE parent_id IS NULL").fetchone()[0]
        ok &= orphelins == 0
        print(f"  {enfant:<9} sans parent : {orphelins}")
    for englobant, table in (("_er", "_cd"), ("_csd", "_da")):
        multiples = con.execute(f"""
            SELECT count(*) FROM (
                SELECT e.id FROM {table} e JOIN {englobant} p
                  ON ST_Within(ST_PointOnSurface(e.geom), p.geom)
                GROUP BY e.id HAVING count(*) > 1)""").fetchone()[0]
        ok &= multiples == 0
        print(f"  {table[1:].upper():<9} dans plusieurs {englobant[1:].upper()} : {multiples}")
    doublons = con.execute("""
        SELECT count(*) FROM (SELECT territoire_id FROM _inclusion WHERE niveau = 'CA.CT'
                              GROUP BY territoire_id HAVING count(*) > 1)""").fetchone()[0]
    ok &= doublons == 0
    print(f"  DA dans plusieurs secteurs : {doublons}")

    print("\n--- superficies (somme des enfants = englobant) ---")
    for enfant, englobant, relation in EMBOITEMENTS:
        jointure = ("SELECT e.id AS e_id, e.parent_id AS p_id FROM territoire e "
                    "WHERE e.niveau_code = ? AND e.parent_id IS NOT NULL"
                    if relation == "parent" else
                    "SELECT i.territoire_id AS e_id, i.englobant_id AS p_id "
                    "FROM territoire_inclusion i JOIN territoire e ON e.id = i.territoire_id "
                    "WHERE e.niveau_code = ?")
        n_parents, ecarts, pire = con.execute(f"""
            WITH lien AS ({jointure}),
            s AS (
                SELECT l.p_id, p.superficie_km2 AS sup, sum(e.superficie_km2) AS somme,
                       count(*) AS n
                FROM lien l JOIN territoire e ON e.id = l.e_id JOIN territoire p ON p.id = l.p_id
                WHERE p.niveau_code = ?
                GROUP BY l.p_id, p.superficie_km2)
            SELECT count(*), count(*) FILTER (WHERE abs(sup - somme) > greatest(0.01, ? * n)),
                   max(abs(sup - somme))
            FROM s""", [enfant, englobant, ARRONDI_KM2]).fetchone()
        ok &= ecarts == 0
        print(f"  {enfant.split('.')[1]:>5} → {englobant.split('.')[1]:<6} ({relation:<9}) "
              f"{n_parents:>5} englobants, {ecarts} écarts, écart max {pire or 0:.4f} km²")

    print("\n--- géométries ---")
    db.charger_spatial(con)
    for niveau, sans, invalides in con.execute("""
        SELECT t.niveau_code, count(*) FILTER (WHERE g.geometrie IS NULL),
               count(*) FILTER (WHERE g.geometrie IS NOT NULL
                                  AND NOT ST_IsValid(ST_GeomFromWKB(g.geometrie)))
        FROM territoire t LEFT JOIN territoire_geometrie g ON g.territoire_id = t.id
        WHERE t.id IN (SELECT id FROM _pr UNION ALL SELECT id FROM _er UNION ALL
                       SELECT id FROM _cd UNION ALL SELECT id FROM _csd UNION ALL
                       SELECT id FROM _cmaca UNION ALL SELECT id FROM _ct UNION ALL
                       SELECT id FROM _da)
        GROUP BY t.niveau_code ORDER BY t.niveau_code""").fetchall():
        ok &= sans == 0 and invalides == 0
        print(f"  {niveau:<9} sans géométrie {sans}  invalides {invalides}")

    con.close()
    print(f"\n{'limites chargées et cohérentes' if ok else 'ÉCHEC des vérifications'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
