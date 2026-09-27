# Modèle de données

Fichier de référence : `pipeline/sql/001_schema.sql`. Ce document explique les
choix ; le SQL fait foi.

## Le principe

Aucune notion propre au Canada n'apparaît dans les tables. Le Canada est un jeu
de **lignes** dans `pays`, `niveau_geo`, `axe` et `classification`. Ajouter un
pays consiste à ajouter des lignes et un connecteur — jamais une colonne. C'est
l'exigence de la section 4 du PRD, celle qui rend la phase 6 possible sans
refonte.

```
pays ──< niveau_geo ──< territoire ──< observation >── langue >── classification
                             │                │                        │
                             └ territoire_lien └────────< axe >────────┘
                                                             │
         source ──< extraction ──────────────────────────────┘
                        └──< variable_source
```

## Les six tables qui portent le modèle

### `territoire`
Clé primaire = identifiant naturel de la source (DGUID au Canada). Une
réexécution du pipeline produit donc les mêmes clés : le jeu de données est
reproductible, et deux extractions sont comparables ligne à ligne.

`annee_limites` est `NOT NULL` et distincte de l'année d'observation. Voir
[décision 0002](decisions/0002-geographies-harmonisees-des-le-schema.md).

`tnr_questionnaire_abrege` / `tnr_questionnaire_long` : taux globaux de
non-réponse publiés par la source. Statistique Canada recommande la prudence
au-delà de 25 % — critère objectif d'avertissement, distinct du seuil de faible
population.

### `niveau_geo`
Hiérarchie propre à chaque pays, ordonnée par `rang` (0 = pays, croissant vers le
plus fin). `zoom_min` / `zoom_max` portent la bascule automatique de niveau selon
le zoom (PRD 6.3).

`couverture_partielle` existe parce qu'un niveau peut manquer sur une partie du
territoire : hors RMR, le Canada n'a pas de secteurs de recensement et passe de
la subdivision directement à l'aire de diffusion. La carte doit le savoir avant
d'essayer d'afficher un niveau absent (roadmap phase 2).

### `axe`
Un axe = une manière de mesurer la langue. **L'interface lit cette table et ne
présuppose aucun axe.**

`famille` range les axes par comparabilité conceptuelle
(`langue_maternelle`, `langue_maison`, `langue_principale`, `connaissance`,
`registre`, `derive`). Deux axes de même famille sont comparables entre pays ;
`derive` signale un axe propre à un pays — la PLOP canadienne — qu'aucun autre ne
reproduit. `remarques_comparabilite` porte le texte de l'avertissement.

### `classification` et `langue`
Une classification est l'arbre de postes que publie une source. Deux axes peuvent
la partager : au Canada, langue maternelle et langue parlée à la maison emploient
les mêmes 331 postes (vérifié en phase 0). La nommer une fois évite de recopier
l'arbre par axe.

`langue.code` est un code **interne**, dérivé du libellé français
(`ca.langue.anglais`), et non le code de la source. Raison : les numéros de poste
changent d'un recensement à l'autre. Un code dérivé du libellé survit aux
renumérotations, ce qui est la condition pour comparer des années.

`type_noeud` distingue ce que la carte ne doit pas confondre — `total`,
`regroupement`, `famille`, `langue`, `residuel`, `multiple`, `aucune`. Seuls
`langue` et, selon le mode, `residuel` entrent dans le calcul de la langue
dominante : une combinaison n'est jamais répartie silencieusement (PRD 6.6).

`famille_affichage` porte le regroupement de la légende. Il n'est pas déductible
d'une profondeur fixe — voir `docs/sources-canada.md`, section 4.

### `observation`
Grain : territoire × année × axe × langue × sexe.

`sexe` est dans la clé primaire parce que la source porte cette dimension. La
valeur `'T'` est le total. La conserver évite de supposer silencieusement le
total ; le PRD n'en demande pas la ventilation, mais l'omettre aurait imposé une
migration pour l'obtenir.

`effectif` est `NULL` quand la donnée est supprimée, avec `qualite = 'supprime'`.
**L'absence est une information, pas un zéro.**

`total_reference` est le dénominateur de l'axe pour ce territoire. C'est lui,
jamais `territoire.population`, qui sert à calculer un pourcentage : les axes
linguistiques excluent les résidents des établissements institutionnels (54
personnes sur 2 684 dans le secteur d'essai).

### `source`, `extraction`, `variable_source`
`observation.extraction_id` est `NOT NULL` : une observation sans provenance ne
peut pas entrer dans la base. Voir [provenance.md](provenance.md).

`variable_source` est **le seul endroit du schéma qui connaisse les identifiants
d'une source donnée**. Il porte la correspondance code de variable → (axe,
langue), datée par recensement (`jeu = 'CP2021'`). Tout le reste du modèle ignore
comment la source numérote ses variables.

## Ce que le schéma ne fait pas encore

- **Géométries** : la colonne `territoire.geometrie` existe, vide. Les fichiers de
  limites ne s'obtiennent pas par API et restent à télécharger (phase 1).
- **Indices calculés** (diversité de Greenberg ou Shannon) : ce sont des vues ou
  des colonnes dérivées, à ajouter quand les modes d'affichage existeront.
- **Projections** (phase 5) : elles produiront des observations d'un genre
  différent — avec intervalles d'incertitude et scénario. Une colonne `scenario`
  et deux bornes sur `observation`, ou une table séparée : à trancher en phase 5,
  quand le modèle sera choisi.
