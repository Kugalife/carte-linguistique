# 0006 — Deux emboîtements : administratif et métropolitain

**Date :** 27 septembre 2026 · **Statut :** accepté

## Contexte

En phase 1, limitée à la RMR de Montréal, une aire de diffusion avait pour
parent son secteur de recensement (`territoire.parent_id`). La phase 2 couvre
tout le Québec, et deux faits rendent ce choix intenable :

- **Hors des RMR et des agglomérations à secteurs, il n'y a pas de secteurs.**
  Une aire de Gaspé ou de Chibougamau n'a pas de secteur parent.
- **Les deux découpages ne s'emboîtent pas l'un dans l'autre.** La chaîne
  administrative (province → région économique → division de recensement →
  subdivision → aire) couvre tout le territoire. La chaîne métropolitaine
  (RMR → secteur → aire) n'en couvre qu'une partie, et un secteur n'est pas
  garanti de rester dans une seule subdivision.

Un territoire n'a qu'un `parent_id`. Il faut donc choisir une chaîne principale
et loger l'autre ailleurs.

## Décision

1. **`parent_id` suit la chaîne administrative**, qui couvre tout le territoire :
   province → région économique → division de recensement → subdivision de
   recensement → aire de diffusion. La RMR garde la province pour parent, le
   secteur garde la RMR.
2. **Une table `territoire_inclusion` porte les autres appartenances** :
   aire ∈ secteur, subdivision ∈ RMR. Rien ne la référence : elle se recharge
   librement, comme `territoire_geometrie`.
3. **Chaque rattachement est vérifié**, par code quand le code le permet (une
   subdivision `2466023` appartient à la division `2466`) et par position sinon
   (point intérieur, `ST_PointOnSurface`), puis contrôlé par les superficies :
   la somme des enfants doit redonner le parent.

## Conséquences

- **La base est reconstruite.** DuckDB interdit de modifier `parent_id` d'une
  ligne référencée ; la base est de toute façon un produit du pipeline.
- **Les scripts propres à la RMR sont généralisés à une province** : les limites,
  les données et l'export prennent un code de province, et la RMR de Montréal en
  devient un sous-ensemble.
- **Sur la carte, deux chemins de zoom coexistent.** Dans une RMR, on passe de la
  subdivision au secteur puis à l'aire ; ailleurs, de la subdivision directement
  à l'aire. Les aires hors secteurs s'affichent donc plus tôt.
- **Les fichiers de composition du panneau de détail ne sont plus rangés par
  secteur** (une aire rurale n'en a pas) mais répartis en 256 fichiers selon
  une empreinte de l'identifiant, calculée de la même façon par le pipeline et
  par le site.
