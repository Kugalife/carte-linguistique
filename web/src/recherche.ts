// Recherche d'adresses et de lieux avec Photon (données OpenStreetMap), choisi
// parce qu'il est conçu pour l'autocomplétion, gratuit et sans clé. Le service
// public demande un usage raisonnable : délai avant chaque requête, au moins
// 3 caractères, et abandon de la requête précédente.
import { langue, t } from "./i18n";

const PHOTON = "https://photon.komoot.io/api/";
// Boîte englobante du Québec (ouest, sud, est, nord).
const BOITE = "-79.8,44.9,-57.0,62.7";
const DELAI_MS = 300;

export interface Resultat {
  libelle: string;
  detail: string;
  lngLat: [number, number];
  /** Emprise d'une ville ou d'une région : ouest, sud, est, nord. */
  emprise?: [number, number, number, number];
}

interface ProprietesPhoton {
  name?: string;
  housenumber?: string;
  street?: string;
  city?: string;
  district?: string;
  county?: string;
  state?: string;
  postcode?: string;
  extent?: [number, number, number, number]; // ouest, nord, est, sud
}

function versResultat(f: { geometry: { coordinates: [number, number] }; properties: ProprietesPhoton }): Resultat {
  const p = f.properties;
  const rue = [p.housenumber, p.street].filter(Boolean).join(" ");
  const libelle = p.name ?? (rue || p.city || "");
  const detail = [p.name && rue ? rue : null, p.district, p.city !== libelle ? p.city : null, p.postcode]
    .filter(Boolean).join(", ");
  const e = p.extent;
  return {
    libelle,
    detail,
    lngLat: f.geometry.coordinates,
    emprise: e ? [e[0], e[3], e[2], e[1]] : undefined,
  };
}

/** Les noms viennent d'OpenStreetMap : on les échappe avant de les insérer. */
function echapper(texte: string): string {
  return texte.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

let controleur: AbortController | null = null;

async function chercher(q: string): Promise<Resultat[]> {
  controleur?.abort();
  controleur = new AbortController();
  const url = `${PHOTON}?${new URLSearchParams({ q, limit: "6", lang: langue(), bbox: BOITE })}`;
  const r = await fetch(url, { signal: controleur.signal });
  if (!r.ok) throw new Error(`Photon ${r.status}`);
  const json = await r.json();
  return json.features.map(versResultat).filter((x: Resultat) => x.libelle);
}

/** Branche le champ de recherche ; aller(résultat) centre la carte. */
export function brancherRecherche(champ: HTMLInputElement, liste: HTMLElement, aller: (r: Resultat) => void): void {
  let minuterie: number | undefined;
  let resultats: Resultat[] = [];
  let actif = -1;

  const fermer = () => { liste.hidden = true; actif = -1; champ.setAttribute("aria-expanded", "false"); };
  const choisir = (r: Resultat) => { champ.value = r.libelle; fermer(); aller(r); };
  const dessiner = () => {
    liste.innerHTML = resultats.length
      ? resultats.map((r, i) => `<li role="option" data-i="${i}" aria-selected="${i === actif}">
          <strong>${echapper(r.libelle)}</strong>${r.detail ? `<br><span class="discret">${echapper(r.detail)}</span>` : ""}</li>`).join("")
      : `<li class="discret">${t("aucunResultat")}</li>`;
    liste.hidden = false;
    champ.setAttribute("aria-expanded", "true");
  };

  champ.addEventListener("input", () => {
    clearTimeout(minuterie);
    const q = champ.value.trim();
    if (q.length < 3) { fermer(); return; }
    minuterie = window.setTimeout(async () => {
      try {
        resultats = await chercher(q);
        actif = -1;
        dessiner();
      } catch (e) {
        if ((e as Error).name !== "AbortError") { resultats = []; dessiner(); }
      }
    }, DELAI_MS);
  });
  champ.addEventListener("keydown", (e) => {
    if (liste.hidden || !resultats.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      actif = (actif + (e.key === "ArrowDown" ? 1 : -1) + resultats.length) % resultats.length;
      dessiner();
    } else if (e.key === "Enter") {
      e.preventDefault();
      choisir(resultats[Math.max(actif, 0)]);
    } else if (e.key === "Escape") {
      fermer();
    }
  });
  liste.addEventListener("mousedown", (e) => {
    const li = (e.target as HTMLElement).closest("li[data-i]") as HTMLElement | null;
    if (li) { e.preventDefault(); choisir(resultats[Number(li.dataset.i)]); }
  });
  champ.addEventListener("blur", () => setTimeout(fermer, 150));
}
