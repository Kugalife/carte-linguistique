#!/usr/bin/env python3
"""Phase 1 — limites cartographiques d'une RMR.

Crée les secteurs de recensement et les aires de diffusion de la RMR, pose leurs
géométries, puis vérifie que les aires s'emboîtent dans les secteurs.

    python pipeline/scripts/04_charger_limites_rmr.py [code_rmr]

Par défaut : 462, Montréal. Le premier lancement télécharge environ 225 Mo de
fichiers de limites, conservés sous data/raw/statcan_limites/.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders
from atlas.connectors.statcan_limites import StatCanLimites
from atlas.connectors.statcan_sdmx import StatCanSdmx

# Écart toléré entre la superficie d'un secteur et la somme de ses aires. Les
# superficies publiées sont arrondies à 4 décimales (km²) : sur une centaine
# d'aires, l'arrondi seul peut produire quelques millièmes de km².
TOLERANCE_KM2 = 0.01


def main(*args: str) -> int:
    code_rmr = args[0] if args else "462"
    config.charger_env()
    con = db.ouvrir()
    print(f"base : {config.chemin_db()}")

    # La province et la RMR viennent du service SDMX, comme en phase 0 : leurs
    # noms sont ceux de la source. Déjà présentes, elles sont laissées telles quelles.
    sdmx = StatCanSdmx()
    pr = loaders.charger_territoire(
        con, sdmx, niveau_code="CA.PR", dguid_cible=loaders.dguid("CA.PR", "24"))
    rmr = loaders.charger_territoire(
        con, sdmx, niveau_code="CA.CMACA", dguid_cible=loaders.dguid("CA.CMACA", code_rmr),
        parent_id=pr)

    n = loaders.charger_limites(con, StatCanLimites(), rmr_id=rmr)
    print(f"RMR {code_rmr} : {n['CA.CT']} secteurs, {n['CA.DA']} aires de diffusion\n")

    print("--- emboîtement ---")
    ok = True

    # Chaque aire dans un secteur et un seul. Un doublon signalerait un point
    # intérieur posé sur une limite commune, ce que ST_PointOnSurface évite en
    # principe.
    doublons = con.execute(
        "SELECT count(*) - count(DISTINCT id) FROM _da").fetchone()[0]
    ok &= doublons == 0
    print(f"  aires rattachées à plusieurs secteurs : {doublons}")

    vides = con.execute("""
        SELECT count(*) FROM _ct c
        WHERE NOT EXISTS (SELECT 1 FROM _da d WHERE d.parent_id = c.id)""").fetchone()[0]
    ok &= vides == 0
    print(f"  secteurs sans aucune aire          : {vides}")

    # Superficie : la somme des aires doit redonner le secteur.
    ecarts = con.execute("""
        SELECT c.code_local, c.superficie, sum(d.superficie) AS somme
        FROM _ct c JOIN _da d ON d.parent_id = c.id
        GROUP BY c.code_local, c.superficie
        HAVING abs(c.superficie - sum(d.superficie)) > ?
        ORDER BY abs(c.superficie - sum(d.superficie)) DESC""", [TOLERANCE_KM2]).fetchall()
    ok &= not ecarts
    print(f"  secteurs dont la superficie diffère de la somme de leurs aires : {len(ecarts)}")
    for code, sup, somme in ecarts[:5]:
        print(f"    {code}  secteur {sup:.4f} km²  aires {somme:.4f} km²")

    sup_rmr, sup_ct = con.execute("""
        SELECT (SELECT superficie FROM _rmr), (SELECT sum(superficie) FROM _ct)""").fetchone()
    ok &= abs(sup_rmr - sup_ct) <= TOLERANCE_KM2 * n["CA.CT"]
    print(f"  superficie RMR {sup_rmr:,.2f} km², somme des secteurs {sup_ct:,.2f} km²")

    print("\n--- géométries stockées ---")
    db.charger_spatial(con)
    for niveau, sans, invalides, xmin, ymin, xmax, ymax in con.execute("""
        WITH t AS (
            SELECT t.niveau_code, ST_GeomFromWKB(g.geometrie) AS g
            FROM territoire t LEFT JOIN territoire_geometrie g ON g.territoire_id = t.id
            WHERE t.id = ? OR t.parent_id = ?
               OR t.parent_id IN (SELECT id FROM territoire WHERE parent_id = ?))
        SELECT niveau_code, count(*) FILTER (WHERE g IS NULL),
               count(*) FILTER (WHERE g IS NOT NULL AND NOT ST_IsValid(g)),
               min(ST_XMin(g)), min(ST_YMin(g)), max(ST_XMax(g)), max(ST_YMax(g))
        FROM t GROUP BY niveau_code ORDER BY niveau_code""", [rmr, rmr, rmr]).fetchall():
        ok &= sans == 0 and invalides == 0
        print(f"  {niveau:<9} sans géométrie {sans}  invalides {invalides}  "
              f"lon {xmin:.3f} à {xmax:.3f}  lat {ymin:.3f} à {ymax:.3f}")

    con.close()
    print(f"\n{'limites chargées et cohérentes' if ok else 'ÉCHEC des vérifications'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
