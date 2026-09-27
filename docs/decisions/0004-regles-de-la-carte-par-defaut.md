# 0004 — Règles éditoriales de la carte par défaut

**Date :** 27 septembre 2026 · **Statut :** accepté

## Contexte

Le PRD (6.6) fixe le mode par défaut, « langue dominante × intensité », sans
dire comment traiter les cas qu'on rencontre dès le premier quartier : réponses
multiples, égalités, petites aires, choix des couleurs. Ces règles changent ce
que la carte affirme. Elles sont donc éditoriales, pas techniques.

## Décision

Toutes ces règles vivent dans un seul fichier, `config/carte.json`. Chaque
réglage y porte son statut (`decide` ou `provisoire`) et, quand il y en a, ses
alternatives. On change de règle en modifiant ce fichier, sans toucher au code.

| Règle | Choix | Statut |
|---|---|---|
| Axe à l'ouverture | Langue maternelle | décidé |
| Réponses multiples | Exclues du calcul de la langue dominante | décidé, révisable |
| Seuil de faible population | 100 habitants : l'aire est hachurée en dessous | décidé, à ajuster |
| Paliers d'intensité | < 40 %, 40-60 %, 60-80 %, ≥ 80 % | décidé (PRD) |
| Couleurs fixes | Français en bleu, anglais en rouge, espagnol en jaune | décidé |
| Trois autres couleurs | Arabe, créole haïtien, italien | provisoire |
| Égalité | Stricte : effectifs identiques seulement | décidé |

## Pourquoi

**Réponses multiples.** « Français et anglais » n'est pas une langue. En faire
une teinte de dominance ferait apparaître une couleur « mixte » qui se lirait
comme une communauté linguistique. Le schéma applique déjà cette règle
(`langue.type_noeud`). Deux autres options sont documentées dans
`config/carte.json`, si l'on veut trancher autrement : la réponse multiple
concourt comme catégorie à part, ou elle est répartie entre ses langues de
manière explicite.

**Trois autres couleurs provisoires.** Elles sont attribuées aux langues qui
dominent probablement des aires de diffusion hors du français et de l'anglais.
Ce sont des estimations tant que les aires de la région de Montréal ne sont pas
chargées. Le chargement dira quelles langues dominent réellement des aires.
Une langue sans couleur tombe dans « autres langues », en gris.

**Six teintes et non huit.** Le PRD autorise jusqu'à 8 couleurs. Avec le bleu,
le rouge et le jaune imposés, aucune septième teinte ne passe le test de
daltonisme : tous les violets testés se confondent avec le bleu du français
(deutéranopie). Sur une carte, n'importe quelle aire peut toucher n'importe
quelle autre. La palette est donc vérifiée **sur toutes les paires**, pas
seulement sur les couleurs voisines dans la légende.

**PLOP.** « Français et anglais » est rendu en hachures bleu/rouge. Toute autre
teinte reprendrait la couleur d'une langue maternelle, et changer d'axe
changerait le sens d'une couleur sous les yeux du lecteur.

## Vérification de la palette

Test fait avec un validateur de palette : bande de clarté, saturation minimale,
distance perçue entre toutes les paires en vision normale et pour les trois
formes de daltonisme.

- Les 6 teintes de langue maternelle **passent**. La paire bleu ciel / rose est
  à la limite pour la deutéranopie (ΔE 6,3). C'est acceptable parce que la
  légende et l'info-bulle nomment toujours la langue.
- Le jaune et le rose contrastent peu avec un fond clair (2,5:1 et 2,7:1).
  Il faut compenser : bordure des aires, étiquettes et tableau de données.

## Conséquences et points à vérifier en phase 1

- **Le test porte sur les couleurs de base, pas sur les dégradés d'intensité.**
  Or la clarté varie avec la part de la langue, et un bleu ciel foncé se
  rapproche du bleu du français. Il faudra tester les 4 paliers de chaque teinte.
- **Le jaune pâle disparaît sur fond clair.** Le palier < 40 % ne doit pas
  descendre trop près du blanc pour le jaune.
- **Égalité stricte.** Les effectifs sont arrondis au multiple de 5 : dans une
  petite aire, 20 locuteurs de français contre 20 d'arabe est fréquent. Seule
  l'égalité exacte donne la catégorie « égalité ». Un écart de 5, pourtant peu
  significatif, désigne une langue dominante : le palier < 40 % et le seuil de
  faible population signalent déjà cette fragilité. L'option « marge » (égalité
  jusqu'à 5 d'écart) reste documentée dans `config/carte.json`.
