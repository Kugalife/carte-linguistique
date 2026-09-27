// Panneau de détail : composition complète du territoire cliqué, sur les deux
// axes, avec population, non-réponse et source (PRD 6.3).
import { composition, nomPoste, type Fiche } from "./donnees";
import { nombre, pourcentage, t } from "./i18n";
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

export async function afficherDetail(racine: HTMLElement, id: string, secteur: string, v: Vue): Promise<void> {
  racine.hidden = false;
  racine.innerHTML = `<p class="discret">${t("chargement")}</p>`;
  const c = await composition(secteur);
  const fiche = id === c.secteur.id ? c.secteur : c.aires[id];
  if (!fiche) {
    racine.innerHTML = `<p class="discret">${t("nonDisponible")}</p>`;
    return;
  }
  const estAire = fiche.niveau === "CA.DA";
  const code = estAire ? id.replace(/^2021S0512/, "") : id.replace(/^2021S0507/, "");
  racine.innerHTML = `
    <button class="fermer" aria-label="${t("fermer")}">×</button>
    <h2>${estAire ? t("aire") : t("secteur")} ${code}</h2>
    <p class="discret">
      ${fiche.population != null ? `${nombre(fiche.population)} ${t("habitants")}` : ""}
      ${fiche.non_reponse_pct != null ? ` · ${t("nonReponse")} ${pourcentage(fiche.non_reponse_pct / 100)}` : ""}
    </p>
    <h3>${t("lm")}</h3>
    ${barres(fiche, "lm", v)}
    <h3>${t("plop")}</h3>
    ${barres(fiche, "plop", v)}
    <p class="discret">${t("reponsesUniques")}</p>`;
  racine.querySelector(".fermer")!.addEventListener("click", () => (racine.hidden = true));
}
