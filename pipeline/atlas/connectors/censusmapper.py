"""Connecteur — CensusMapper (paquet R cancensus).

Rôle dans le projet, après la validation de la phase 0 : **source secondaire**.
Le service SDMX de Statistique Canada couvre 2021 sans clé API et avec davantage
de métadonnées (voir docs/decisions/0003-sdmx-source-primaire.md). CensusMapper
garde deux usages qu'aucune autre source ne remplit aussi bien :

  1. les recensements **1996 à 2016**, que le service SDMX ne diffuse pas
     (roadmap phase 3) ;
  2. le **contrôle croisé** des valeurs 2021 contre la source officielle.

Ce que la phase 0 a établi sur cette API :

  * `GET /api/v1/list_datasets` répond **sans clé** : CA1996, CA01, CA06, CA11,
    CA16, CA21. La couverture historique annoncée par le PRD est donc confirmée.
  * `GET /api/v1/vector_info/{jeu}` répond **sans clé** et renvoie l'arbre complet
    des variables, imbriqué. Utile pour inventorier, mais moins riche que
    `CL_CHARACTERISTIC` du service SDMX : libellés en anglais seulement.
  * Les réponses sont **gzippées quelle que soit l'en-tête de négociation** : il
    faut décompresser (requests le fait, curl seulement avec --compressed).
  * `list_regions` n'existe pas à l'URL que documente `cancensus` ; la liste des
    territoires passe par `/data_sets/{jeu}/place_names.csv`.
  * Les **données** exigent une clé API.

  * Les numéros de vecteur suivent un pas de 3 (`v_CA21_1174`, `1177`, `1180`…) :
    chaque poste existe en Total / Hommes / Femmes. Le vecteur « Total » est le
    premier des trois.
  * Correspondance avec le service SDMX, vérifiée sur les deux axes : le pas de 3
    des vecteurs répond au pas de 1 des caractéristiques —
    `v_CA21_1159` → `374` (PLOP) et `v_CA21_1174` → `379` (langue maternelle).
    Le contrôle croisé s'appuie néanmoins sur les **libellés** et non sur cette
    arithmétique, qui n'est vérifiée que dans le bloc linguistique.
"""

from __future__ import annotations

import json

import requests

from . import PosteClassification

BASE = "https://censusmapper.ca/api/v1"
CODE_SOURCE = "censusmapper"

# Racines des axes dans la numérotation CensusMapper de 2021.
RACINE_AXE_CA21 = {
    "CA.plop": "v_CA21_1159",
    "CA.langue_maternelle": "v_CA21_1174",
    "CA.langue_maison": "v_CA21_2200",
}


class CleManquante(RuntimeError):
    """Levée quand une opération exige la clé API et qu'elle n'est pas configurée."""


class CensusMapper:
    code_source = CODE_SOURCE

    def __init__(self, cle: str | None = None, session: requests.Session | None = None,
                 timeout: int = 120):
        self.cle = cle
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "atlas-langues/0.1 (pipeline de recherche)"
        self.timeout = timeout

    # ------------------------------------------------- métadonnées (sans clé)

    def jeux(self) -> list[dict]:
        """Recensements disponibles. Aucune clé requise."""
        r = self.s.get(f"{BASE}/list_datasets", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def classification(self, jeu: str = "CA21") -> list[PosteClassification]:
        """Arbre des variables d'un recensement. Aucune clé requise.

        L'arbre est imbriqué : la profondeur vient de la structure, pas d'un
        champ. Les libellés sont en anglais uniquement — c'est pourquoi la table
        langue est construite depuis le service SDMX, qui les donne bilingues.
        """
        r = self.s.get(f"{BASE}/vector_info/{jeu}", timeout=self.timeout)
        r.raise_for_status()
        arbre = r.json()

        postes: list[PosteClassification] = []

        def descendre(noeud: dict, parent: str | None, profondeur: int) -> None:
            cles = noeud.get("key")
            code = (cles[0] if isinstance(cles, list) else cles) if cles else None
            nom = str(noeud.get("name") or "")
            if code:
                postes.append(PosteClassification(
                    code_source=code, nom_fr=nom, nom_en=nom,
                    parent_source=parent, profondeur=profondeur,
                ))
                parent, profondeur = code, profondeur + 1
            for enfant in noeud.get("children") or []:
                descendre(enfant, parent, profondeur)

        descendre(arbre, None, 0)
        return postes

    def territoires(self, jeu: str = "CA21") -> bytes:
        """CSV des territoires (nom, geo_uid, type, population). Aucune clé requise."""
        r = self.s.get(f"https://censusmapper.ca/data_sets/{jeu}/place_names.csv",
                       timeout=self.timeout)
        r.raise_for_status()
        return r.content

    # -------------------------------------------------------- données (clé requise)

    def observations(self, *, jeu: str, regions: dict[str, list[str]],
                     vecteurs: list[str], niveau: str) -> bytes:
        """Effectifs. **Exige la clé API.**

        regions : {type de région → codes}, par exemple {"CMA": ["46246"]}.
        niveau  : 'CT', 'DA', 'CSD'…
        """
        if not self.cle:
            raise CleManquante(
                "CENSUSMAPPER_API_KEY absente. Elle n'est requise que pour les "
                "données CensusMapper — les recensements 1996 à 2016 (phase 3) et "
                "le contrôle croisé. Les effectifs 2021 viennent du service SDMX, "
                "qui n'en demande pas. Créer une clé : "
                "https://censusmapper.ca/users/sign_up"
            )
        r = self.s.get(
            f"{BASE}/data.csv",
            params={
                "dataset": jeu,
                "regions": json.dumps(regions),
                "vectors": json.dumps(vecteurs),
                "level": niveau,
                "api_key": self.cle,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.content
