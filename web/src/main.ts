import {
  addProtocol, Map as Carte, NavigationControl, Popup, setWorkerUrl,
  type FilterSpecification, type MapGeoJSONFeature, type MapLayerMouseEvent,
} from "maplibre-gl";
// MapLibre cherche son worker à côté de son propre fichier, que Vite déplace :
// on fait regrouper le worker (et ses imports) par Vite, puis on donne son URL.
import urlWorker from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import {
  expressionRayures, expressionRemplissage, motifHachures, motifPoints, motifRayures, PREFIXE_RAYURES,
} from "./couleurs";
import { afficherDetail } from "./detail";
import { chargerPostes, chargerSources, nomPoste, URL_TUILES } from "./donnees";
import { choisirLangue, langue, nombre, nomNiveau, pourcentage, t, type Langue } from "./i18n";
import { dessinerLegende } from "./legende";
import { brancherRecherche } from "./recherche";
import { EGALITE, proprietes, reglages, type Vue } from "./reglages";
import "./style.css";

// Fond de carte OpenFreeMap : gratuit, sans clé (décision du 27 septembre).
const FOND = "https://tiles.openfreemap.org/styles/positron";

// Niveau affiché selon le zoom (PRD 6.3, décision 0006). Deux chemins : dans une
// RMR, municipalité → secteur → aire ; ailleurs, sans secteurs, municipalité →
// aire directement. Les aires hors secteur s'affichent donc dès le zoom 10.
interface Couche {
  id: string;
  source: string;         // couche des tuiles (06_exporter_carte.py)
  min: number;
  max: number;
  filtre?: FilterSpecification;
}
const COUCHES: Couche[] = [
  { id: "regions", source: "regions", min: 0, max: 6.5 },
  { id: "mrc", source: "mrc", min: 6.5, max: 8.5 },
  // Une municipalité découpée en arrondissements (Montréal) cède la place à
  // ceux-ci au même zoom.
  { id: "municipalites", source: "municipalites", min: 8.5, max: 10, filtre: ["!", ["has", "subdivise"]] },
  { id: "arrondissements", source: "arrondissements", min: 8.5, max: 10 },
  { id: "secteurs", source: "secteurs", min: 10, max: 12 },
  { id: "aires-hors-secteur", source: "aires", min: 10, max: 24, filtre: ["!", ["has", "ct"]] },
  { id: "aires", source: "aires", min: 12, max: 24, filtre: ["has", "ct"] },
];

/** Combine le filtre propre à une couche et un filtre de sous-couche. */
function et(c: Couche, f: FilterSpecification): FilterSpecification {
  return c.filtre ? (["all", c.filtre, f] as FilterSpecification) : f;
}

const vue: Vue = { carte: "lm", sansOfficielles: false, denominateur: "population" };

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

setWorkerUrl(urlWorker);

const protocole = new Protocol();
addProtocol("pmtiles", protocole.tile);

const carte = new Carte({
  container: "carte",
  style: FOND,
  center: [-72.6, 46.6],
  zoom: 6,
  minZoom: 3.5,
  maxZoom: 17,
  attributionControl: { compact: true },
  hash: true,
});
carte.addControl(new NavigationControl({ showCompass: false }), "top-right");

function premiereCoucheDeTexte(): string | undefined {
  return carte.getStyle().layers.find((l: { type: string }) => l.type === "symbol")?.id;
}

function ajouterCouches(): void {
  carte.addSource("atlas", {
    type: "vector",
    url: `pmtiles://${URL_TUILES}`,
    attribution: `© <a href="https://www.statcan.gc.ca/">Statistique Canada</a>, ${t("licence")} · `
      + `${t("attributionVille")}`,
  });
  carte.addImage("hachures", motifHachures("rgba(40,40,40,0.55)"));
  carte.addImage("points", motifPoints("rgba(40,40,40,0.6)"));

  // Les couleurs passent sous les noms de rues et de lieux du fond.
  const avant = premiereCoucheDeTexte();
  for (const c of COUCHES) {
    const base = { source: "atlas", "source-layer": c.source, minzoom: c.min, maxzoom: c.max } as const;
    carte.addLayer({
      id: `${c.id}-remplissage`, type: "fill", ...base, ...(c.filtre ? { filter: c.filtre } : {}),
      paint: { "fill-color": expressionRemplissage(vue), "fill-opacity": 0.88 },
    }, avant);
    carte.addLayer({
      id: `${c.id}-egalite`, type: "fill", ...base, filter: et(c, filtreEgalite()),
      paint: { "fill-pattern": expressionRayures(vue), "fill-opacity": 0.88 },
    }, avant);
    carte.addLayer({
      id: `${c.id}-faible`, type: "fill", ...base,
      filter: et(c, ["all", ["==", ["get", "fp"], true], ["==", ["get", "nd"], false]]),
      paint: { "fill-pattern": "hachures" },
    }, avant);
    carte.addLayer({
      id: `${c.id}-nd`, type: "fill", ...base, filter: et(c, ["==", ["get", "nd"], true]),
      paint: { "fill-pattern": "points" },
    }, avant);
    carte.addLayer({
      id: `${c.id}-contour`, type: "line", ...base, ...(c.filtre ? { filter: c.filtre } : {}),
      paint: {
        "line-color": "#ffffff",
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.3, 14, 0.8],
        "line-opacity": 0.8,
      },
    }, avant);
    carte.addLayer({
      id: `${c.id}-survol`, type: "line", ...base, filter: ["==", ["get", "id"], ""],
      paint: { "line-color": "#1a1a1a", "line-width": 2 },
    });
  }
}

function filtreEgalite(): FilterSpecification {
  return ["==", ["get", proprietes(vue).langue], EGALITE];
}

function appliquerVue(): void {
  for (const c of COUCHES) {
    if (!carte.getLayer(`${c.id}-remplissage`)) continue;
    carte.setPaintProperty(`${c.id}-remplissage`, "fill-color", expressionRemplissage(vue));
    carte.setPaintProperty(`${c.id}-egalite`, "fill-pattern", expressionRayures(vue));
    carte.setFilter(`${c.id}-egalite`, et(c, filtreEgalite()));
  }
  dessinerLegende($("#legende"), vue);
  $("#option-sans").hidden = vue.carte !== "lm";
  $("#option-denominateur").hidden = !(vue.carte === "lm" && vue.sansOfficielles);
}

// ---------------------------------------------------------------- info-bulle

const bulle = new Popup({ closeButton: false, closeOnClick: false, maxWidth: "280px", offset: 12 });

function texteBulle(f: MapGeoJSONFeature): string {
  const p = f.properties;
  const k = proprietes(vue);
  const niveau = NIVEAU_DE_COUCHE[f.sourceLayer ?? ""] ?? "CA.DA";
  const entete = `<strong>${p.nom ?? nomNiveau(niveau)}</strong>${p.nom ? `<br><span class="discret">${nomNiveau(niveau)}</span>` : ""}<br><span class="discret">${p.pop != null ? `${nombre(p.pop)} ${t("habitants")}` : ""}</span>`;
  if (p.nd) return `${entete}<br>${p.auto ? t("autochtoneNd") : t("nonDisponible")}`;
  const l = p[k.langue];
  if (l == null) return entete;
  if (l === EGALITE) {
    const pre = k.langue.replace(/_l$/, "");
    const noms = [p[`${pre}_l1`], p[`${pre}_l2`]].map((c: string) => nomPoste(c)).join(t("et"));
    const reste = p[`${pre}_n`] - 2;
    const plus = reste > 1 ? t("etAutres", { n: reste }) : reste === 1 ? t("etAutre") : "";
    return `${entete}<br>${t("egalite")} : ${noms}${plus}, <strong>${pourcentage(p[k.part])}</strong> (${nombre(p[k.effectif])} ${t("chacune")})`;
  }
  const avert = p.fp ? `<br><em class="discret">${t("faiblePop", { n: reglages.seuilFaiblePopulation })}</em>` : "";
  return `${entete}<br>${nomPoste(l)} : <strong>${pourcentage(p[k.part])}</strong> (${nombre(p[k.effectif])})${avert}`;
}

const NIVEAU_DE_COUCHE: Record<string, string> = {
  regions: "CA.ER", mrc: "CA.CD", municipalites: "CA.CSD", arrondissements: "CA.ARR",
  secteurs: "CA.CT", aires: "CA.DA",
};

let survole: string | null = null;
function survol(e: MapLayerMouseEvent): void {
  const f = e.features?.[0];
  if (!f) return;
  carte.getCanvas().style.cursor = "pointer";
  if (survole !== f.properties.id) {
    survole = f.properties.id;
    for (const c of COUCHES) carte.setFilter(`${c.id}-survol`, ["==", ["get", "id"], survole]);
  }
  bulle.setLngLat(e.lngLat).setHTML(texteBulle(f)).addTo(carte);
}
function sortie(): void {
  carte.getCanvas().style.cursor = "";
  survole = null;
  for (const c of COUCHES) carte.setFilter(`${c.id}-survol`, ["==", ["get", "id"], ""]);
  bulle.remove();
}

function clic(e: MapLayerMouseEvent): void {
  const f = e.features?.[0];
  if (!f) return;
  afficherDetail($("#detail"), f.properties.id as string, vue);
}

// ---------------------------------------------------------------- interface

function textes(): void {
  document.querySelectorAll<HTMLElement>("[data-t]").forEach((el) => {
    el.textContent = t(el.dataset.t as Parameters<typeof t>[0]);
  });
  $("#bouton-langue").textContent = langue() === "fr" ? "English" : "Français";
  $<HTMLInputElement>("#recherche").placeholder = t("rechercher");
}

async function sources(): Promise<void> {
  const liste = await chargerSources();
  const vus = new Set<string>();
  $("#sources-liste").innerHTML = liste
    .filter((s) => (vus.has(s.tableau) ? false : (vus.add(s.tableau), true)))
    .map((s) => `<li>${s.organisme}, ${s.source} — ${s.tableau} v${s.version}, ${s.publie_le ?? ""} <span class="discret">(${s.extrait_au.slice(0, 10)})</span></li>`)
    .join("") + `<li><a href="${liste[0]?.licence_url ?? "#"}">${t("licence")}</a></li>`;
}

function brancherInterface(): void {
  document.querySelectorAll<HTMLInputElement>('input[name="carte"]').forEach((r) =>
    r.addEventListener("change", () => { vue.carte = r.value as Vue["carte"]; appliquerVue(); }));
  $<HTMLInputElement>("#sans-officielles").addEventListener("change", (e) => {
    vue.sansOfficielles = (e.target as HTMLInputElement).checked; appliquerVue();
  });
  document.querySelectorAll<HTMLInputElement>('input[name="denominateur"]').forEach((r) =>
    r.addEventListener("change", () => { vue.denominateur = r.value as Vue["denominateur"]; appliquerVue(); }));
  // Une adresse mène au niveau de l'aire de diffusion ; une ville ou une région,
  // à son emprise.
  brancherRecherche($<HTMLInputElement>("#recherche"), $("#recherche-resultats"), (r) => {
    if (r.emprise) carte.fitBounds(r.emprise, { padding: 40, maxZoom: 14 });
    else carte.flyTo({ center: r.lngLat, zoom: 14.5 });
  });
  $("#bouton-langue").addEventListener("click", () => {
    choisirLangue((langue() === "fr" ? "en" : "fr") as Langue);
    textes(); appliquerVue(); sources();
    $("#detail").hidden = true;
  });
}

choisirLangue(langue());
textes();
brancherInterface();
await chargerPostes();
sources();
// Les rayures d'égalité sont dessinées à la demande, une image par paire de
// couleurs et par palier.
carte.on("styleimagemissing", (e) => {
  if (!e.id.startsWith(PREFIXE_RAYURES) || carte.hasImage(e.id)) return;
  const image = motifRayures(e.id);
  if (image) carte.addImage(e.id, image);
});

carte.on("load", () => {
  ajouterCouches();
  appliquerVue();
  for (const c of COUCHES) {
    carte.on("mousemove", `${c.id}-remplissage`, survol);
    carte.on("mouseleave", `${c.id}-remplissage`, sortie);
    carte.on("click", `${c.id}-remplissage`, clic);
  }
});
