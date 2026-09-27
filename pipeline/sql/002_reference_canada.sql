-- Données de référence — Canada.
--
-- Réappliqué à chaque ouverture de la base (atlas/db.py), d'où ON CONFLICT
-- DO NOTHING : le script doit être rejouable sans erreur.
--
-- Pourquoi DO NOTHING plutôt qu'un upsert : DuckDB refuse de supprimer OU de
-- mettre à jour une ligne référencée par une clé étrangère, et ne connaît pas
-- les contraintes différées. INSERT OR REPLACE (qui supprime puis réinsère) et
-- ON CONFLICT DO UPDATE échouent donc tous deux sur un niveau géographique
-- parent ou une langue parente.
--
-- Conséquence assumée : modifier une donnée de référence n'a pas d'effet sur une
-- base existante. La façon de la modifier est de reconstruire la base
--     python pipeline/scripts/02_charger_secteur.py --recreer
-- ce qui est cohérent avec la reproductibilité exigée au PRD section 8 : la base
-- est un produit du pipeline, jamais un état à corriger sur place.
--
-- Le Canada n'est qu'un jeu de lignes : ajouter un pays n'ajoute pas de colonne.


---------------------------------------------------------------- sources

INSERT INTO source (code, nom, organisme, licence, licence_url, url_base, remarques) VALUES
  ('statcan_sdmx_cp',
   'Profil du recensement — service SDMX',
   'Statistique Canada',
   'Licence du gouvernement ouvert — Canada',
   'https://www.statcan.gc.ca/fr/reference/licence',
   'https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest',
   'Source primaire des effectifs 2021, sans clé API. Un dataflow par niveau géographique (DF_PR, DF_ER, DF_CD, DF_CSD, DF_CMACA, DF_ADA, DF_CT, DF_DA). Porte la hiérarchie complète des langues, en français et en anglais, jusqu''à l''aire de diffusion.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, nom, organisme, licence, licence_url, url_base, remarques) VALUES
  ('censusmapper',
   'CensusMapper API (paquet R cancensus)',
   'CensusMapper / Jens von Bergmann',
   'Conditions de CensusMapper ; données sous Licence du gouvernement ouvert',
   'https://censusmapper.ca/api',
   'https://censusmapper.ca/api/v1',
   'Clé API requise pour les données, pas pour les métadonnées. Utile pour le contrôle croisé et surtout pour les recensements 1996 à 2016 (phase 3), que le service SDMX ne couvre pas.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, nom, organisme, licence, licence_url, url_base, remarques) VALUES
  ('statcan_limites',
   'Fichiers des limites cartographiques',
   'Statistique Canada',
   'Licence du gouvernement ouvert — Canada',
   'https://www.statcan.gc.ca/fr/reference/licence',
   'https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index-fra.cfm',
   'Version cartographique (découpée selon le littoral), à préférer à la version numérique pour l''affichage.')
ON CONFLICT (code) DO NOTHING;

------------------------------------------------------------------ pays

INSERT INTO pays (code, nom_fr, nom_en) VALUES
  ('CA', 'Canada', 'Canada')
ON CONFLICT (code) DO NOTHING;

------------------------------------------------- hiérarchie géographique
-- rang croissant = plus fin. couverture_partielle : le niveau n'existe pas
-- partout — hors RMR il n'y a pas de secteur de recensement et l'on passe de la
-- subdivision directement à l'aire de diffusion (roadmap phase 2).
-- Une ligne par instruction : un parent doit exister avant son enfant.

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.C',     'CA', 'C',     'Pays',                     'Country',                   0, NULL,       FALSE, 0,    4)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.PR',    'CA', 'PR',    'Province ou territoire',   'Province or territory',     1, 'CA.C',     FALSE, 4,    6)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.ER',    'CA', 'ER',    'Région économique',        'Economic region',           2, 'CA.PR',    FALSE, 6,    7.5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.CD',    'CA', 'CD',    'Division de recensement',  'Census division',           3, 'CA.PR',    FALSE, 7.5,  9)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.CMACA', 'CA', 'CMACA', 'Région métropolitaine ou agglomération', 'Census metropolitan area or agglomeration', 3, 'CA.PR', TRUE, NULL, NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.CSD',   'CA', 'CSD',   'Subdivision de recensement','Census subdivision',       4, 'CA.CD',    FALSE, 9,    10.5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.ADA',   'CA', 'ADA',   'Aire de diffusion agrégée','Aggregate dissemination area',5,'CA.CSD',  FALSE, 10.5, 11.5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.CT',    'CA', 'CT',    'Secteur de recensement',   'Census tract',              6, 'CA.CMACA', TRUE,  11.5, 13)
ON CONFLICT (code) DO NOTHING;

INSERT INTO niveau_geo (code, pays_code, code_local, nom_fr, nom_en, rang, parent_code, couverture_partielle, zoom_min, zoom_max) VALUES
  ('CA.DA',    'CA', 'DA',    'Aire de diffusion',        'Dissemination area',        7, 'CA.CSD',   FALSE, 13,   22)
ON CONFLICT (code) DO NOTHING;

------------------------------------------------ classifications linguistiques

INSERT INTO classification (code, pays_code, nom_fr, nom_en, nb_postes, source_code, remarques) VALUES
  ('ca.langue', 'CA',
   'Classification des langues du recensement canadien',
   'Canadian census language classification',
   NULL, 'statcan_sdmx_cp',
   'Arbre familles → langues publié par Statistique Canada, 331 postes. Partagé par les axes langue maternelle et langue parlée à la maison, dont les postes sont identiques (vérifié en phase 0). Le regroupement par famille demandé pour la légende (PRD 6.6) se déduit de cet arbre : il n''est pas à reconstruire depuis Glottolog.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO classification (code, pays_code, nom_fr, nom_en, nb_postes, source_code, remarques) VALUES
  ('ca.plop', 'CA',
   'Première langue officielle parlée — 4 postes',
   'First official language spoken — 4 categories',
   5, 'statcan_sdmx_cp',
   'Variable dérivée. « Français et anglais » et « Ni français ni anglais » ne sont pas des langues mais des états linguistiques : la table langue les type respectivement multiple et aucune, pour qu''ils n''entrent jamais dans le calcul de la langue dominante (PRD 6.6).')
ON CONFLICT (code) DO NOTHING;

-------------------------------------------------------------------- axes
-- L'interface lit cette table et ne présuppose aucun axe (PRD section 4).

INSERT INTO axe (code, pays_code, nom_fr, nom_en, definition_fr, definition_en, famille, reponses_multiples, classification_code, univers, source_code, remarques_comparabilite) VALUES
  ('CA.langue_maternelle', 'CA',
   'Langue maternelle', 'Mother tongue',
   'Première langue apprise à la maison dans l''enfance et encore comprise au moment du recensement.',
   'First language learned at home in childhood and still understood at the time of the census.',
   'langue_maternelle', TRUE, 'ca.langue',
   'Population totale à l''exclusion des résidents des établissements institutionnels',
   'statcan_sdmx_cp',
   'Données intégrales (100 %) : disponibles à l''aire de diffusion. Comparable en principe aux axes « langue maternelle » d''autres pays, mais la formulation canadienne exige que la langue soit « encore comprise », condition que tous les pays n''imposent pas.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO axe (code, pays_code, nom_fr, nom_en, definition_fr, definition_en, famille, reponses_multiples, classification_code, univers, source_code, remarques_comparabilite) VALUES
  ('CA.plop', 'CA',
   'Première langue officielle parlée', 'First official language spoken',
   'Variable dérivée classant chaque personne selon sa langue officielle principale, à partir de la connaissance des langues officielles, de la langue maternelle et de la langue parlée à la maison.',
   'Derived variable classifying each person by their main official language.',
   'derive', FALSE, 'ca.plop',
   'Population totale à l''exclusion des résidents des établissements institutionnels',
   'statcan_sdmx_cp',
   'Variable dérivée propre au Canada, construite pour l''application de la Loi sur les langues officielles. NON comparable à un axe d''un autre pays : avertissement obligatoire au changement de pays.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO axe (code, pays_code, nom_fr, nom_en, definition_fr, definition_en, famille, reponses_multiples, classification_code, univers, source_code, remarques_comparabilite) VALUES
  ('CA.langue_maison', 'CA',
   'Langue parlée le plus souvent à la maison', 'Language spoken most often at home',
   'Langue parlée le plus souvent à la maison au moment du recensement.',
   'Language spoken most often at home at the time of the census.',
   'langue_maison', TRUE, 'ca.langue',
   'Population totale à l''exclusion des résidents des établissements institutionnels',
   'statcan_sdmx_cp',
   'Données intégrales (100 %), même classification que la langue maternelle. Catalogué en phase 0 mais non chargé. C''est cet axe, et non la PLOP, qui rendra le Canada comparable aux États-Unis, à l''Australie et à la Nouvelle-Zélande (PRD section 4, roadmap phase 6). Voir docs/sources-canada.md.')
ON CONFLICT (code) DO NOTHING;
