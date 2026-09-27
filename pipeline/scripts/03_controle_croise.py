#!/usr/bin/env python3
"""Contrôles de cohérence sur les données chargées (phase 0, tâche 3).

Deux contrôles, dont le premier ne demande aucune clé API :

  1. **Cohérence interne de l'arbre** : dans une classification hiérarchique,
     l'effectif d'un poste doit égaler la somme de ses enfants. C'est le contrôle
     qui valide réellement la correspondance variable → langue : une erreur de
     mappage casse une somme quelque part dans l'arbre.

     L'arrondissement aléatoire de Statistique Canada (multiples de 5) introduit
     un écart légitime : la somme de n enfants arrondis s'écarte du parent arrondi.
     La tolérance en tient compte ; un écart supérieur signale un vrai problème.

  2. **Contrôle croisé avec CensusMapper**, si la clé est configurée. Il compare
     la source officielle à une source tierce sur les mêmes territoires.

    python pipeline/scripts/03_controle_croise.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db
from atlas.connectors.censusmapper import CensusMapper

# Un poste arrondi au multiple de 5 s'écarte d'au plus 2 de sa vraie valeur.
# Pour un parent et n enfants, l'écart cumulé possible est de 2 * (n + 1).
TOLERANCE_PAR_POSTE = 2


def coherence_arbre(con) -> tuple[int, int]:
    """Vérifie parent = somme(enfants) pour chaque poste ayant des enfants."""
    lignes = con.execute("""
        SELECT o.territoire_id, o.axe_code, parent.code, parent.nom_fr,
               op.effectif AS effectif_parent,
               sum(o.effectif) AS somme_enfants,
               count(*) AS nb_enfants
        FROM langue parent
        JOIN langue enfant       ON enfant.parent_code = parent.code
        JOIN observation o        ON o.langue_code = enfant.code
        JOIN observation op       ON op.langue_code = parent.code
                                 AND op.territoire_id = o.territoire_id
                                 AND op.axe_code = o.axe_code
                                 AND op.annee = o.annee
        GROUP BY 1, 2, 3, 4, 5, parent.ordre_affichage
        ORDER BY parent.ordre_affichage
    """).fetchall()

    ecarts = 0
    for terr, axe, code, nom, parent, somme, n in lignes:
        if parent is None or somme is None:
            continue
        tolerance = TOLERANCE_PAR_POSTE * (n + 1)
        if abs(parent - somme) > tolerance:
            ecarts += 1
            print(f"  ÉCART  {nom[:44]:<46} parent={parent:>8,.0f} "
                  f"somme={somme:>8,.0f} ({n} enfants, tolérance ±{tolerance})")
    return len(lignes), ecarts


def main() -> int:
    config.charger_env()
    con = db.ouvrir()

    n_obs = con.execute("SELECT count(*) FROM observation").fetchone()[0]
    if not n_obs:
        print("aucune observation en base — lancer 02_charger_secteur.py d'abord")
        return 1
    print(f"{n_obs} observations en base\n")

    print("=== 1. cohérence interne de l'arbre (parent = somme des enfants) ===")
    verifies, ecarts = coherence_arbre(con)
    print(f"  {verifies} relations parent-enfant vérifiées, {ecarts} écart(s) hors tolérance")

    print("\n=== 2. contrôle croisé CensusMapper ===")
    cm = CensusMapper(config.cle_censusmapper())
    if not cm.cle:
        print("  ignoré : CENSUSMAPPER_API_KEY absente.")
        print("  Ce contrôle compare la source officielle à une source tierce ; il")
        print("  n'est pas requis pour la phase 0, dont les données viennent du")
        print("  service SDMX. Voir docs/decisions/0003-sdmx-source-primaire.md.")
        print("  Clé : https://censusmapper.ca/users/sign_up")
    else:
        print("  clé présente — comparaison à implémenter en phase 1 sur un")
        print("  échantillon de secteurs (la correspondance des postes passe par")
        print("  les libellés, non par l'arithmétique des numéros de vecteur).")

    con.close()
    print(f"\n{'contrôles conformes' if not ecarts else f'{ecarts} écart(s) à examiner'}")
    return 0 if not ecarts else 1


if __name__ == "__main__":
    raise SystemExit(main())
