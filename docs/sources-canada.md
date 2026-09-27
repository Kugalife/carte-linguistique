# Sources canadiennes — inventaire de la phase 0

Ce qui suit a été établi en interrogeant les services, non en lisant leur
documentation. Les points marqués **⚠** contredisent ce que le PRD supposait ou
ce que la documentation laisse entendre.

## 1. Quelle source pour quoi

| Besoin | Source retenue | Clé API |
|---|---|---|
| Effectifs 2021, tous niveaux jusqu'à l'aire de diffusion | **Service SDMX du profil du recensement** | aucune |
| Classification des langues, bilingue, hiérarchisée | Service SDMX (`CL_CHARACTERISTIC`) | aucune |
| Noms et existence des territoires | Service SDMX (`CL_GEO_*`) | aucune |
| Recensements 1996 à 2016 (phase 3) | CensusMapper | **requise** |
| Géométries pour les tuiles | Fichiers des limites cartographiques | aucune |

**⚠ La clé CensusMapper n'est pas nécessaire pour la phase 0 ni pour le MVP
2021.** Le PRD plaçait `cancensus` en source principale et l'API de Statistique
Canada en simple contrôle ; c'est l'inverse qui est praticable. Le service SDMX
est officiel, sans clé, sans quota, et porte davantage de métadonnées. La clé
CensusMapper reste nécessaire pour la phase 3, qu'aucune autre source
n'automatise aussi bien.

**⚠ Le Web Data Service `CPR20xx.json` ne couvre pas 2021.**
`https://www12.statcan.gc.ca/rest/census-recensement/CPR2016.json?...` répond en
JSON pour 2016 ; l'équivalent 2021 renvoie une page HTML avec un code 200. Le
PRD mentionnait ce service « à valider » : il est validé négativement pour 2021,
et c'est le service SDMX qui le remplace.

## 2. Service SDMX — ce qu'il faut savoir pour l'utiliser

Base : `https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest`

Un dataflow par niveau géographique, tous en version **1.3** au 26 septembre 2026 :
`DF_PR`, `DF_ER`, `DF_CD`, `DF_CSD`, `DF_CMACA`, `DF_ADA`, `DF_CT`, `DF_DA`,
plus `DF_DPL`, `DF_FED`, `DF_FSA`, `DF_HR`, `DF_POPCNTR`, `DF_DCSD`.

Quatre pièges, tous rencontrés en phase 0 :

1. **⚠ La clé de données compte cinq positions, pas six.**
   `FREQ.REF_AREA.GENDER.CHARACTERISTIC.STATISTIC` — alors que la définition de
   structure déclare `TIME_PERIOD` en position 2. Placer l'année dans le chemin
   renvoie `NoRecordsFound`. L'année passe par `startPeriod` / `endPeriod`.

2. **⚠ `FREQ` vaut `A5`** (« every 5 years »), pas `A`. C'est la cause la plus
   probable d'un `NoRecordsFound` sur une clé par ailleurs correcte.

3. **⚠ La version est obligatoire et n'est pas 1.0.** `STC_CP,DF_CT,1.0` renvoie
   « Could not find Dataflow ». Le pipeline découvre la version à l'exécution.

4. **`REF_AREA` est le DGUID dont le point est remplacé par un souligné** :
   `2021S05074620001.00` → `2021S05074620001_00`.

Requête d'exemple, vérifiée :

```
GET .../data/STC_CP,DF_CT,1.3/A5.2021S05074620001_00.1.374+375+376+377+378.1
    ?startPeriod=2021&endPeriod=2021
Accept: application/vnd.sdmx.data+csv
```

### Joker ou énumération : cela dépend du nombre de territoires

**Un seul territoire : joker.** Mesuré sur un secteur de Montréal (phase 0),
énumérer les 331 postes de la langue maternelle prend **53 s**, le joker qui en
rapporte 2 631 prend **43 s**. `charger_observations` garde ce comportement.

**Plusieurs territoires : énumération.** Le joker rapporte 2 631 postes *par
territoire*. Mesuré sur 10 aires de diffusion (phase 1) : **22 s** en joker,
**7 s** en énumérant les 337 postes des deux axes. `charger_observations_lot`
énumère, et une seule requête couvre les deux axes.

**Taille des lots.** Les territoires énumérés allongent l'URL, et le service
répond **414 Request-URI Too Large** au-delà d'environ 8 000 caractères (6 869
acceptés, 8 669 refusés). Le connecteur découpe sous 7 500 caractères et au plus
200 territoires par requête (200 aires en 21 s, 300 en 62 s) : `StatCanSdmx.lots()`.

**Écriture.** `executemany` de DuckDB insère ligne par ligne : 445 s pour les
67 000 observations d'un lot. Le pipeline écrit un CSV temporaire et l'insère en
bloc : moins d'une seconde.

### Colonnes utiles de la réponse

| Colonne | Usage dans le modèle |
|---|---|
| `OBS_VALUE`, `FLAG` | `observation.effectif`, `observation.drapeau_source` |
| `ALT_GEO_CODE` | `territoire.code_local` |
| `RELEASE_DATE` | `extraction.publie_le` — **varie selon le thème** : 2022-02-09 pour la population, 2022-08-17 pour la langue |
| `TNR_SF`, `TNR_LF` | taux globaux de non-réponse, questionnaire abrégé et long |
| `DATA_QUALITY_FLAG` | indicateur composite de la source |
| `CI_LOW`, `CI_HIGH` | intervalles de confiance (vides pour les données intégrales) |

## 3. Les axes disponibles pour le Canada

| Axe | Poste racine (2021) | Postes | Données | Chargé en phase 0 |
|---|---|---|---|---|
| Langue maternelle | `379` | 331 | intégrales (100 %) | oui |
| Première langue officielle parlée | `374` | 5 | intégrales (100 %) | oui |
| Langue parlée le plus souvent à la maison | `721` | 331 | intégrales (100 %) | catalogué, non chargé |
| Connaissance des langues | `369` (officielles), `3229`-… | 324 | échantillon 25 % | non |
| Langue utilisée au travail | `2293` | 288 | échantillon 25 % | non |

**Les deux axes du PRD sont en données intégrales**, donc disponibles à l'aire de
diffusion avec le minimum de suppression — la meilleure situation possible pour
le MVP.

**⚠ Un troisième axe mérite attention.** Le PRD range « langue parlée à la
maison » parmi les axes *d'autres pays* (États-Unis, Australie,
Nouvelle-Zélande). Le Canada le publie aussi, en données intégrales, et avec
**exactement la même classification à 331 postes que la langue maternelle**
(vérifié : même forme d'arbre, mêmes libellés). C'est donc lui, et non la PLOP,
qui rendra les comparaisons internationales possibles en phase 6. Il est
catalogué dans la table `axe` et son chargement ne demande qu'une ligne de plus
dans la liste des axes du script.

**⚠ Les numéros de poste changent d'un recensement à l'autre.** « Anglais » est
la caractéristique `382` en 2021 ; elle portera un autre numéro en 2016 et en
2026. C'est la raison pour laquelle la table `langue` emploie des codes internes
dérivés du libellé (`ca.langue.anglais`), et non les codes de la source. La table
`variable_source` porte la correspondance, datée par recensement (`jeu = 'CP2021'`).

## 4. La classification des langues

`CL_CHARACTERISTIC` porte, pour chaque poste, les liens parent-enfant **et** les
libellés en français et en anglais. Conséquences directes :

- **Le regroupement par famille demandé au PRD 6.6 n'est pas à construire.**
  L'arbre de Statistique Canada est déjà familles → langues. Inutile de repartir
  de Glottolog, qui reste utile seulement pour relier les langues entre pays
  (phase 6).
- **L'interface bilingue (PRD 6.3) est alimentée par la source**, sans
  traduction à produire.

Structure de l'axe langue maternelle :

```
Total (379)
├── Réponses uniques (380)
│   ├── Langues officielles (381) → Anglais, Français
│   └── Langues non officielles (384)
│       ├── Langues autochtones (385)   → 13 familles
│       └── Langues non autochtones (476) → 19 familles
└── Réponses multiples (704) → 5 postes
```

### Le regroupement de la légende n'est pas déductible d'une profondeur

La profondeur 4 donne 32 familles, ce qui paraît idéal — mais « langues
indo-européennes » y couvre à elle seule le français, l'italien, le russe,
l'hindi et le grec. Inexploitable comme entrée de légende.

Le pipeline part donc de la profondeur 4 puis **éclate trois nœuds trop larges**
(`langues-indo-europeennes`, `langues-balto-slaves`, `langues-indo-iraniennes`),
ce qui fait apparaître exactement les familles que le PRD nomme — langues
slaves, langues indo-aryennes — et porte le total à 50 familles d'affichage.
C'est un choix éditorial, assumé comme tel dans `atlas/languages.py`, et à
revalider en phase 1 contre les effectifs réels de Montréal : 50 familles
dépassent largement les 8 couleurs de la palette.

### Ce qui n'est pas une langue

La table `langue` type chaque poste, parce que la carte doit les traiter
différemment (PRD 6.6) :

| `type_noeud` | Exemple | Effectif |
|---|---|---|
| `total` | Total - Langue maternelle | 1 |
| `regroupement` | Réponses uniques, Langues officielles | 4 |
| `famille` | Langues slaves | 57 |
| `langue` | Français, Kabyle | 215 |
| `residuel` | Créole, n.d.a. | 49 |
| `multiple` | Français et anglais | 5 |
| `aucune` | Ni français ni anglais (PLOP) | 1 |

Seuls `langue` et, selon le mode, `residuel` entrent dans le calcul de la langue
dominante. Une combinaison n'est jamais répartie silencieusement.

**⚠ La PLOP n'a pas de branche « Réponses multiples »** sous laquelle ranger ses
catégories composites. « Français et anglais » et « Ni français ni anglais » y
sont pourtant tout aussi peu des langues. Le typage se fait donc sur le libellé,
pas sur la position dans l'arbre.

## 5. Univers de population

Pour le secteur 4620001.00 : population 2 684, univers linguistique 2 630. L'écart
de 54 correspond aux résidents des établissements institutionnels, que les axes
linguistiques excluent. **Le dénominateur d'un pourcentage linguistique est
`observation.total_reference`, jamais `territoire.population`.**

## 6. Fichiers des limites cartographiques

Aucune API : un fichier zip national par niveau, téléchargé une fois et conservé
sous `data/raw/statcan_limites/` (connecteur `statcan_limites.py`).

| Niveau | Fichier | Taille |
|---|---|---|
| RMR et agglomérations | `lcma000b21a_e.zip` | 13 Mo |
| Secteurs de recensement | `lct_000b21a_e.zip` | 13 Mo |
| Aires de diffusion | `lda_000b21a_e.zip` | 197 Mo |

- **Version cartographique** (« b » dans le nom), découpée selon le littoral. La
  version numérique (« a ») couvre le fleuve et les lacs.
- **Projection EPSG:3347** (Lambert de Statistique Canada, en mètres). Le
  pipeline stocke les géométries en WGS 84 (EPSG:4326), la projection des tuiles.
- **Le fichier des aires de diffusion ne dit ni le secteur ni la RMR.** Ses
  attributs : `DAUID`, `DGUID`, `LANDAREA`, `PRUID`. L'aire est rattachée au
  secteur qui contient un point intérieur de son polygone. Les secteurs, eux, se
  filtrent par préfixe : un `CTUID` commence par le code de sa RMR.
- **`LANDAREA` est la superficie terrestre en km²**, arrondie à 4 décimales. Elle
  sert au contrôle d'emboîtement : la somme des aires redonne le secteur.
- **Le serveur ralentit parfois une connexion** à quelques dizaines de Ko/s ou la
  laisse en suspens, alors qu'une nouvelle connexion obtient plusieurs Mo/s. Le
  connecteur rouvre la connexion sous 200 Ko/s et reprend le transfert (en-tête
  `Range`, que le serveur accepte).
- DuckDB lit le shapefile dans l'archive (`/vsizip/`), sans décompression.

## 7. Ce qui reste à faire

- [x] Géométries : fichiers de limites cartographiques, voir la section 6.
- [ ] Clé CensusMapper, pour la phase 3 seulement.
- [ ] Contrôle croisé SDMX / CensusMapper (`03_controle_croise.py`), qui exige cette clé.
- [ ] Vérifier la disponibilité de la PLOP dans les recensements antérieurs (roadmap phase 3).
- [ ] Correspondance ISO 639-3 : 65 postes sur 336 sont reliés ; les familles et les résiduels n'ont pas de code, ce qui est normal.
