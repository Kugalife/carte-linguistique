# 0003 — Le service SDMX de Statistique Canada comme source primaire

**Date :** 26 septembre 2026 · **Statut :** accepté

## Contexte

Le PRD prévoyait CensusMapper (via le paquet R `cancensus`) comme source
principale des données du recensement, et « l'API de Statistique Canada (Web Data
Service et service SDMX […], à valider) » comme source officielle « utile pour
contrôler les valeurs ».

## Décision

Inversion : le service SDMX du profil du recensement est la source primaire pour
2021. CensusMapper devient la source des recensements antérieurs (phase 3) et un
moyen de contrôle croisé.

## Pourquoi

La validation demandée par le PRD a été faite (voir `docs/sources-canada.md`) et
donne un résultat net :

- Le service SDMX **ne demande aucune clé API**, ce qui retire une dépendance
  externe du chemin critique de la phase 0 et du MVP.
- Il couvre **tous les niveaux géographiques jusqu'à l'aire de diffusion**, dont
  le secteur de recensement, avec la hiérarchie complète des langues.
- Il fournit des métadonnées que CensusMapper n'a pas : libellés **bilingues**,
  liens **parent-enfant** de la classification, **taux de non-réponse** par
  territoire, dates de diffusion par thème.
- Il est la source officielle, donc la référence en cas d'écart.

À l'inverse, le Web Data Service `CPR20xx.json`, que le PRD cite en premier, **ne
couvre pas 2021** : il répond en JSON pour 2016 et renvoie du HTML pour 2021.

Le prix de ce choix est que le service SDMX est mal documenté : la forme de la
clé de données contredit sa propre définition de structure, et trois de ses
particularités ne se découvrent qu'en essayant. Elles sont consignées dans
`docs/sources-canada.md` et dans l'en-tête du connecteur.

## Conséquences

- La phase 0 se termine sans clé API. La tâche « obtenir une clé CensusMapper »
  de la roadmap se déplace vers la phase 3, où elle redevient nécessaire.
- Le contrôle croisé prévu en phase 0 change de nature : il ne s'agit plus de
  vérifier CensusMapper contre Statistique Canada, mais de vérifier la cohérence
  interne de la source officielle (les totaux d'un niveau redonnent-ils le
  niveau supérieur). C'est ce que fait `02_charger_secteur.py`. Le contrôle
  croisé entre sources attendra la clé.
- Le connecteur découvre la version du dataflow à l'exécution : une version
  codée en dur casserait à la prochaine révision.
