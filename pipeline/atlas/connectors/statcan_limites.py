"""Connecteur — Fichiers des limites cartographiques de Statistique Canada.

Géométries des territoires du recensement 2021. Aucune clé API, mais aucune API
non plus : ce sont des fichiers de formes (shapefile) nationaux, un par niveau.

Ce que la phase 1 a établi :

  * Version *cartographique* (lettre « b » : lda_000b21a_e) et non *numérique*
    (« a ») : la cartographique est découpée selon le littoral, la numérique
    s'étend sur le fleuve et les lacs.
  * Les fichiers sont nationaux ; il n'existe pas de découpage par province.
    Celui des aires de diffusion pèse 197 Mo compressé.
  * Projection EPSG:3347 (NAD83 / Statistique Canada Lambert), en mètres.
  * Le fichier des aires de diffusion ne dit pas à quel secteur de recensement
    ni à quelle RMR appartient une aire : ses attributs se limitent à DAUID,
    DGUID, LANDAREA et PRUID. Le rattachement se fait donc par position (voir
    loaders.charger_limites_province).
  * Tous les fichiers portent PRUID : une province se filtre directement. Une
    RMR à cheval sur deux provinces (Ottawa-Gatineau) a une ligne par partie.
  * GDAL lit le shapefile directement dans l'archive (/vsizip/) : rien à
    décompresser.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .. import config

BASE = ("https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/"
        "boundary-limites/files-fichiers")

# Fichier par niveau géographique du modèle générique, et colonnes
# d'identifiant court et de nom dans ses attributs (None : pas de nom).
# Tailles : 134 à 197 Mo chacun, sauf RMR et secteurs (13 Mo).
FICHIER_PAR_NIVEAU = {
    "CA.PR": ("lpr_000b21a_e", "PRUID", "PRFNAME"),
    "CA.ER": ("ler_000b21a_e", "ERUID", "ERNAME"),
    "CA.CD": ("lcd_000b21a_e", "CDUID", "CDNAME"),
    "CA.CSD": ("lcsd000b21a_e", "CSDUID", "CSDNAME"),
    "CA.CMACA": ("lcma000b21a_e", "CMAUID", "CMANAME"),
    "CA.CT": ("lct_000b21a_e", "CTUID", "CTNAME"),
    "CA.DA": ("lda_000b21a_e", "DAUID", None),
}

PROJECTION = "EPSG:3347"

# En dessous de ce débit, mesuré sur la fenêtre, la connexion est rouverte.
DEBIT_MIN = 200_000          # octets par seconde
FENETRE_DEBIT_S = 10
CODE_SOURCE = "statcan_limites"


@dataclass
class Fichier:
    """Un fichier de limites téléchargé, avec ce qu'il faut pour la provenance."""

    niveau_code: str
    nom: str
    url: str
    chemin: Path
    sha256: str
    colonne_code: str
    colonne_nom: str | None

    @property
    def couche(self) -> str:
        """Chemin GDAL du shapefile, lu dans l'archive sans la décompresser."""
        return f"/vsizip/{self.chemin}/{self.nom}.shp"


class StatCanLimites:
    code_source = CODE_SOURCE

    def __init__(self, session: requests.Session | None = None, timeout: int = 60,
                 tentatives: int = 50):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "atlas-langues/0.1 (pipeline de recherche)"
        self.timeout = timeout
        self.tentatives = tentatives

    def _telecharger(self, url: str, chemin: Path) -> None:
        """Téléchargement avec reprise.

        Le serveur de Statistique Canada laisse parfois une connexion en
        suspens ou la ralentit à quelques dizaines de Ko/s (observé : blocage à
        2 Mo sur 13, sans erreur), alors qu'une nouvelle connexion obtient
        plusieurs Mo/s. Une connexion bloquée ou trop lente est donc abandonnée
        et le transfert reprend là où il s'était arrêté (en-tête Range), au lieu
        de tout recommencer.
        """
        chemin.parent.mkdir(parents=True, exist_ok=True)
        partiel = chemin.with_suffix(".zip.partiel")
        attendu = None
        for _ in range(self.tentatives):
            deja = partiel.stat().st_size if partiel.exists() else 0
            entetes = {"Range": f"bytes={deja}-"} if deja else {}
            try:
                with self.s.get(url, stream=True, timeout=self.timeout,
                                headers=entetes) as r:
                    r.raise_for_status()
                    if deja and r.status_code != 206:
                        deja = 0          # le serveur ignore Range : on repart de zéro
                    if attendu is None:
                        attendu = deja + int(r.headers["Content-Length"])
                    with partiel.open("ab" if deja else "wb") as f:
                        debut, recu = time.monotonic(), 0
                        for bloc in r.iter_content(1 << 16):
                            f.write(bloc)
                            recu += len(bloc)
                            duree = time.monotonic() - debut
                            if duree > FENETRE_DEBIT_S:
                                if recu / duree < DEBIT_MIN:
                                    break  # connexion trop lente : on en rouvre une
                                debut, recu = time.monotonic(), 0
            except (requests.ConnectionError, requests.Timeout,
                    requests.exceptions.ChunkedEncodingError):
                continue
            if partiel.stat().st_size == attendu:
                # Renommer à la fin : un téléchargement interrompu ne passe
                # jamais pour un fichier complet.
                partiel.rename(chemin)
                return
        raise RuntimeError(f"téléchargement incomplet après {self.tentatives} tentatives : {url}")

    def fichier(self, niveau_code: str) -> Fichier:
        """Télécharge le fichier d'un niveau s'il n'est pas déjà là.

        L'archive est conservée telle que reçue sous data/raw/statcan_limites/ :
        c'est la réponse brute de la provenance. Contrairement aux observations,
        on ne la redemande pas à chaque exécution — 197 Mo pour un fichier publié
        une fois pour tout le recensement. L'empreinte, recalculée à chaque
        chargement, dit si le fichier a changé.
        """
        nom, colonne, colonne_nom = FICHIER_PAR_NIVEAU[niveau_code]
        url = f"{BASE}/{nom}.zip"
        chemin = config.BRUT / CODE_SOURCE / f"{nom}.zip"
        if not chemin.exists():
            self._telecharger(url, chemin)

        h = hashlib.sha256()
        with chemin.open("rb") as f:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        return Fichier(niveau_code, nom, url, chemin, h.hexdigest(), colonne, colonne_nom)
