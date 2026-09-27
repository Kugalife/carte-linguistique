// Fichiers produits par pipeline/scripts/06_exporter_carte.py.
import { langue } from "./i18n";

const BASE = "./donnees/";
export const PROVINCE = "24";
export const URL_TUILES = new URL(`${BASE}pr-${PROVINCE}.pmtiles`, document.baseURI).href;

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
  nom: string | null;
  population: number | null;
  non_reponse_pct: number | null;
  superficie_km2: number | null;
  axes: Partial<Record<"lm" | "plop", { total: number; postes: [string, number][] }>>;
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

/**
 * Fichier de composition d'un territoire : FNV-1a 32 bits de son identifiant,
 * modulo 256. Même calcul que pipeline/scripts/06_exporter_carte.py.
 */
function fichierComposition(id: string): string {
  let h = 0x811c9dc5;
  for (const octet of new TextEncoder().encode(id)) {
    h = Math.imul(h ^ octet, 0x01000193) >>> 0;
  }
  return (h % 256).toString(16).padStart(2, "0");
}

const cache = new Map<string, Promise<Record<string, Fiche>>>();

/** Composition complète d'un territoire, lue au clic. */
export async function composition(id: string): Promise<Fiche | undefined> {
  const nom = fichierComposition(id);
  if (!cache.has(nom)) {
    cache.set(nom, fetch(`${BASE}composition/${nom}.json`).then((r) => r.json()));
  }
  return (await cache.get(nom)!)[id];
}
