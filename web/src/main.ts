import {
  addProtocol, Map as Carte, NavigationControl, Popup, setWorkerUrl,
  type MapGeoJSONFeature, type MapLayerMouseEvent,
} from "maplibre-gl";
// MapLibre cherche son worker à côté de son propre fichier, que Vite déplace :
// on fait regrouper le worker (et ses imports) par Vite, puis on donne son URL.
import urlWorker from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { expressionRemplissage, motifHachures, motifPoints } from "./couleurs";
import { afficherDetail } from "./detail";
import { chargerPostes, chargerSources, nomPoste, URL_TUILES } from "./donnees";
import { choisirLangue, langue, nombre, pourcentage, t, type Langue } from "./i18n";
import { dessinerLegende } from "./legende";
import { EGALITE, proprietes, reglages, type Vue } from "./reglages";
import "./style.css";

// Fond de carte OpenFreeMap : gratuit, sans clé (décision du 27 septembre).
const FOND = "https://tiles.openfreemap.org/styles/positron";

// Bascule secteurs → aires de diffusion selon le zoom (PRD 6.3). Les tuiles
// portent les aires dès le zoom 11 ; on les affiche à partir de 12.
const ZOOM_AIRES = 12;

const vue: Vue = { carte: "lm", sansOfficielles: false, denominateur: "population" };

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

setWorkerUrl(urlWorker);

const protocole = new Protocol();
addProtocol("pmtiles", protocole.tile);

const carte = new Carte({
  container: "carte",
  style: FOND,
  center: [-73.65, 45.53],
  zoom: 9.6,
  minZoom: 8,
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
    attribution: `© <a href="https://www.statcan.gc.ca/">Statistique Canada</a>, ${t("licence")}`,
  });
  carte.addImage("hachures", motifHachures("rgba(40,40,40,0.55)"));
  carte.addImage("points", motifPoints("rgba(40,40,40,0.6)"));

  // Les couleurs passent sous les noms de rues et de lieux du fond.
  const avant = premiereCoucheDeTexte();
  for (const [couche, min, max] of [["secteurs", 0, ZOOM_AIRES], ["aires", ZOOM_AIRES, 24]] as const) {
    carte.addLayer({
      id: `${couche}-remplissage`, type: "fill", source: "atlas", "source-layer": couche,
      minzoom: min, maxzoom: max,
      paint: { "fill-color": expressionRemplissage(vue), "fill-opacity": 0.88 },
    }, avant);
    carte.addLayer({
      id: `${couche}-faible`, type: "fill", source: "atlas", "source-layer": couche,
      minzoom: min, maxzoom: max, filter: ["all", ["==", ["get", "fp"], true], ["==", ["get", "nd"], false]],
      paint: { "fill-pattern": "hachures" },
    }, avant);
    carte.addLayer({
      id: `${couche}-nd`, type: "fill", source: "atlas", "source-layer": couche,
      minzoom: min, maxzoom: max, filter: ["==", ["get", "nd"], true],
      paint: { "fill-pattern": "points" },
    }, avant);
    carte.addLayer({
      id: `${couche}-contour`, type: "line", source: "atlas", "source-layer": couche,
      minzoom: min, maxzoom: max,
      paint: {
        "line-color": "#ffffff",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.2, 14, 0.8],
        "line-opacity": 0.8,
      },
    }, avant);
    carte.addLayer({
      id: `${couche}-survol`, type: "line", source: "atlas", "source-layer": couche,
      minzoom: min, maxzoom: max, filter: ["==", ["get", "id"], ""],
      paint: { "line-color": "#1a1a1a", "line-width": 2 },
    });
  }
  carte.addLayer({
    id: "rmr-contour", type: "line", source: "atlas", "source-layer": "rmr",
    paint: { "line-color": "#555", "line-width": 1, "line-dasharray": [3, 2] },
  }, avant);
}

function appliquerVue(): void {
  for (const c of ["secteurs", "aires"]) {
    if (carte.getLayer(`${c}-remplissage`)) carte.setPaintProperty(`${c}-remplissage`, "fill-color", expressionRemplissage(vue));
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
  const niveau = f.sourceLayer === "aires" ? t("aire") : t("secteur");
  const entete = `<strong>${niveau}</strong><br><span class="discret">${p.pop != null ? `${nombre(p.pop)} ${t("habitants")}` : ""}</span>`;
  if (p.nd) return `${entete}<br>${t("nonDisponible")}`;
  const l = p[k.langue];
  if (l == null) return entete;
  if (l === EGALITE) return `${entete}<br>${t("egalite")}`;
  const avert = p.fp ? `<br><em class="discret">${t("faiblePop", { n: reglages.seuilFaiblePopulation })}</em>` : "";
  return `${entete}<br>${nomPoste(l)} : <strong>${pourcentage(p[k.part])}</strong> (${nombre(p[k.effectif])})${avert}`;
}

let survole: string | null = null;
function survol(e: MapLayerMouseEvent): void {
  const f = e.features?.[0];
  if (!f) return;
  carte.getCanvas().style.cursor = "pointer";
  if (survole !== f.properties.id) {
    survole = f.properties.id;
    for (const c of ["secteurs", "aires"]) carte.setFilter(`${c}-survol`, ["==", ["get", "id"], survole]);
  }
  bulle.setLngLat(e.lngLat).setHTML(texteBulle(f)).addTo(carte);
}
function sortie(): void {
  carte.getCanvas().style.cursor = "";
  survole = null;
  for (const c of ["secteurs", "aires"]) carte.setFilter(`${c}-survol`, ["==", ["get", "id"], ""]);
  bulle.remove();
}

function clic(e: MapLayerMouseEvent): void {
  const f = e.features?.[0];
  if (!f) return;
  const id = f.properties.id as string;
  const secteur = f.sourceLayer === "aires" ? (f.properties.ct as string) : id;
  afficherDetail($("#detail"), id, secteur, vue);
}

// ---------------------------------------------------------------- interface

function textes(): void {
  document.querySelectorAll<HTMLElement>("[data-t]").forEach((el) => {
    el.textContent = t(el.dataset.t as Parameters<typeof t>[0]);
  });
  $("#bouton-langue").textContent = langue() === "fr" ? "English" : "Français";
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
carte.on("load", () => {
  ajouterCouches();
  appliquerVue();
  for (const c of ["secteurs", "aires"]) {
    carte.on("mousemove", `${c}-remplissage`, survol);
    carte.on("mouseleave", `${c}-remplissage`, sortie);
    carte.on("click", `${c}-remplissage`, clic);
  }
});
