#!/usr/bin/env python3
"""Arrondissements de la ville de Montréal, par addition d'aires de diffusion.

Limites : données ouvertes de la Ville (CC BY 4.0). Chiffres : somme des aires
de diffusion dont le point intérieur tombe dans l'arrondissement. Contour :
réunion de ces aires. À lancer après 05_charger_donnees.py.

    python pipeline/scripts/07_charger_arrondissements.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders
from atlas.connectors.ville_montreal import VilleMontreal

MONTREAL = "2021A00052466023"
ARRONDI = 5


def main() -> int:
    config.charger_env()
    con = db.ouvrir()
    n = loaders.charger_arrondissements(con, VilleMontreal(), csd_id=MONTREAL)
    print(f"{n['arrondissements']} arrondissements, {n['aires']} aires de diffusion rattachées\n")

    ok = True
    print("--- rattachement des aires de la ville de Montréal ---")
    total, rattachees, multiples = con.execute("""
        SELECT (SELECT count(*) FROM territoire WHERE parent_id = ? AND niveau_code = 'CA.DA'),
               count(DISTINCT aire_id), count(*) - count(DISTINCT aire_id)
        FROM _arr_aires""", [MONTREAL]).fetchone()
    ok &= rattachees == total and multiples == 0
    print(f"  {rattachees} aires rattachées sur {total} ; dans plusieurs arrondissements : {multiples}")

    print("\n--- les arrondissements redonnent la ville (somme des aires, arrondies à 5) ---")
    for axe in ("CA.langue_maternelle", "CA.plop"):
        ville, somme, n_aires = con.execute("""
            SELECT (SELECT total_reference FROM observation WHERE territoire_id = ? AND axe_code = ?
                    LIMIT 1),
                   (SELECT sum(t) FROM (SELECT any_value(total_reference) AS t FROM observation
                    WHERE axe_code = ? AND territoire_id IN (SELECT DISTINCT arr_id FROM _arr_aires)
                    GROUP BY territoire_id)),
                   (SELECT count(*) FROM _arr_aires)""", [MONTREAL, axe, axe]).fetchone()
        # Chaque aire est arrondie séparément : la somme de n aires s'écarte du
        # total de la ville d'au plus 5 × (n + 1), bien moins en pratique.
        ecart = somme - ville
        ok &= abs(ecart) <= ARRONDI * (n_aires + 1)
        print(f"  {axe:<22} ville {ville:,.0f}, somme des arrondissements {somme:,.0f} "
              f"(écart {ecart:+,.0f}, {ecart / ville:+.2%})")

    # La limite officielle englobe le fleuve et les plans d'eau ; les aires de
    # Statistique Canada s'arrêtent au rivage. L'écart est attendu : c'est ce qui
    # justifie de dessiner la réunion des aires.
    print("\n--- contour : réunion des aires (terre ferme) contre limite officielle ---")
    aire = "ST_Area(ST_Transform({}, 'EPSG:4326', 'EPSG:3347', always_xy := true)) / 1e6"
    for nom, officielle, reunion in con.execute(f"""
        SELECT a.nom, {aire.format('a.geom')}, {aire.format('ST_GeomFromWKB(g.geometrie)')}
        FROM _arr a JOIN territoire_geometrie g ON g.territoire_id = a.id
        ORDER BY a.nom""").fetchall():
        print(f"  {nom:<42} officielle {officielle:6.2f} km², réunion des aires {reunion:6.2f} km²")

    con.close()
    print(f"\n{'arrondissements chargés et cohérents' if ok else 'ÉCHEC des vérifications'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
