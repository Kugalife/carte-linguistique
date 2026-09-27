# 0005 — Site statique, projet ouvert

**Date :** 27 septembre 2026 · **Statut :** accepté

## Décision

1. **Le MVP est un site entièrement statique.** Tuiles vectorielles PMTiles et
   fichiers JSON préparés par le pipeline, sans serveur ni API. FastAPI (PRD 9)
   attend un besoin réel, au plus tôt les projections (phase 5).
2. **Front-end : Vite + TypeScript, sans framework**, autour de MapLibre GL JS.
   L'interface est petite ; un framework s'ajoutera si elle grossit.
3. **Le projet est ouvert : code et données.** Cela répond à la question ouverte
   du PRD (section 11).

## Licence et hébergement

**Licence** (décidée le 27 septembre ; fichiers `LICENSE` et `LICENSE-DONNEES`).
- Code : MIT, simple et la plus répandue.
- Documentation et données dérivées : CC BY 4.0.
- Données sources : elles restent sous la Licence du gouvernement ouvert du
  Canada, qui impose de citer Statistique Canada. La carte et le dépôt le font.

**Hébergement : GitHub Pages pour le MVP, Render plus tard** (décidé le 27 septembre).

PMTiles fonctionne sans serveur de tuiles parce que le navigateur lit des
morceaux du fichier par requêtes HTTP partielles (*Range*). L'hébergeur doit
donc les accepter.

- **GitHub Pages** les accepte, se déploie depuis le dépôt et est gratuit.
  Limites : 100 Mo par fichier et 1 Go par site, suffisant pour Montréal et
  probablement pour le Québec.
- **Render** héberge aussi les sites statiques gratuitement, mais ajoute un
  compte sans rien apporter pour un site statique. Le support des requêtes
  partielles sur son réseau de diffusion n'est pas vérifié. Render devient utile
  quand il y aura une API (phase 5). Son offre gratuite met le service en veille
  après une période d'inactivité.
- **Pour le Canada complet (phase 4)**, les tuiles dépasseront les limites de
  GitHub. Cloudflare R2 est gratuit jusqu'à 10 Go, sans frais de sortie.

## Conséquences

- Aucun coût d'hébergement pendant les phases 1 à 3.
- Le pipeline produit tout ce que le site affiche ; le site ne calcule rien
  qu'on ne puisse retrouver dans les fichiers publiés.
- La carte affiche la mention de Statistique Canada exigée par sa licence.
