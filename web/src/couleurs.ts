// Dégradés d'intensité et expressions de style MapLibre.
//
// La teinte dit la langue, la clarté dit sa part (PRD 6.6). Chaque palier
// mélange la couleur de base avec le blanc dans l'espace OKLab, où la clarté
// perçue varie régulièrement : un mélange en RGB éclaircirait inégalement les
// teintes (le jaune paraîtrait délavé bien avant le bleu).
import type { ExpressionSpecification } from "maplibre-gl";
import { AUTRES, EGALITE, entrees, paliersDe, proprietes, reglages, type Vue } from "./reglages";

/** Part de la couleur de base à chaque palier, du plus clair au plus foncé. */
const INTENSITES = [0.3, 0.52, 0.76, 1];

export const COULEUR_NON_DISPONIBLE = "#ffffff";

type Lab = [number, number, number];

function versLineaire(c: number): number {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}
function versSrgb(c: number): number {
  return c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
}

function hexVersOklab(hex: string): Lab {
  const [r, g, b] = [1, 3, 5].map((i) => versLineaire(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function oklabVersHex([L, a, b]: Lab): string {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return "#" + rgb.map((c) => Math.round(Math.min(1, Math.max(0, versSrgb(c))) * 255).toString(16).padStart(2, "0")).join("");
}

const BLANC = hexVersOklab("#ffffff");

/** Les 4 paliers d'une teinte, du plus clair au plus foncé. */
export function degrade(base: string): string[] {
  const c = hexVersOklab(base);
  return INTENSITES.map((t) => oklabVersHex([0, 1, 2].map((i) => BLANC[i] + (c[i] - BLANC[i]) * t) as Lab));
}

/** Nombre de paliers d'une vue : un de plus que de seuils. */
export function nbPaliers(v: Vue): number {
  return paliersDe(v).length + 1;
}

/** Couleur de remplissage d'une entité selon la vue. */
export function expressionRemplissage(v: Vue): ExpressionSpecification {
  const p = proprietes(v);
  const palier: ExpressionSpecification = ["to-number", ["get", p.palier], 0];
  const branches: (string | ExpressionSpecification)[] = [];
  for (const e of entrees(v)) {
    const d = degrade(e.couleur);
    branches.push(e.cle, ["match", palier, 0, d[0], 1, d[1], 2, d[2], d[3]] as ExpressionSpecification);
  }
  return [
    "case",
    ["==", ["get", "nd"], true], COULEUR_NON_DISPONIBLE,
    // Égalité : le remplissage reste vide, la couche de rayures le dessine.
    ["==", ["get", p.langue], EGALITE], "rgba(0,0,0,0)",
    ["!", ["has", p.cle]], COULEUR_NON_DISPONIBLE,
    ["==", ["get", p.cle], null], COULEUR_NON_DISPONIBLE,
    ["match", ["get", p.cle], ...branches, degrade(entrees(v).find((e) => e.cle === AUTRES)?.couleur ?? "#8a8f98")[1]],
  ] as unknown as ExpressionSpecification;
}

/** Motif de hachures diagonales, pour les aires à faible population. */
export function motifHachures(couleur: string, taille = 8): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = taille;
  const ctx = c.getContext("2d")!;
  ctx.strokeStyle = couleur;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  // Trois segments pour que le motif se raccorde d'une tuile à l'autre.
  for (const d of [-taille, 0, taille]) {
    ctx.moveTo(d, taille);
    ctx.lineTo(d + taille, 0);
  }
  ctx.stroke();
  return ctx.getImageData(0, 0, taille, taille);
}

/** Motif à points, pour les données non disponibles. */
export function motifPoints(couleur: string, taille = 6): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = taille;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = couleur;
  ctx.beginPath();
  ctx.arc(taille / 2, taille / 2, 1, 0, 2 * Math.PI);
  ctx.fill();
  return ctx.getImageData(0, 0, taille, taille);
}

/** Couleur de base de chaque clé de couleur, toutes cartes confondues. */
function couleurDeCle(cle: string): string {
  if (cle === AUTRES) return reglages.autres;
  const langue = reglages.couleurs.find((c) => c.langue === cle);
  if (langue) return langue.couleur;
  const plop = reglages.plop[cle];
  return plop && plop.startsWith("#") ? plop : reglages.autres;
}

/** Nom d'image des rayures d'une égalité, construit dans le style MapLibre. */
export function expressionRayures(v: Vue): ExpressionSpecification {
  const p = proprietes(v);
  const c2 = p.cle.replace(/_c$/, "_c2");
  return ["concat", "rayures|", ["get", p.cle], "|", ["get", c2], "|",
    ["to-string", ["to-number", ["get", p.palier], 0]]] as ExpressionSpecification;
}

export const PREFIXE_RAYURES = "rayures|";

/**
 * Rayures des deux langues à égalité, à la clarté du palier (décision 0004).
 * Créées à la demande : il y a une image par paire de couleurs et par palier.
 */
export function motifRayures(nom: string, taille = 16): ImageData | null {
  const [, cle1, cle2, palier] = nom.split("|");
  if (!cle1 || !cle2) return null;
  const i = Math.min(Number(palier) || 0, INTENSITES.length - 1);
  const [a, b] = [degrade(couleurDeCle(cle1))[i], degrade(couleurDeCle(cle2))[i]];
  const c = document.createElement("canvas");
  c.width = c.height = taille;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = a;
  ctx.fillRect(0, 0, taille, taille);
  // Rayures à 45°, deux bandes de même largeur par période ; trois segments
  // pour que le motif se raccorde d'une tuile à l'autre.
  ctx.strokeStyle = b;
  ctx.lineWidth = taille / (2 * Math.SQRT2);
  ctx.beginPath();
  for (const d of [-taille, 0, taille]) {
    ctx.moveTo(d, taille);
    ctx.lineTo(d + taille, 0);
  }
  ctx.stroke();
  return ctx.getImageData(0, 0, taille, taille);
}
