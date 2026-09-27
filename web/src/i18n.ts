// Interface bilingue (PRD 6.3). Les noms de langues viennent de langues.json,
// produit par le pipeline à partir des libellés de Statistique Canada.

export type Langue = "fr" | "en";

const textes = {
  fr: {
    titre: "Atlas des langues",
    sousTitre: "Québec, recensement de 2021",
    niveauER: "Région économique",
    niveauCD: "Division de recensement (MRC)",
    niveauCSD: "Municipalité",
    niveauARR: "Arrondissement",
    noteArrondissement: "Somme des aires de diffusion de l'arrondissement, chacune arrondie à 5 par Statistique Canada. Contour : réunion de ces aires.",
    attributionVille: "Arrondissements : <a href=\"https://donnees.montreal.ca/dataset/limites-administratives-agglomeration\">Ville de Montréal</a> (CC BY 4.0)",
    carte: "Carte",
    lm: "Langue maternelle",
    plop: "Première langue officielle parlée",
    sansOfficielles: "Retirer le français et l'anglais",
    intensite: "Intensité",
    population: "Part de la population",
    allophones: "Part parmi les allophones",
    legendeLangue: "Langue dominante",
    legendePart: "Part de cette langue",
    egalite: "Égalité",
    egaliteLegende: "Égalité : rayures des deux langues",
    et: " et ",
    etAutres: " (+ {n} autres)",
    etAutre: " (+ 1 autre)",
    chacune: "chacune",
    autres: "Autres langues",
    faiblePop: "Moins de {n} habitants : pourcentages instables",
    nonDisponible: "Donnée non disponible",
    autochtoneNd: "Communauté autochtone : le recensement n'a pu y être mené entièrement, ou les données sont supprimées.",
    secteur: "Secteur de recensement",
    aire: "Aire de diffusion",
    habitants: "habitants",
    nonReponse: "Taux de non-réponse",
    composition: "Composition",
    reponsesUniques: "Les réponses multiples (ex. « français et anglais ») sont montrées à part, jamais réparties.",
    sources: "Sources",
    avertissement:
      "Statistique Canada arrondit chaque effectif au multiple de 5 : dans une petite aire, les pourcentages sont approximatifs. " +
      "Une couleur décrit un territoire, pas chacun de ses habitants.",
    fermer: "Fermer",
    rechercher: "Adresse, rue ou lieu…",
    aucunResultat: "Aucun résultat au Québec",
    cliquez: "Cliquez sur un territoire pour sa composition complète.",
    chargement: "Chargement…",
    autresPostes: "{n} autres postes",
    licence: "Contient des informations visées par la Licence du gouvernement ouvert — Canada.",
  },
  en: {
    titre: "Language Atlas",
    sousTitre: "Quebec, 2021 Census",
    niveauER: "Economic region",
    niveauCD: "Census division",
    niveauCSD: "Municipality",
    niveauARR: "Borough",
    noteArrondissement: "Sum of the borough's dissemination areas, each rounded to 5 by Statistics Canada. Outline: union of those areas.",
    attributionVille: "Boroughs: <a href=\"https://donnees.montreal.ca/dataset/limites-administratives-agglomeration\">City of Montréal</a> (CC BY 4.0)",
    carte: "Map",
    lm: "Mother tongue",
    plop: "First official language spoken",
    sansOfficielles: "Remove French and English",
    intensite: "Intensity",
    population: "Share of population",
    allophones: "Share of allophones",
    legendeLangue: "Leading language",
    legendePart: "Share of that language",
    egalite: "Tie",
    egaliteLegende: "Tie: stripes of both languages",
    et: " and ",
    etAutres: " (+ {n} more)",
    etAutre: " (+ 1 more)",
    chacune: "each",
    autres: "Other languages",
    faiblePop: "Fewer than {n} residents: unstable percentages",
    nonDisponible: "Data not available",
    autochtoneNd: "Indigenous community: the census could not be fully conducted here, or data are suppressed.",
    secteur: "Census tract",
    aire: "Dissemination area",
    habitants: "residents",
    nonReponse: "Non-response rate",
    composition: "Composition",
    reponsesUniques: "Multiple responses (e.g. “English and French”) are shown separately, never split.",
    sources: "Sources",
    avertissement:
      "Statistics Canada rounds every count to a multiple of 5: in a small area, percentages are approximate. " +
      "A colour describes an area, not each of its residents.",
    fermer: "Close",
    rechercher: "Address, street or place…",
    aucunResultat: "No result in Quebec",
    cliquez: "Click an area for its full composition.",
    chargement: "Loading…",
    autresPostes: "{n} more",
    licence: "Contains information licensed under the Open Government Licence – Canada.",
  },
} as const;

export type Cle = keyof (typeof textes)["fr"];

let courante: Langue = (navigator.language || "fr").startsWith("en") ? "en" : "fr";

export function langue(): Langue {
  return courante;
}
export function choisirLangue(l: Langue): void {
  courante = l;
  document.documentElement.lang = l;
}
export function t(cle: Cle, vars: Record<string, string | number> = {}): string {
  let s: string = textes[courante][cle];
  for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
  return s;
}

export function nombre(n: number): string {
  return n.toLocaleString(courante === "fr" ? "fr-CA" : "en-CA", { maximumFractionDigits: 0 });
}
export function pourcentage(p: number): string {
  return (p * 100).toLocaleString(courante === "fr" ? "fr-CA" : "en-CA", { maximumFractionDigits: p < 0.1 ? 1 : 0 }) + (courante === "fr" ? " %" : "%");
}

/** Nom d'un niveau géographique du modèle (CA.DA, CA.CSD…). */
export function nomNiveau(niveau: string): string {
  switch (niveau) {
    case "CA.ER": return t("niveauER");
    case "CA.CD": return t("niveauCD");
    case "CA.CSD": return t("niveauCSD");
    case "CA.ARR": return t("niveauARR");
    case "CA.CT": return t("secteur");
    default: return t("aire");
  }
}
