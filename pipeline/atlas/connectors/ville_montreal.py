"""Connecteur — données ouvertes de la Ville de Montréal (donnees.montreal.ca).

Limites des arrondissements et des villes liées de l'agglomération, en GeoJSON,
WGS 84. Licence CC BY 4.0. Aucune clé.

Ce que la phase 2 a établi :

  * Le serveur refuse une requête sans User-Agent explicite : curl, avec son
    User-Agent par défaut, reçoit « RBAC: access denied » (19 octets, code 200).
    Une requête qui s'identifie obtient le fichier.
  * Le lien de téléchargement redirige vers un stockage Google Cloud signé.
  * Le fichier distingue TYPE = 'Arrondissement' (19) et 'Ville liée' (15). Les
    villes liées sont déjà des subdivisions de recensement : seuls les
    arrondissements sont un découpage nouveau.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

CODE_SOURCE = "ville_montreal"
URL_LIMITES = (
    "https://donnees.montreal.ca/dataset/9797a946-9da8-41ec-8815-f6b276dec7e9/resource/"
    "e18bfd07-edc8-4ce8-8a5a-3b617662a794/download/limites-administratives-agglomeration.geojson"
)


@dataclass
class Limites:
    entites: list[dict]
    octets: bytes
    url: str


class VilleMontreal:
    code_source = CODE_SOURCE

    def __init__(self, session: requests.Session | None = None, timeout: int = 120):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "atlas-langues/0.1 (pipeline de recherche)"
        self.timeout = timeout

    def limites(self) -> Limites:
        r = self.s.get(URL_LIMITES, timeout=self.timeout)
        r.raise_for_status()
        if not r.content.lstrip().startswith(b"{"):
            raise RuntimeError(f"réponse inattendue de la Ville : {r.content[:60]!r}")
        return Limites(json.loads(r.content)["features"], r.content, URL_LIMITES)
