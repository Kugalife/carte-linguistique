// Légende en matrice (PRD 6.6) : une ligne par langue, une colonne par palier
// de part. Le palier le plus bas rappelle qu'une langue « dominante » n'est
// souvent qu'une pluralité.
import { degrade } from "./couleurs";
import { nomPoste } from "./donnees";
import { langue, t } from "./i18n";
import { AUTRES, entrees, paliersDe, reglages, type Vue } from "./reglages";

function etiquettesPaliers(seuils: number[]): string[] {
  const pct = langue() === "fr" ? " %" : "%";
  return [
    `< ${seuils[0]}${pct}`,
    ...seuils.slice(1).map((s, i) => `${seuils[i]}–${s}`),
    `≥ ${seuils[seuils.length - 1]}${pct}`,
  ];
}

/** Échantillon de rayures : les deux premières langues colorées de la vue. */
function rayuresExemple(v: Vue): string {
  const [a, b] = entrees(v).slice(0, 2).map((e) => degrade(e.couleur)[2]);
  return `repeating-linear-gradient(135deg, ${a} 0 4px, ${b} 4px 8px)`;
}

function nom(cle: string): string {
  return cle === AUTRES ? t("autres") : nomPoste(cle);
}

export function dessinerLegende(racine: HTMLElement, v: Vue): void {
  const seuils = paliersDe(v);
  const colonnes = etiquettesPaliers(seuils);
  const lignes = entrees(v)
    .map((e) => {
      const d = degrade(e.couleur);
      const cases = d
        .map((c, i) => {
          const fond = e.hachures && i === d.length - 1
            ? `repeating-linear-gradient(135deg, ${e.hachures[0]} 0 4px, ${e.hachures[1]} 4px 8px)`
            : c;
          return `<td><span class="case" style="background:${fond}" title="${nom(e.cle)} ${colonnes[i]}"></span></td>`;
        })
        .join("");
      return `<tr><th scope="row">${nom(e.cle)}</th>${cases}</tr>`;
    })
    .join("");

  racine.innerHTML = `
    <table class="matrice">
      <caption>${t("legendeLangue")} × ${t("legendePart").toLowerCase()}</caption>
      <thead><tr><td></td>${colonnes.map((c) => `<th scope="col">${c}</th>`).join("")}</tr></thead>
      <tbody>${lignes}</tbody>
    </table>
    <ul class="cas">
      <li><span class="case" style="background:${rayuresExemple(v)}"></span>${t("egaliteLegende")}</li>
      <li><span class="case hachures"></span>${t("faiblePop", { n: reglages.seuilFaiblePopulation })}</li>
      <li><span class="case points"></span>${t("nonDisponible")}</li>
    </ul>`;
}
