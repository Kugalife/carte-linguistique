# Atlas des langues

Carte mondiale interactive de la répartition des langues, à l'échelle la plus
fine que permettent les données publiques de chaque pays.

- [`prd.md`](prd.md) — vision, périmètre, conception visuelle
- [`roadmap.md`](roadmap.md) — phases et livrables

**État : phase 0 (fondations) terminée.** Le pipeline charge un secteur de
recensement montréalais dans un schéma multi-pays, avec provenance complète et
contrôles de cohérence. Aucune carte n'existe encore — c'est la phase 1.

## Démarrer

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Critère de fin de la phase 0 : charge un secteur, vérifie, retrace
.venv/bin/python pipeline/scripts/02_charger_secteur.py --recreer
```

Aucune clé API n'est nécessaire. Compter environ 80 s la première fois (le
pipeline télécharge et met en cache 12 Mo de définitions de structure), puis une
vingtaine de secondes.

```bash
# Inventaire des axes disponibles pour le Canada
.venv/bin/python pipeline/scripts/01_inventaire_variables.py

# Contrôles de cohérence sur les données chargées
.venv/bin/python pipeline/scripts/03_controle_croise.py

# Phase 1 : secteurs et aires de diffusion de la RMR de Montréal, avec leurs
# limites. Le premier lancement télécharge 225 Mo de fichiers de limites.
.venv/bin/python pipeline/scripts/04_charger_limites_rmr.py

# Phase 1 : langue maternelle et PLOP de tous ces territoires (environ 20 min ;
# relancé, il reprend là où il s'était arrêté)
.venv/bin/python pipeline/scripts/05_charger_donnees_rmr.py

# Phase 1 : tuiles et fichiers de la carte, sous web/public/donnees/
# (exige tippecanoe : https://github.com/felt/tippecanoe)
.venv/bin/python pipeline/scripts/06_exporter_carte.py
```

Copier `.env.example` vers `.env` pour configurer une clé CensusMapper — utile
seulement pour les recensements antérieurs à 2021 (phase 3).

## Organisation

```
pipeline/
  atlas/
    config.py          chemins et réglages
    db.py              connexion DuckDB, application du schéma
    provenance.py      journal des extractions
    languages.py       construction de la table des langues
    loaders.py         traduction source → modèle générique
    indicateurs.py     ce que la carte affiche, selon config/carte.json
    connectors/
      statcan_sdmx.py  source primaire des effectifs 2021
      censusmapper.py  recensements 1996-2016, contrôle croisé
      statcan_limites.py  géométries (fichiers de limites cartographiques)
  sql/
    001_schema.sql            schéma générique multi-pays
    002_reference_canada.sql  données de référence du Canada
  scripts/             points d'entrée exécutables
docs/
  schema.md            le modèle de données et ses pourquoi
  provenance.md        la convention de traçabilité
  sources-canada.md    inventaire des sources, pièges des API
  decisions/           décisions d'architecture
data/                  produit par le pipeline, non versionné
web/                   phase 1
```

## Ce que la phase 0 a établi

Trois résultats modifient ce que prévoyait le PRD. Ils sont détaillés dans
[`docs/sources-canada.md`](docs/sources-canada.md) et dans les
[décisions](docs/decisions/).

1. **Le service SDMX de Statistique Canada remplace CensusMapper comme source
   primaire.** Il est officiel, ne demande aucune clé API, couvre tous les
   niveaux jusqu'à l'aire de diffusion et fournit davantage de métadonnées
   (libellés bilingues, hiérarchie des langues, taux de non-réponse). Le Web Data
   Service que le PRD citait en premier ne couvre pas 2021.

2. **Le regroupement des langues par famille ne doit pas être reconstruit.** La
   classification de Statistique Canada est déjà un arbre familles → langues, en
   français et en anglais. Restait un choix éditorial : aucune profondeur fixe ne
   donne une bonne légende, il faut éclater trois nœuds trop larges pour obtenir
   les familles que le PRD nomme.

3. **Le Canada publie un troisième axe utile.** « Langue parlée le plus souvent à
   la maison », en données intégrales et avec la même classification que la langue
   maternelle. C'est lui, et non la PLOP, qui rendra le Canada comparable aux
   États-Unis, à l'Australie et à la Nouvelle-Zélande en phase 6. Il est catalogué
   mais non chargé.

## Licence

Projet ouvert (décision 0005).

- Code : MIT, voir [`LICENSE`](LICENSE).
- Documentation, réglages éditoriaux, données produites et cartes : CC BY 4.0,
  voir [`LICENSE-DONNEES`](LICENSE-DONNEES).
- Données sources : Statistique Canada, sous la Licence du gouvernement ouvert —
  Canada, dont la mention est obligatoire.
