# PRD — Carte linguistique mondiale interactive

**Nom de travail :** Atlas des langues (à définir)
**Version :** 0.1 — brouillon
**Date :** septembre 2026
**Périmètre initial :** Montréal (RMR), puis province de Québec

---

## 1. Vision

Construire une carte mondiale interactive qui montre la répartition des langues au sein des populations, à l'échelle la plus fine que permettent les données publiques de chaque pays : du pays jusqu'au quartier, voire au pâté de maisons.

La carte répond à trois questions :

1. **Où en est-on ?** L'état le plus récent recensé.
2. **D'où vient-on ?** L'évolution dans le temps, sur des territoires comparables.
3. **Où va-t-on ?** Des projections paramétrables selon des scénarios démographiques et linguistiques.

Le projet démarre par Montréal parce que les données canadiennes sont parmi les plus riches au monde (recensement exhaustif, question linguistique détaillée, diffusion jusqu'à l'aire de diffusion) et que la situation linguistique montréalaise est particulièrement dynamique.

## 2. Problème

Les données linguistiques existent mais sont dispersées, hétérogènes et difficiles à lire :

- elles sont publiées sous forme de tableaux volumineux, rarement cartographiés à l'échelle fine ;
- les limites géographiques changent à chaque recensement, ce qui rend les comparaisons dans le temps trompeuses ;
- chaque pays mesure la langue différemment (langue maternelle, langue d'usage, langue officielle, langue connue) ;
- les projections existantes sont publiées en rapports statiques, sans possibilité de tester ses propres hypothèses.

## 3. Utilisateurs cibles

| Profil | Besoin principal |
|---|---|
| Grand public curieux | Explorer son quartier, comparer avec d'autres villes |
| Journalistes | Illustrer un article avec une carte fiable et citable |
| Chercheurs (démographie, sociolinguistique, géographie) | Accéder à des données harmonisées et exportables |
| Décideurs publics, urbanistes, organismes communautaires | Adapter les services (francisation, services en langues d'origine) |
| Enseignants et élèves | Support pédagogique sur la diversité linguistique |

## 4. Concept central : les axes d'observation

Le cœur du modèle est la notion d'**axe d'observation** : une manière de mesurer la langue d'une population. Chaque pays expose un ou plusieurs axes selon ce que ses sources publient.

### Axes disponibles pour le Canada

| Axe | Définition (Statistique Canada) | Intérêt |
|---|---|---|
| **Langue maternelle** | Première langue apprise à la maison dans l'enfance et encore comprise | Origine linguistique des populations, diversité réelle |
| **Première langue officielle parlée (PLOP)** | Variable dérivée classant chaque personne selon sa langue officielle principale : français, anglais, français et anglais, ni l'un ni l'autre | Intégration linguistique, planification des services en langues officielles |

Ces deux axes se complètent : croiser les deux montre, par exemple, vers quelle langue officielle s'orientent les personnes de langue maternelle autre que le français ou l'anglais.

### Axes probables ailleurs (à valider pays par pays)

- **Langue parlée à la maison** : États-Unis (ACS), Australie, Nouvelle-Zélande, Afrique du Sud.
- **Langue principale** : Suisse.
- **Langue enregistrée dans les registres de population** : Finlande, Estonie.
- **Connaissance des langues** : nombreux recensements, souvent en réponses multiples.

**Règle de conception :** l'interface ne présuppose jamais un axe particulier. Elle affiche les axes disponibles pour le territoire consulté, et signale clairement quand deux axes ne sont pas comparables d'un pays à l'autre.

## 5. Objectifs et indicateurs de succès

| Objectif | Indicateur |
|---|---|
| Couvrir Montréal à l'aire de diffusion | 100 % des aires de diffusion de la RMR 462 affichées, 2 axes, recensement 2021 |
| Couvrir le Québec en multi-échelle | Navigation fluide de la province à l'aire de diffusion |
| Fiabilité | Chaque valeur affichée est traçable jusqu'à sa source (tableau, année, identifiant) |
| Performance | Premier affichage < 3 s ; changement d'axe ou d'année < 500 ms |
| Usage | À définir après le MVP (visites, partages, exports) |

## 6. Périmètre fonctionnel

### 6.1 Collecte des données (pipeline)

- Récupération automatisée par API lorsque possible :
  - **CensusMapper / cancensus** : données du recensement canadien et géométries, tous niveaux, recensements 1996 à 2021 ;
  - **API de Statistique Canada** (Web Data Service et service SDMX pour le recensement de 2021, à valider) : source officielle, utile pour contrôler les valeurs ;
  - **API CKAN de Données Québec et du portail de la Ville de Montréal** : limites d'arrondissements, de quartiers, de MRC.
- Téléchargement des fichiers de limites cartographiques de Statistique Canada (version cartographique, découpée selon le littoral).
- Pipeline reproductible et versionné : chaque exécution produit un jeu de données daté, avec journal de provenance.

### 6.2 Modèle de données

Modèle générique, indépendant du pays :

- **territoire** : identifiant unique (DGUID pour le Canada), nom, niveau géographique, parent, géométrie, année de référence des limites ;
- **niveau géographique** : hiérarchie propre à chaque pays (pour le Canada : pays → province → région économique → division de recensement → subdivision de recensement → secteur de recensement → aire de diffusion) ;
- **axe** : langue maternelle, PLOP, langue parlée à la maison, etc., avec sa définition et sa source ;
- **langue** : code interne relié à ISO 639-3 et à Glottolog quand c'est possible, plus les catégories agrégées propres aux sources (« langues chinoises, n.i.a. », « autres langues ») ;
- **observation** : territoire × année × axe × langue → effectif, total de référence, indicateur de qualité (arrondi, suppression).

### 6.3 Carte interactive

- Carte zoomable avec **changement automatique de niveau géographique** selon le zoom (région à grande échelle, aire de diffusion au niveau du quartier).
- **Sélecteur d'axe** (langue maternelle / PLOP au Canada).
- **Modes de représentation** (détaillés en section 6.6) :
  - **mode par défaut : langue dominante × intensité** (teinte = langue dominante, clarté = part de cette langue) ;
  - langue non officielle dominante (français et anglais exclus) ;
  - part d'une langue choisie, en dégradé d'une seule teinte, avec échelle logarithmique en option ;
  - indice de diversité linguistique (indice de Greenberg ou de Shannon) ;
  - carte à points (densité de points) pour éviter de surreprésenter les grands territoires peu peuplés ;
  - écart entre axes (ex. : part des allophones dont la PLOP est le français).
- **Info-bulle et panneau latéral** : composition linguistique complète du territoire, population, source et année.
- **Comparaison** de deux territoires côte à côte.
- **Export** : image de la carte, données du territoire en CSV, lien partageable qui conserve l'état de la vue.
- Interface bilingue français-anglais au lancement.

### 6.4 Évolution historique (phase ultérieure)

- Curseur temporel sur les recensements disponibles.
- Harmonisation des géographies entre recensements (méthode tongfen ou table de correspondance) pour comparer des territoires stables.
- Signalement explicite des ruptures de série (changements de questionnaire, réponses multiples).

### 6.5 Projections (phase ultérieure)

- Modèle par composantes : fécondité, mortalité, immigration internationale, migrations internes, transmission intergénérationnelle et substitution linguistique.
- Paramètres ajustables par l'utilisateur à partir de scénarios de référence (ISQ, Statistique Canada, OQLF).
- Affichage des résultats avec intervalles d'incertitude, à une échelle compatible avec la fiabilité du modèle (région ou MRC plutôt qu'aire de diffusion).

### 6.6 Conception visuelle et légende

**Mode par défaut : langue dominante × intensité (carte bivariée).**
À l'échelle la plus fine (aire de diffusion), chaque territoire est coloré selon deux dimensions :
- la **teinte** indique la langue dominante (la plus déclarée) ;
- la **clarté** indique la part de cette langue : clair = majorité faible ou simple pluralité, foncé = langue très majoritaire.

Ce mode s'inspire de CensusMapper pour la lecture par intensité, et reste valable pour les deux axes canadiens : en langue maternelle, il révèle les poches allophones ; en PLOP, il montre vers quelle langue officielle ces populations s'orientent. Basculer d'un axe à l'autre recolore la carte sans changer de vue.

**Légende en matrice.**
- Lignes : les langues (une teinte chacune).
- Colonnes : paliers de part de la langue dominante, par exemple < 40 %, 40–60 %, 60–80 %, ≥ 80 %.
- Le palier inférieur à 40 % est indispensable : dans les quartiers mixtes de Montréal, la langue « dominante » n'est souvent qu'une pluralité de 25 à 30 %. Sans ce palier, on laisserait croire qu'un quartier est majoritairement d'une langue alors qu'elle n'y est que la première parmi d'autres.
- Chaque entrée de la légende est **cliquable** : cliquer sur une langue fait passer la carte en mode « part d'une langue choisie ».
- La légende affiche l'effectif de chaque langue dans la zone visible.

**Palette.**
- 8 couleurs catégorielles au maximum, dans un ordre fixe : une langue garde toujours la même couleur, quel que soit le filtre ou le zoom.
- Au-delà, les langues moins fréquentes sont regroupées par famille ou région (langues slaves, langues indo-aryennes, langues autochtones, etc.), dans l'esprit de la légende de la carte des langues de New York ; la légende se déplie pour afficher les langues détaillées en nuances de la couleur de leur famille.
- Axe PLOP : 4 catégories seulement (français, anglais, français et anglais, ni l'un ni l'autre).
- Palette vérifiée pour les personnes daltoniennes.

**Mode « langue non officielle dominante ».**
Hors de Montréal, le mode par défaut produit une carte presque uniformément francophone : c'est exact, mais peu informatif. Ce mode exclut le français et l'anglais pour révéler la diversité cachée (Laval, Brossard, Gatineau, etc.) et les langues autochtones dans le Nord.

**Mode « part d'une langue choisie » (inspiré de languagemap.us).**
- Dégradé d'une seule teinte, celle de la langue sélectionnée.
- Échelle logarithmique en option, pour rendre visibles les langues rares que la carte de dominance ne montre jamais.
- Contrepartie à signaler : l'échelle logarithmique écrase les nuances pour les langues très répandues.

**Carte à points (inspirée de la carte des langues du Census Bureau américain).**
- Un point représente un nombre fixe de personnes, variable selon le zoom.
- Points placés aléatoirement à l'intérieur de chaque aire (aucune localisation individuelle).
- Placement **dasymétrique** : points uniquement dans les zones résidentielles (exclusion des parcs, zones industrielles, plans d'eau), à partir de l'occupation du sol.
- Fond sombre en option, sur lequel les couleurs ressortent mieux.
- Animation entre recensements pour le volet historique.

**Traitement des cas limites.**
- Aires à très faible population : hachurées ou atténuées, avec un avertissement lié à l'arrondissement aléatoire.
- Données supprimées : motif distinct « donnée non disponible ».
- Égalité entre deux langues : règle explicite et documentée (ex. : afficher la catégorie « mixte »).
- Réponses multiples (ex. : français et anglais) : catégories propres, jamais réparties silencieusement.

**Panneau de détail.**
Composition linguistique complète du territoire sous forme de treemap ou de barres, inspirée de la visualisation « Langue maternelle selon la géographie » de Statistique Canada.

**Références visuelles.**
- CensusMapper, indice de diversité de la langue maternelle (lecture par intensité).
- languagemap.us (une langue à la fois, échelle logarithmique).
- Languages of New York City Map (légende par familles, cliquable, exploration par quartier).
- Carte des langues du Census Bureau américain (carte à points, placement aléatoire par secteur).
- Guide de visualisation de data.europa.eu (cartes à points dasymétriques).

## 7. Hors périmètre (pour l'instant)

- Données individuelles ou microdonnées confidentielles.
- Dialectes et variétés régionales d'une même langue.
- Contributions de données par les utilisateurs.
- Application mobile native (le site sera responsive).

## 8. Exigences non fonctionnelles

- **Performance :** tuiles vectorielles préparées à l'avance (PMTiles) plutôt que chargement de géométries brutes ; le Canada compte de l'ordre de 57 000 aires de diffusion.
- **Traçabilité :** chaque chiffre renvoie à sa source, son tableau et sa date d'extraction.
- **Accessibilité :** palettes lisibles par les personnes daltoniennes, navigation au clavier, données disponibles en tableau.
- **Licences :** respect de la Licence du gouvernement ouvert de Statistique Canada et des licences des portails ouverts ; mention des sources sur la carte.
- **Reproductibilité :** pipeline sous contrôle de version, exécutable de bout en bout.

## 9. Architecture technique proposée

| Couche | Choix proposé | Alternatives |
|---|---|---|
| Collecte | Python (requests) + R (cancensus, tongfen) | Tout en R ou tout en Python |
| Stockage | PostgreSQL + PostGIS | DuckDB + extension spatiale pour démarrer léger |
| Préparation des tuiles | tippecanoe → PMTiles | Martin ou pg_tileserv (tuiles dynamiques) |
| Front-end | MapLibre GL JS | deck.gl pour les couches de points |
| API interne | FastAPI | Fichiers statiques JSON/Parquet pour un MVP sans serveur |
| Projections | Python (numpy, pandas) | R |
| Hébergement | Stockage objet + CDN pour les tuiles | À définir |

## 10. Contraintes et risques liés aux données

| Risque | Impact | Mitigation |
|---|---|---|
| Arrondissement aléatoire (multiples de 5) dans les petites aires | Pourcentages instables | Afficher les effectifs, avertir sous un seuil de population, proposer le secteur de recensement |
| Suppression de données pour confidentialité | Trous dans la carte | Représentation distincte « donnée non disponible » |
| Limites qui changent entre recensements | Comparaisons fausses | Harmonisation avant tout affichage temporel |
| Réponses multiples (ex. français et anglais) | Double comptage ou catégories ambiguës | Conserver les réponses multiples comme catégories propres |
| Erreur écologique | Mauvaise interprétation (« tous les habitants parlent… ») | Textes pédagogiques, carte à points |
| Axes non comparables entre pays | Comparaisons internationales trompeuses | Axes explicitement nommés, avertissement lors du changement de pays |
| Réserves autochtones partiellement dénombrées | Sous-estimation des langues autochtones | Signalement explicite, sources complémentaires |
| Recensement 2026 publié en 2027 | Données à intégrer en cours de projet | Pipeline conçu pour ajouter une année sans refonte |

## 11. Questions ouvertes

- Quel indicateur afficher par défaut à l'ouverture de la carte ?
- Faut-il agréger les aires de diffusion par arrondissement nous-mêmes, ou utiliser les profils de Montréal en statistiques ?
- Quels pays pilotes pour l'international (critères : échelle fine disponible, licence ouverte, axe de mesure) ?
- Modèle de publication : projet ouvert (code et données) ou produit fermé ?
- Hébergement et coûts pour la version mondiale.

## 12. Sources de référence

- Statistique Canada : Recensement de la population (profils, tableaux de données, fichiers des limites), projections linguistiques, modèle Demosim.
- CensusMapper (API) et paquets R cancensus et tongfen.
- Institut de la statistique du Québec : perspectives démographiques.
- Office québécois de la langue française : suivi de la situation linguistique.
- Ville de Montréal (Montréal en statistiques, portail de données ouvertes) et Données Québec.
- International (à évaluer) : IPUMS International, UN Demographic Statistics, Glottolog, recensements nationaux.
