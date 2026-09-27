// Réglages éditoriaux de la carte : le même fichier que lit le pipeline.
// Voir docs/decisions/0004-regles-de-la-carte-par-defaut.md.
import brut from "../../config/carte.json";

export interface CouleurLangue {
  langue: string;
  couleur: string;
  nom: string;
  statut: string;
}

export const reglages = {
  paliers: brut.paliers_intensite.valeur as number[],
  seuilFaiblePopulation: brut.seuil_faible_population.valeur as number,
  couleurs: brut.palette.couleurs as CouleurLangue[],
  autres: brut.palette.autres_langues.couleur as string,
  plop: brut.palette.plop as Record<string, string>,
  sansOfficielles: brut.sans_francais_anglais.denominateurs,
};

export const EGALITE = "egalite";
export const AUTRES = "autres";

/** Les cartes, et la variante « sans français ni anglais » de la langue maternelle. */
export type Carte = "lm" | "plop";
export type Denominateur = "population" | "allophones";

export interface Vue {
  carte: Carte;
  sansOfficielles: boolean;
  denominateur: Denominateur;
}

/**
 * Préfixes des propriétés des tuiles (voir pipeline/atlas/indicateurs.py) :
 * langue dominante, clé de couleur et effectif d'un côté, part et palier de l'autre,
 * puisque les deux dénominateurs du mode sans officielles partagent la même langue.
 */
export function proprietes(v: Vue): { langue: string; cle: string; effectif: string; part: string; palier: string } {
  if (v.carte === "lm" && v.sansOfficielles) {
    const d = v.denominateur === "population" ? "nofp" : "noal";
    return { langue: "no_l", cle: "no_c", effectif: "no_e", part: `${d}_p`, palier: `${d}_i` };
  }
  const p = v.carte;
  return { langue: `${p}_l`, cle: `${p}_c`, effectif: `${p}_e`, part: `${p}_p`, palier: `${p}_i` };
}

export function paliersDe(v: Vue): number[] {
  if (v.carte === "lm" && v.sansOfficielles) return reglages.sansOfficielles[v.denominateur].paliers;
  return reglages.paliers;
}

/** Entrées de la légende pour une vue : clé de couleur → couleur de base. */
export function entrees(v: Vue): { cle: string; couleur: string; hachures?: [string, string] }[] {
  if (v.carte === "plop") {
    // « Français et anglais » est une réponse multiple : elle ne peut pas être
    // dominante (décision 0004) et n'a donc pas de ligne dans la matrice. Ses
    // hachures servent au panneau de détail.
    return Object.entries(reglages.plop)
      .filter(([k]) => !k.startsWith("_") && !k.endsWith("francais-et-anglais"))
      .map(([cle, val]) => {
        const m = val.match(/hachures (#\w+) \/ (#\w+)/);
        return m ? { cle, couleur: m[1], hachures: [m[1], m[2]] as [string, string] } : { cle, couleur: val };
      });
  }
  const officielles = new Set(["ca.langue.francais", "ca.langue.anglais"]);
  return [
    ...reglages.couleurs
      .filter((c) => !(v.sansOfficielles && officielles.has(c.langue)))
      .map((c) => ({ cle: c.langue, couleur: c.couleur })),
    { cle: AUTRES, couleur: reglages.autres },
  ];
}
