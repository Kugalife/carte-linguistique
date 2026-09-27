// Panneau de détail : composition complète du territoire cliqué, sur les deux
// axes, avec population, non-réponse et source (PRD 6.3).
import { composition, nomPoste, type Fiche } from "./donnees";
import { nombre, nomNiveau, pourcentage, t } from "./i18n";
import { entrees, type Vue } from "./reglages";

const NB_POSTES = 12;

function barres(fiche: Fiche, axe: "lm" | "plop", v: Vue): string {
  const bloc = fiche.axes[axe];
  if (!bloc || !bloc.total) return `<p class="discret">${t("nonDisponible")}</p>`;
  const couleurs = new Map(entrees({ ...v, carte: axe, sansOfficielles: false }).map((e) => [e.cle, e.couleur]));
  const visibles = bloc.postes.slice(0, NB_POSTES);
  const reste = bloc.postes.length - visibles.length;
  const lignes = visibles
    .map(([code, eff]) => {
      const part = eff / bloc.total;
      const couleur = couleurs.get(code) ?? "#8a8f98";
      return `<li>
        <span class="nom">${nomPoste(code)}</span>
        <span class="barre"><span style="width:${Math.max(part * 100, 0.5)}%;background:${couleur}"></span></span>
        <span class="valeur">${pourcentage(part)}<small>${nombre(eff)}</small></span>
      </li>`;
    })
    .join("");
  return `<ol class="barres">${lignes}</ol>${reste > 0 ? `<p class="discret">${t("autresPostes", { n: reste })}</p>` : ""}`;
}

export async function afficherDetail(racine: HTMLElement, id: string, v: Vue): Promise<void> {
  racine.hidden = false;
  racine.innerHTML = `<p class="discret">${t("chargement")}</p>`;
  const fiche = await composition(id);
  if (!fiche) {
    racine.innerHTML = `<p class="discret">${t("nonDisponible")}</p>`;
    return;
  }
  const titre = fiche.nom && fiche.niveau !== "CA.CT" && fiche.niveau !== "CA.DA"
    ? fiche.nom : fiche.id.replace(/^2021S05(07|12)/, "");
  racine.innerHTML = `
    <button class="fermer" aria-label="${t("fermer")}">×</button>
    <p class="discret niveau">${nomNiveau(fiche.niveau)}</p>
    <h2>${titre}</h2>
    <p class="discret">
      ${fiche.population != null ? `${nombre(fiche.population)} ${t("habitants")}` : ""}
      ${fiche.non_reponse_pct != null ? ` · ${t("nonReponse")} ${pourcentage(fiche.non_reponse_pct / 100)}` : ""}
    </p>
    <h3>${t("lm")}</h3>
    ${barres(fiche, "lm", v)}
    <h3>${t("plop")}</h3>
    ${barres(fiche, "plop", v)}
    <p class="discret">${t("reponsesUniques")}</p>
    ${fiche.niveau === "CA.ARR" ? `<p class="discret">${t("noteArrondissement")}</p>` : ""}`;
  racine.querySelector(".fermer")!.addEventListener("click", () => (racine.hidden = true));
}
