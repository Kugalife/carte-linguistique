#!/usr/bin/env bash
# Publie le site sur la branche gh-pages (GitHub Pages).
#
# Les données de la carte (web/public/donnees/) ne sont pas versionnées sur la
# branche principale : le pipeline les produit (06_exporter_carte.py). Elles
# sont donc construites ici puis poussées avec le site.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f public/donnees/rmr-462.pmtiles ]; then
  echo "données absentes : lancer pipeline/scripts/06_exporter_carte.py" >&2
  exit 1
fi

npm run build
touch dist/.nojekyll   # servir les fichiers tels quels, sans traitement Jekyll

depot=$(git -C .. remote get-url origin)
source=$(git -C .. rev-parse --short HEAD)
cd dist
rm -rf .git
git init -q -b gh-pages
git add -A
git -c user.name="$(git -C ../.. config user.name)" -c user.email="$(git -C ../.. config user.email)" \
  commit -q -m "Publication du site ($source)"
git push -q -f "$depot" gh-pages
rm -rf .git
echo "publié sur gh-pages depuis $source"
