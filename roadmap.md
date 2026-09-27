# Roadmap — Carte linguistique mondiale interactive

**Version :** 0.1 — septembre 2026
**Document associé :** `prd.md`

Les durées sont indicatives, pour une petite équipe (1 à 2 personnes). Chaque phase se termine par un livrable utilisable.

---

## Vue d'ensemble

| Phase | Objectif | Durée indicative | Livrable |
|---|---|---|---|
| 0 | Fondations ✅ | *terminée* | Modèle de données, pipeline squelette |
| 1 | MVP Montréal | 4–6 semaines | Carte de la RMR de Montréal, 2 axes, 2021 |
| 2 | Province de Québec | 4–6 semaines | Carte multi-échelle du Québec |
| 3 | Évolution historique | 6–8 semaines | Curseur temporel sur géographies harmonisées |
| 4 | Canada complet + recensement 2026 | 4–6 semaines | Couverture pancanadienne, données 2026 dès leur publication |
| 5 | Projections | 8–12 semaines | Module de scénarios paramétrables |
| 6 | International | Continu | Pays pilotes, puis extension progressive |

---

## Phase 0 — Fondations ✅ terminée (26 septembre 2026)

**But :** poser un socle qui supportera plusieurs pays et plusieurs axes sans refonte.

- [x] Créer le dépôt de code (pipeline, base de données, front-end)
- [x] ~~Obtenir une clé API CensusMapper et tester cancensus sur quelques secteurs de Montréal~~ → **déplacé en phase 3.** Les métadonnées CensusMapper ont été testées sans clé ; les données 2021 viennent du service SDMX, qui n'en demande pas. La clé ne devient nécessaire que pour les recensements 1996-2016.
- [x] Tester l'API de Statistique Canada pour le recensement 2021 et comparer les valeurs avec cancensus → **fait, avec deux conclusions inattendues** : le Web Data Service ne couvre pas 2021, et le service SDMX est meilleur que CensusMapper comme source primaire (voir `docs/decisions/0003-sdmx-source-primaire.md`). La comparaison avec cancensus attend la clé.
- [x] Inventorier les variables utiles pour les deux axes (langue maternelle, PLOP) et leurs identifiants → `docs/inventaire-variables.md`, `docs/sources-canada.md`. **Six** axes linguistiques recensés, dont un troisième directement utile.
- [x] Concevoir le schéma générique : territoire, niveau géographique, axe, langue, observation → `pipeline/sql/001_schema.sql`, 11 tables, expliqué dans `docs/schema.md`
- [x] Définir la table des langues (codes internes, correspondance ISO 639-3, catégories agrégées de Statistique Canada) → 336 postes chargés, 7 types de nœud, 50 familles d'affichage, 65 correspondances ISO 639-3
- [x] Mettre en place PostgreSQL/PostGIS (ou DuckDB pour démarrer) → DuckDB, schéma portable vers PostGIS (`docs/decisions/0001-duckdb-pour-demarrer.md`)
- [x] Rédiger la convention de provenance (source, tableau, date d'extraction) → `docs/provenance.md` ; `observation.extraction_id` est `NOT NULL`, donc la règle est tenue par le schéma et non par la discipline

**Critère de fin :** un script récupère les données d'un secteur de recensement, les charge dans la base selon le schéma générique, avec provenance. → **satisfait** par `pipeline/scripts/02_charger_secteur.py`, qui charge le secteur 4620001.00 (Montréal) sur les deux axes, vérifie que les totaux se recomposent, confirme qu'aucune observation n'est orpheline de provenance et retrace chaque valeur jusqu'à sa requête.

### Ajouté en cours de route

- [x] Table `territoire_lien` et colonne `annee_limites` dès le schéma initial, pour que l'harmonisation de la phase 3 n'impose pas de migration (`docs/decisions/0002-geographies-harmonisees-des-le-schema.md`)
- [x] Taux de non-réponse par territoire, que la source publie : critère objectif d'avertissement de fiabilité, distinct du seuil de faible population
- [x] Contrôle de cohérence de l'arbre (parent = somme des enfants, tolérance d'arrondissement) : 63 relations vérifiées, 0 écart — c'est ce qui valide réellement la correspondance variable → langue

### Non fait, et pourquoi

- [ ] **Géométries.** Les fichiers de limites cartographiques ne s'obtiennent pas par API ; la colonne `territoire.geometrie` existe, vide. Premier travail de la phase 1.
- [x] **Licence du dépôt.** Réglée le 27 septembre (décision 0005) : MIT pour le code, CC BY 4.0 pour les données et la documentation.

---

## Phase 1 — MVP Montréal

**But :** une carte fonctionnelle et fiable de la région métropolitaine de Montréal.

### Décisions préalables (27 septembre, décisions 0004 et 0005)
- [x] Règles de la carte par défaut, dans `config/carte.json` : axe, réponses multiples, seuil, paliers, palette
- [x] Site statique (PMTiles + JSON), Vite + TypeScript, projet ouvert
- [x] Règle d'égalité : stricte
- [x] Hébergement : GitHub Pages
- [x] Licence : MIT pour le code, CC BY 4.0 pour les données et la documentation

### Données
- [ ] Récupérer, pour la RMR 462 et le recensement 2021, la langue maternelle et la PLOP aux niveaux secteur de recensement et aire de diffusion
- [ ] Récupérer les limites cartographiques correspondantes
- [ ] Contrôler la cohérence : totaux des aires de diffusion vs secteurs vs RMR
- [ ] Marquer les territoires à données supprimées ou à faible population

### Carte
- [ ] Générer les tuiles vectorielles (tippecanoe → PMTiles)
- [ ] Afficher la carte avec MapLibre, bascule secteur / aire de diffusion selon le zoom
- [ ] Sélecteur d'axe : langue maternelle / PLOP
- [ ] Mode par défaut : langue dominante × intensité (teinte = langue, clarté = part), voir PRD 6.6
- [ ] Légende en matrice (langues × paliers < 40 / 40–60 / 60–80 / ≥ 80 %), entrées cliquables
- [ ] Palette fixe (6 teintes validées, voir décision 0004) ; confirmer les 3 couleurs provisoires sur les langues réellement dominantes des aires de diffusion
- [ ] Tester les paliers d'intensité de chaque teinte pour le daltonisme, pas seulement les couleurs de base
- [ ] Mode « part d'une langue choisie » (une teinte, échelle logarithmique en option)
- [ ] Traitement des aires à faible population (hachures) et des données supprimées
- [ ] Info-bulle et panneau de détail (composition complète, population, source)
- [ ] Légende, mention des sources, avertissement sur les petites populations
- [ ] Interface en français et en anglais

**Critère de fin :** un utilisateur peut trouver son quartier, basculer entre les deux axes et comprendre d'où viennent les chiffres.

---

## Phase 2 — Province de Québec

**But :** étendre à tout le Québec avec une navigation multi-échelle.

- [ ] Étendre la collecte à toutes les aires de diffusion du Québec
- [ ] Ajouter les niveaux région économique, division de recensement (≈ MRC) et subdivision de recensement
- [ ] Gérer les zones hors RMR où il n'existe pas de secteurs de recensement (passage direct de la subdivision à l'aire de diffusion)
- [ ] Intégrer les arrondissements et quartiers de Montréal (API CKAN de la Ville), par agrégation des aires de diffusion ou via Montréal en statistiques
- [ ] Ajouter le mode « langue non officielle dominante » (indispensable hors de Montréal)
- [ ] Ajouter l'indice de diversité linguistique
- [ ] Ajouter la carte à points dasymétrique (points en zones résidentielles seulement, fond sombre en option)
- [ ] Légende dépliable par famille de langues
- [ ] Panneau de détail en treemap
- [ ] Ajouter le mode « écart entre axes » (ex. : allophones dont la PLOP est le français)
- [ ] Traitement des réserves autochtones partiellement dénombrées
- [ ] Recherche par adresse ou par nom de lieu
- [ ] Export CSV et lien partageable

**Critère de fin :** navigation fluide du Québec entier jusqu'à l'aire de diffusion, sur ordinateur et mobile.

---

## Phase 3 — Évolution historique

**But :** montrer l'évolution sur des territoires comparables.

- [ ] **Obtenir une clé API CensusMapper** (déplacée depuis la phase 0 : elle n'est nécessaire qu'ici)
- [ ] Récupérer les recensements antérieurs disponibles via CensusMapper (2016, 2011, 2006, 2001, 1996) — disponibilité des six recensements confirmée en phase 0
- [ ] Vérifier la disponibilité de la PLOP pour chaque année (variable dérivée, disponibilité à confirmer selon les recensements)
- [ ] Harmoniser les géographies avec tongfen ou la Canadian Longitudinal Census Tract Database
- [ ] Documenter les ruptures de série (changements de questionnaire, traitement des réponses multiples, recensement volontaire de 2011 pour certaines variables)
- [ ] Curseur temporel et animation (recoloration de la carte bivariée, apparition et disparition des points)
- [ ] Mode « variation » : écart en points de pourcentage entre deux recensements
- [ ] Graphique d'évolution dans le panneau de détail

**Critère de fin :** comparer Montréal-Nord ou le Plateau entre 2001 et 2021 sur des limites identiques, avec les avertissements appropriés.

---

## Phase 4 — Canada complet et recensement 2026

**But :** couverture nationale et intégration des données les plus récentes.

- [ ] Étendre le pipeline à toutes les provinces et territoires
- [ ] Optimiser les tuiles pour l'échelle nationale
- [ ] Surveiller le calendrier de diffusion du recensement 2026 (données linguistiques attendues en 2027, à confirmer)
- [ ] Intégrer 2026 dès sa publication, y compris l'harmonisation avec 2021
- [ ] Mettre en place une exécution automatique du pipeline à chaque nouvelle diffusion

**Critère de fin :** Canada complet, recensement 2026 intégré sans modification du schéma.

---

## Phase 5 — Projections

**But :** permettre de tester des scénarios d'évolution linguistique.

- [ ] Revue des méthodes : projections linguistiques de Statistique Canada (Demosim), perspectives de l'ISQ, travaux de l'OQLF
- [ ] Choisir l'échelle de projection (région ou MRC, pas l'aire de diffusion, pour des raisons de fiabilité)
- [ ] Construire un modèle par composantes : fécondité, mortalité, immigration, migrations internes, transmission et substitution linguistiques
- [ ] Calibrer le modèle sur les recensements passés (rétroprojection 2001 → 2021)
- [ ] Définir des scénarios de référence (bas, moyen, élevé)
- [ ] Interface de paramétrage : immigration, part de francisation, taux de substitution, fécondité par groupe
- [ ] Affichage des résultats avec intervalles d'incertitude et avertissements clairs

**Critère de fin :** un utilisateur modifie le niveau d'immigration et voit l'effet projeté sur la composition linguistique du Québec à l'horizon choisi.

---

## Phase 6 — International

**But :** étendre progressivement la carte au monde, en respectant les axes propres à chaque pays.

### Évaluation des pays pilotes

Critères : échelle géographique fine, licence ouverte, API ou téléchargement automatisable, qualité de la question linguistique.

| Pays | Axe probable | Échelle fine | Remarque |
|---|---|---|---|
| États-Unis | Langue parlée à la maison (ACS) | Secteur, groupe d'îlots | Estimations d'enquête avec marges d'erreur |
| Australie | Langue parlée à la maison | SA1 | Très fine, API disponible |
| Nouvelle-Zélande | Langues parlées | SA2 | Réponses multiples |
| Suisse | Langue principale | Commune | Relevé structurel par échantillon |
| Finlande | Langue enregistrée (registre) | Grille, code postal | Données de registre, pas de recensement |
| Afrique du Sud | Langue parlée le plus souvent | Petite zone | Grande diversité linguistique |

### Tâches
- [ ] Valider les axes et les sources de chaque pays pilote
- [ ] Ajouter chaque pays comme « connecteur » du pipeline, sans modifier le schéma
- [ ] Construire la table de correspondance des langues entre sources (ISO 639-3, Glottolog)
- [ ] Afficher les avertissements de non-comparabilité entre axes de pays différents
- [ ] Couche mondiale de base (niveau pays) à partir de sources internationales pour les pays sans données fines

**Critère de fin (par pays) :** le pays est navigable à son échelle la plus fine disponible, avec ses propres axes documentés.

---

## Jalons clés

| Jalon | Contenu |
|---|---|
| J1 ✅ | Pipeline de bout en bout sur un secteur de recensement |
| J2 | Démo publique de la carte de Montréal |
| J3 | Carte du Québec complète |
| J4 | Curseur historique 2001–2021 |
| J5 | Intégration du recensement 2026 |
| J6 | Premier scénario de projection publié |
| J7 | Premier pays hors Canada |

## Dépendances et points de vigilance

- Le calendrier de diffusion du recensement 2026 conditionne la phase 4.
- L'harmonisation historique (phase 3) est techniquement la partie la plus risquée : prévoir de la marge.
- Les projections (phase 5) nécessitent des données de flux (immigration, fécondité par groupe linguistique) qui ne sont pas toutes disponibles à l'échelle fine.
- Chaque nouveau pays demande une analyse de sa définition de la langue : ne pas sous-estimer ce travail.
