import { defineConfig } from "vite";

export default defineConfig({
  // Chemins relatifs : le site fonctionne sous le sous-chemin de GitHub Pages.
  base: "./",
  // config/carte.json vit à la racine du dépôt, hors de web/ : le pipeline et le
  // site lisent le même fichier de réglages.
  server: { fs: { allow: [".."] } },
  // MapLibre charge son worker comme module ES.
  worker: { format: "es" },
});
