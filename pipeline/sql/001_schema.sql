-- Atlas des langues — schéma générique multi-pays / multi-axes
-- Phase 0. Voir docs/schema.md pour le raisonnement, docs/provenance.md pour la traçabilité.
--
-- Principes :
--   1. Aucune notion propre au Canada dans les tables. Le Canada est un jeu de
--      lignes dans pays / niveau_geo / axe, pas une colonne.
--   2. Toutes les clés primaires sont des identifiants naturels et stables
--      (DGUID, code interne de langue). Une réexécution du pipeline produit
--      les mêmes clés : le jeu de données est reproductible bit à bit.
--   3. Toute observation pointe vers une extraction, donc vers une source datée.
--   4. Les géographies harmonisées existent dès maintenant (territoire_lien),
--      pour que la phase 3 n'impose pas de migration.

------------------------------------------------------------------- provenance

CREATE TABLE IF NOT EXISTS source (
    code            TEXT PRIMARY KEY,       -- 'statcan_sdmx_cp', 'censusmapper', 'statcan_limites'
    nom             TEXT NOT NULL,
    organisme       TEXT NOT NULL,
    licence         TEXT NOT NULL,
    licence_url     TEXT,
    url_base        TEXT,
    remarques       TEXT
);

-- Une exécution du pipeline contre une source. Tout chiffre affiché remonte ici.
CREATE TABLE IF NOT EXISTS extraction (
    id              TEXT PRIMARY KEY,       -- '<source>:<horodatage>:<empreinte requête>'
    source_code     TEXT NOT NULL REFERENCES source(code),
    extrait_le      TIMESTAMP NOT NULL,
    requete         TEXT NOT NULL,          -- URL ou appel exact, rejouable tel quel
    reponse_sha256  TEXT,                   -- empreinte de la réponse brute
    nb_lignes       INTEGER,
    tableau_source  TEXT,                   -- n° de tableau ou produit ('98-10-0169', 'DF_CT')
    version_source  TEXT,                   -- version du dataflow / du jeu ('1.3', 'CA21')
    publie_le       DATE,                   -- date de diffusion annoncée par la source
    outil_version   TEXT,                   -- version du pipeline qui a produit l'extraction
    notes           TEXT
);

------------------------------------------------------------------- géographie

CREATE TABLE IF NOT EXISTS pays (
    code            TEXT PRIMARY KEY,       -- ISO 3166-1 alpha-2 : 'CA'
    nom_fr          TEXT NOT NULL,
    nom_en          TEXT NOT NULL
);

-- Hiérarchie propre à chaque pays. rang croissant = de plus en plus fin.
CREATE TABLE IF NOT EXISTS niveau_geo (
    code            TEXT PRIMARY KEY,       -- 'CA.DA', 'CA.CT', 'US.TRACT'
    pays_code       TEXT NOT NULL REFERENCES pays(code),
    code_local      TEXT NOT NULL,          -- 'DA', 'CT', 'CSD' — code de la source
    nom_fr          TEXT NOT NULL,
    nom_en          TEXT NOT NULL,
    rang            INTEGER NOT NULL,       -- 0 = pays, croissant vers le plus fin
    parent_code     TEXT REFERENCES niveau_geo(code),
    -- Un niveau peut manquer sur une partie du territoire : hors RMR, le Canada
    -- passe de la subdivision directement à l'aire de diffusion (roadmap phase 2).
    couverture_partielle BOOLEAN NOT NULL DEFAULT FALSE,
    zoom_min        DOUBLE,                 -- plage de zoom où ce niveau s'affiche
    zoom_max        DOUBLE
);

CREATE TABLE IF NOT EXISTS territoire (
    id              TEXT PRIMARY KEY,       -- DGUID au Canada : '2021S05074620001.00'
    pays_code       TEXT NOT NULL REFERENCES pays(code),
    niveau_code     TEXT NOT NULL REFERENCES niveau_geo(code),
    code_local      TEXT NOT NULL,          -- '4620001.00' — code court de la source
    nom             TEXT,
    nom_en          TEXT,
    parent_id       TEXT REFERENCES territoire(id),
    -- Les limites changent d'un recensement à l'autre : l'année des limites fait
    -- partie de l'identité du territoire, elle n'est pas déductible de l'année
    -- de l'observation.
    annee_limites   INTEGER NOT NULL,
    population      INTEGER,                -- population de référence, pour les seuils d'affichage
    superficie_km2  DOUBLE,
    -- Taux global de non-réponse, publié par la source pour chaque territoire.
    -- Statistique Canada recommande la prudence au-delà de 25 % : c'est le
    -- critère objectif des avertissements de fiabilité (PRD 6.6 et section 10),
    -- distinct du seuil de faible population.
    tnr_questionnaire_abrege DOUBLE,        -- données intégrales (100 %) : langue maternelle, PLOP
    tnr_questionnaire_long   DOUBLE,        -- échantillon 25 % : connaissance des langues, langue au travail
    extraction_id   TEXT REFERENCES extraction(id)
);

-- Correspondance entre territoires de millésimes différents, ou entre un
-- territoire source et une géographie harmonisée construite par le pipeline.
-- poids = part de la population du territoire source attribuée à la cible.
-- Présente dès la phase 0 pour que la phase 3 (harmonisation tongfen / CLCTD)
-- n'oblige pas à retoucher le schéma. Voir docs/decisions/0002.
CREATE TABLE IF NOT EXISTS territoire_lien (
    territoire_source   TEXT NOT NULL REFERENCES territoire(id),
    territoire_cible    TEXT NOT NULL REFERENCES territoire(id),
    poids               DOUBLE NOT NULL,
    methode             TEXT NOT NULL,      -- 'identite', 'tongfen', 'clctd', 'aire', 'population'
    extraction_id       TEXT REFERENCES extraction(id),
    PRIMARY KEY (territoire_source, territoire_cible, methode)
);

-- Limites d'un territoire, à part de la ligne du territoire : c'est une donnée
-- qu'on recharge, et DuckDB interdit de modifier une colonne à clé étrangère
-- (extraction_id) sur une ligne référencée — or un territoire l'est par ses
-- enfants et ses observations. Rien ne référence cette table-ci : elle accepte
-- un vrai upsert.
CREATE TABLE IF NOT EXISTS territoire_geometrie (
    territoire_id   TEXT PRIMARY KEY REFERENCES territoire(id),
    geometrie       BLOB NOT NULL,          -- WKB, WGS 84 (EPSG:4326)
    extraction_id   TEXT NOT NULL REFERENCES extraction(id)
);

-- Appartenances hors de la chaîne principale. parent_id suit la chaîne
-- administrative (province → région économique → division → subdivision →
-- aire), qui couvre tout le territoire ; cette table porte les autres :
-- aire ∈ secteur de recensement, subdivision ∈ RMR. Voir docs/decisions/0006.
CREATE TABLE IF NOT EXISTS territoire_inclusion (
    territoire_id   TEXT NOT NULL REFERENCES territoire(id),
    englobant_id    TEXT NOT NULL REFERENCES territoire(id),
    extraction_id   TEXT NOT NULL REFERENCES extraction(id),
    PRIMARY KEY (territoire_id, englobant_id)
);

------------------------------------------------------------------ axes et langues

-- Une classification linguistique : l'arbre de postes que publie une source.
-- Deux axes peuvent partager la même (au Canada, langue maternelle et langue
-- parlée à la maison emploient la même classification à 331 postes) ; la PLOP a
-- la sienne, à 4 postes. On la nomme donc une fois et on la réutilise, plutôt
-- que de recopier l'arbre par axe.
CREATE TABLE IF NOT EXISTS classification (
    code            TEXT PRIMARY KEY,       -- 'ca.langue', 'ca.plop'
    pays_code       TEXT NOT NULL REFERENCES pays(code),
    nom_fr          TEXT NOT NULL,
    nom_en          TEXT,
    nb_postes       INTEGER,
    source_code     TEXT REFERENCES source(code),
    remarques       TEXT
);

-- Un axe d'observation : une manière de mesurer la langue (PRD section 4).
-- L'interface n'en présuppose aucun ; elle lit cette table.
CREATE TABLE IF NOT EXISTS axe (
    code            TEXT PRIMARY KEY,       -- 'CA.langue_maternelle', 'CA.plop'
    pays_code       TEXT NOT NULL REFERENCES pays(code),
    nom_fr          TEXT NOT NULL,
    nom_en          TEXT NOT NULL,
    definition_fr   TEXT NOT NULL,
    definition_en   TEXT,
    -- Famille conceptuelle, pour signaler ce qui est comparable entre pays :
    -- 'langue_maternelle', 'langue_maison', 'langue_principale',
    -- 'connaissance', 'registre', 'derive'
    famille         TEXT NOT NULL,
    reponses_multiples BOOLEAN NOT NULL DEFAULT FALSE,
    classification_code TEXT NOT NULL REFERENCES classification(code),
    univers         TEXT,                   -- population de référence exacte
    source_code     TEXT REFERENCES source(code),
    remarques_comparabilite TEXT
);

-- Arbre des langues. Reprend la classification de la source (au Canada, la
-- hiérarchie familles → langues du recensement est déjà un arbre : on la
-- conserve au lieu d'en inventer une). Les codes ISO/Glottolog sont
-- facultatifs : « langues chinoises, n.i.a. » n'en a pas.
CREATE TABLE IF NOT EXISTS langue (
    code            TEXT PRIMARY KEY,       -- code interne stable : 'ca.langue.francais'
    classification_code TEXT NOT NULL REFERENCES classification(code),
    nom_fr          TEXT NOT NULL,
    nom_en          TEXT,
    parent_code     TEXT REFERENCES langue(code),
    profondeur      INTEGER NOT NULL,
    -- 'total'        : le dénominateur de l'axe
    -- 'regroupement'  : palier administratif (réponses uniques, langues officielles)
    -- 'famille'       : famille linguistique portant des enfants
    -- 'langue'        : une langue
    -- 'residuel'      : catégorie agrégée n.i.a. / n.d.a. de la source
    -- 'multiple'      : combinaison déclarée (« français et anglais »)
    -- 'aucune'        : absence (« ni français ni anglais », PLOP)
    -- Seul 'langue' et, selon le mode, 'residuel' entrent dans le calcul de la
    -- langue dominante : une combinaison n'est jamais répartie (PRD 6.6).
    type_noeud      TEXT NOT NULL,
    iso639_3        TEXT,
    glottocode      TEXT,
    -- Rattachement pour la légende : famille d'affichage et couleur fixe.
    famille_affichage TEXT,
    ordre_affichage INTEGER,
    officielle_pays TEXT,                   -- 'CA' si langue officielle du pays
    -- La classification elle-même vient d'une source et change d'un recensement
    -- à l'autre : elle est donc datée comme les observations.
    extraction_id   TEXT REFERENCES extraction(id)
);

------------------------------------------------------------------- observations

CREATE TABLE IF NOT EXISTS observation (
    territoire_id   TEXT NOT NULL REFERENCES territoire(id),
    annee           INTEGER NOT NULL,       -- année du recensement, non des limites
    axe_code        TEXT NOT NULL REFERENCES axe(code),
    langue_code     TEXT NOT NULL REFERENCES langue(code),
    -- Dimension présente dans la source (SDMX GENDER). 'T' = total.
    -- Conservée pour éviter de supposer silencieusement le total.
    sexe            TEXT NOT NULL DEFAULT 'T',
    effectif        DOUBLE,                 -- NULL si supprimé : l'absence est une information
    total_reference DOUBLE,                 -- dénominateur de l'axe pour ce territoire
    -- Qualité, pour le traitement des cas limites (PRD 6.6) :
    -- 'ok' | 'supprime' | 'arrondi' | 'faible_population' | 'partiellement_denombre'
    qualite         TEXT NOT NULL DEFAULT 'ok',
    drapeau_source  TEXT,                   -- symbole brut de la source ('x', 'F', '..')
    extraction_id   TEXT NOT NULL REFERENCES extraction(id),
    PRIMARY KEY (territoire_id, annee, axe_code, langue_code, sexe)
);

CREATE INDEX IF NOT EXISTS obs_axe_annee    ON observation (axe_code, annee);
CREATE INDEX IF NOT EXISTS obs_territoire   ON observation (territoire_id);
CREATE INDEX IF NOT EXISTS terr_niveau      ON territoire (niveau_code, annee_limites);

-- Correspondance entre le code de variable d'une source et (axe, langue).
-- C'est le seul endroit du schéma qui connaît les identifiants d'une source
-- donnée : ajouter un pays = ajouter des lignes ici, pas des colonnes.
CREATE TABLE IF NOT EXISTS variable_source (
    source_code     TEXT NOT NULL REFERENCES source(code),
    jeu             TEXT NOT NULL,          -- 'CA21' / 'DF_CT'
    code_variable   TEXT NOT NULL,          -- 'v_CA21_1183' / '382'
    axe_code        TEXT NOT NULL REFERENCES axe(code),
    langue_code     TEXT NOT NULL REFERENCES langue(code),
    est_total       BOOLEAN NOT NULL DEFAULT FALSE,
    extraction_id   TEXT REFERENCES extraction(id),
    PRIMARY KEY (source_code, jeu, code_variable)
);
