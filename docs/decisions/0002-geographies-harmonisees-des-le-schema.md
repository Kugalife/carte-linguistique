# 0002 — Les géographies harmonisées existent dès le schéma initial

**Date :** 26 septembre 2026 · **Statut :** accepté

## Contexte

La roadmap qualifie l'harmonisation des géographies (phase 3) de « partie
techniquement la plus risquée ». Elle est prévue six à huit semaines de travail,
trois phases après le socle.

Or les limites changent à chaque recensement, et le PRD signale que comparer
sans harmoniser produit des comparaisons fausses.

## Décision

La table `territoire_lien` et la colonne `territoire.annee_limites` font partie
du schéma de la phase 0, avant tout besoin d'affichage temporel.

## Pourquoi

Si l'identité d'un territoire ne porte pas l'année de ses limites, cette année
devient implicite, et l'on ne s'en aperçoit qu'en chargeant un deuxième
recensement — c'est-à-dire en phase 3, quand la base contient déjà tout le
Québec. Rattraper cela demanderait alors de réécrire les clés primaires de toutes
les observations.

`territoire_lien` porte une correspondance pondérée entre un territoire source et
un territoire cible, avec la méthode employée (`identite`, `tongfen`, `clctd`,
`aire`, `population`). La phase 3 remplira cette table ; elle n'aura pas à la
créer, donc pas à migrer les données déjà chargées.

Le coût aujourd'hui est de deux objets inutilisés. Le coût de l'omission serait
une migration au moment le plus risqué du projet.

## Conséquences

- `territoire.annee_limites` est `NOT NULL` : l'année des limites n'est jamais
  déduite de l'année de l'observation. Les deux sont distinctes — une observation
  de 2016 peut être portée par des limites de 2021 après harmonisation.
- `observation` est datée par `annee` (le recensement), indépendamment des
  limites du territoire qui la porte.
- La méthode d'harmonisation est stockée avec chaque lien, ce qui permet d'en
  faire coexister plusieurs et de comparer leurs effets.
