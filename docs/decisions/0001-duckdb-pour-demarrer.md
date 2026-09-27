# 0001 — DuckDB plutôt que PostgreSQL/PostGIS pour démarrer

**Date :** 26 septembre 2026 · **Statut :** accepté

## Contexte

Le PRD propose PostgreSQL + PostGIS, avec « DuckDB + extension spatiale pour
démarrer léger » en alternative.

## Décision

DuckDB pour les phases 0 à 2, avec un schéma qui reste portable vers PostGIS.

## Pourquoi

- Aucun serveur à administrer : la base est un fichier, donc jetable et
  reconstructible — ce qui correspond à la façon dont le projet traite ses
  données (un produit du pipeline, pas un état à corriger).
- Le MVP peut se passer de serveur : le PRD envisage lui-même des fichiers
  statiques JSON/Parquet plutôt qu'une API.
- DuckDB lit et écrit le Parquet nativement, format de sortie naturel vers
  `tippecanoe`.

## Conséquences, dont une gênante

Le schéma n'emploie aucune extension propre à DuckDB. Les géométries sont
stockées en WKB dans une colonne `BLOB`, lisible par PostGIS comme par
l'extension spatiale de DuckDB.

**Les clés étrangères de DuckDB sont limitées :** pas de contraintes différées,
et une ligne référencée ne peut être ni supprimée ni mise à jour. Trois
conséquences concrètes :

1. Un arbre s'insère par profondeur croissante (`db.inserer_par_profondeur`).
2. Les données de référence et les classifications s'insèrent en
   `ON CONFLICT DO NOTHING` ; les modifier suppose de reconstruire la base.
3. Seules les observations, que rien ne référence, se mettent réellement à jour.

Ces limites ont été découvertes en phase 0, pas anticipées. Elles restent
acceptables — et elles ont eu un mérite : c'est la contrainte de clé étrangère
qui a révélé que l'arbre des langues était chargé deux fois, une fois par axe
partageant la classification.

## À revoir

Au passage à l'échelle du Québec (phase 2) puis du Canada (phase 4), si le
volume ou la concurrence d'écriture l'exige. Le point de bascule probable n'est
pas le volume mais le besoin de tuiles dynamiques (Martin, pg_tileserv), qui
suppose PostGIS.
