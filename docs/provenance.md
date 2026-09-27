# Convention de provenance

**Règle du projet :** toute valeur affichée sur la carte doit pouvoir être
remontée jusqu'à la requête qui l'a produite. Cette exigence figure au PRD
(section 5, « Fiabilité » ; section 8, « Traçabilité »). Elle est ici une
contrainte du schéma, pas une recommandation : la colonne
`observation.extraction_id` est `NOT NULL`, donc une observation sans provenance
ne peut pas entrer dans la base.

Quatre tables portent un `extraction_id` : `observation`, `territoire`, `langue`
et `variable_source`. Les trois dernières viennent aussi d'une source et changent
d'un recensement à l'autre — les numéros de poste sont renumérotés, des langues
apparaissent dans la classification. Savoir de quelle extraction vient l'arbre
des langues est donc du même ordre que savoir d'où vient un effectif.

## Ce qu'enregistre une extraction

Une ligne d'`extraction` = une exécution du pipeline contre une source.

| Colonne | Rôle |
|---|---|
| `id` | `<source>:<horodatage UTC>:<12 premiers caractères du SHA-256 de la requête>` |
| `source_code` | vers `source` : organisme, licence, URL de base |
| `extrait_le` | instant de l'appel, en UTC |
| `requete` | l'URL ou l'appel **exact**, rejouable tel quel |
| `reponse_sha256` | empreinte de la réponse brute |
| `nb_lignes` | nombre de lignes reçues, pour repérer une réponse tronquée |
| `tableau_source` | produit ou dataflow (`DF_CT`, `CL_CHARACTERISTIC`, `98-10-0169`) |
| `version_source` | version du jeu (`1.3`, `CA21`) — elle change sans préavis |
| `publie_le` | date de diffusion annoncée par la source |
| `outil_version` | version du pipeline (`atlas.__version__`) |

L'identifiant est dérivé de la requête et non d'un compteur : deux extractions
de la même requête sont reconnaissables, et l'identifiant ne dépend pas de
l'ordre d'exécution.

## Réponses brutes

Les réponses d'observations sont écrites telles que reçues sous
`data/raw/<source>/<id>.bin`. Sans elles, `reponse_sha256` ne serait vérifiable
contre rien. Ce répertoire n'est pas versionné : le pipeline le reconstruit.

Exception : les fichiers de limites cartographiques (jusqu'à 197 Mo) sont
conservés sous leur nom d'origine, `data/raw/statcan_limites/<fichier>.zip`, et
ne sont téléchargés qu'une fois. Chaque chargement recalcule leur empreinte et
crée une extraction : si Statistique Canada republie un fichier, l'empreinte
change.

Les réponses de *structure* (définitions, codelists) sont mises en cache sous
`data/interim/sdmx/` pour ne pas solliciter inutilement le service — elles
pèsent près de 700 Ko et sont demandées plusieurs fois par exécution. Ce cache
ne contient jamais d'observations : une donnée chiffrée est toujours redemandée
et retracée.

## Vérifier une valeur

```python
from atlas import db, provenance
con = db.ouvrir()
provenance.tracer(con, "2021S05074620001.00", 2021, "CA.plop")
```

renvoie, pour chaque poste, l'effectif, son indicateur de qualité, la source, le
tableau, sa version et la requête d'origine.

Le script `02_charger_secteur.py` vérifie au passage qu'aucune observation n'est
orpheline de provenance et refuse de se déclarer conforme si c'est le cas.

## Qualité d'une valeur

`observation.qualite` distingue ce que la carte ne doit jamais confondre :

| Valeur | Signification |
|---|---|
| `ok` | effectif publié |
| `supprime` | donnée retirée pour confidentialité — **pas un zéro** |
| `arrondi` | la source signale un arrondissement (multiples de 5) |
| `faible_population` | sous le seuil d'affichage fiable |
| `partiellement_denombre` | territoire partiellement dénombré (réserves) |

Un effectif absent est chargé comme `NULL` avec `qualite = 'supprime'`. Le
remplacer par zéro serait une invention de donnée ; c'est le risque « trous dans
la carte » du PRD section 10, et il se règle à l'affichage par un motif
« donnée non disponible », pas au chargement.

Deux indicateurs complètent cela au niveau du territoire :
`tnr_questionnaire_abrege` et `tnr_questionnaire_long`, les taux globaux de
non-réponse publiés par la source. Statistique Canada recommande la prudence
au-delà de 25 % : c'est un critère objectif d'avertissement, distinct du seuil
de faible population.

## Reproductibilité

La base est un **produit** du pipeline, jamais un état à corriger sur place.
Les identifiants sont des clés naturelles (DGUID, code interne de langue), donc
une réexécution produit les mêmes clés.

DuckDB refuse de supprimer ou de mettre à jour une ligne référencée par une clé
étrangère et ne connaît pas les contraintes différées. Les données de référence
et les classifications sont donc insérées en `ON CONFLICT DO NOTHING`, et se
modifient en reconstruisant la base :

```
python pipeline/scripts/02_charger_secteur.py --recreer
```

Seules les observations, que rien ne référence, sont réellement mises à jour
par une réextraction — avec leur nouvelle provenance.
