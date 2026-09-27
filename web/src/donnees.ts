// Fichiers produits par pipeline/scripts/06_exporter_carte.py.
import { langue } from "./i18n";

const BASE = "./donnees/";
export const RMR = "462";
export const URL_TUILES = new URL(`${BASE}rmr-${RMR}.pmtiles`, document.baseURI).href;

export interface Poste {
  fr: string;
  en: string;
  type: string;
  parent: string | null;
  famille: string | null;
}

export interface Source {
  source: string;
  organisme: string;
  licence: string;
  licence_url: string;
  tableau: string;
  version: string;
  publie_le: string | null;
  extrait_au: string;
}

export interface Fiche {
  id: string;
  niveau: string;
  population: number | null;
  non_reponse_pct: number | null;
  superficie_km2: number | null;
  axes: Partial<Record<"lm" | "plop", { total: number; postes: [string, number][] }>>;
}

export interface Composition {
  secteur: Fiche;
  aires: Record<string, Fiche>;
}

let postes: Record<string, Poste> = {};

export async function chargerPostes(): Promise<void> {
  postes = await (await fetch(`${BASE}langues.json`)).json();
}

export function nomPoste(code: string): string {
  const p = postes[code];
  return p ? p[langue()] ?? p.fr : code;
}

export function typePoste(code: string): string | undefined {
  return postes[code]?.type;
}

export async function chargerSources(): Promise<Source[]> {
  return (await fetch(`${BASE}sources.json`)).json();
}

const cache = new Map<string, Promise<Composition>>();

/** Composition d'un secteur et de ses aires : un fichier par secteur, lu au clic. */
export function composition(secteurId: string): Promise<Composition> {
  const code = secteurId.replace(/^2021S0507/, "");
  if (!cache.has(code)) {
    cache.set(code, fetch(`${BASE}composition/${code}.json`).then((r) => r.json()));
  }
  return cache.get(code)!;
}
