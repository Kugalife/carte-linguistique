"""Connecteur — Profil du recensement de Statistique Canada, service SDMX.

Source primaire des effectifs 2021. Aucune clé API.

Ce que l'exploration de la phase 0 a établi, et qui n'est documenté nulle part
de façon utilisable :

  * La clé de données compte CINQ positions — FREQ.REF_AREA.GENDER.CHARACTERISTIC
    .STATISTIC — alors que la définition de structure déclare TIME_PERIOD en
    position 2. Mettre l'année dans le chemin renvoie « NoRecordsFound ». L'année
    passe par startPeriod / endPeriod.
  * FREQ vaut 'A5' (quinquennal), pas 'A'. C'est la cause la plus probable d'un
    « NoRecordsFound » sur une clé par ailleurs correcte.
  * La version du dataflow n'est pas 1.0 mais 1.3 au moment de l'écriture. On la
    découvre à l'exécution : une version codée en dur casserait à la prochaine
    révision de Statistique Canada.
  * REF_AREA est le DGUID dont le point est remplacé par un souligné :
    2021S0507 4620001.00 → '2021S05074620001_00'.
  * La codelist CL_CHARACTERISTIC porte les liens parent-enfant et les libellés
    en français et en anglais : la hiérarchie des langues et l'interface bilingue
    viennent donc de la source, sans reconstruction.
  * CL_CHARACTERISTIC est commune à tous les dataflows (2631 postes) ; chaque
    dataflow n'en sert qu'une partie. Un code valide dans la codelist peut donc
    ne renvoyer aucune donnée pour un niveau géographique donné.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import requests

from .. import config
from . import ObservationBrute, PosteClassification

BASE = "https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest"
AGENCE = "STC_CP"
FREQ_RECENSEMENT = "A5"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# Dataflow par niveau géographique du modèle générique.
DATAFLOW_PAR_NIVEAU = {
    "CA.C": "DF_PR",
    "CA.PR": "DF_PR",
    "CA.ER": "DF_ER",
    "CA.CD": "DF_CD",
    "CA.CSD": "DF_CSD",
    "CA.CMACA": "DF_CMACA",
    "CA.ADA": "DF_ADA",
    "CA.CT": "DF_CT",
    "CA.DA": "DF_DA",
}

# Postes racines des axes, repérés en phase 0 (voir docs/sources-canada.md).
RACINE_AXE = {
    "CA.plop": "374",
    "CA.langue_maternelle": "379",
    "CA.langue_maison": "721",
}

CODE_SOURCE = "statcan_sdmx_cp"


@dataclass
class Reponse:
    """Réponse d'une requête, avec ses octets bruts pour l'empreinte de provenance."""

    lignes: list[dict]
    octets: bytes
    url: str
    version_dataflow: str
    publie_le: str | None


class StatCanSdmx:
    code_source = CODE_SOURCE

    def __init__(self, session: requests.Session | None = None, timeout: int = 120,
                 cache: bool = True):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "atlas-langues/0.1 (pipeline de recherche)"
        self.timeout = timeout
        self._versions: dict[str, str] = {}
        self._cache_actif = cache

    # -------------------------------------------------------------- transport

    def _cache_chemin(self, url: str) -> Path:
        return config.INTERIM / "sdmx" / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.xml"

    def _structure(self, url: str) -> bytes:
        """Récupère une réponse de structure, en cache sur disque.

        Les définitions de structure pèsent près de 700 Ko et sont demandées
        plusieurs fois par exécution (classification, puis géographies de chaque
        niveau). Les remettre en cache évite de solliciter inutilement le
        service ; le cache ne contient jamais de données d'observation, dont la
        provenance exige au contraire une requête tracée à chaque fois.
        """
        if not self._cache_actif:
            r = self.s.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.content
        chemin = self._cache_chemin(url)
        if chemin.exists():
            return chemin.read_bytes()
        r = self.s.get(url, timeout=self.timeout)
        r.raise_for_status()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(r.content)
        return r.content

    # ------------------------------------------------------------ structures

    def version_dataflow(self, dataflow: str) -> str:
        """Version courante du dataflow, lue dans la source plutôt que supposée."""
        if dataflow not in self._versions:
            url = f"{BASE}/dataflow/{AGENCE}/{dataflow}"
            contenu = self._structure(url).decode("utf-8", "replace")
            m = re.search(rf'<structure:Dataflow id="{dataflow}"[^>]*version="([^"]+)"', contenu)
            if not m:
                raise RuntimeError(f"version introuvable pour le dataflow {dataflow}")
            self._versions[dataflow] = m.group(1)
        return self._versions[dataflow]

    def classification(self, dataflow: str = "DF_CT") -> list[PosteClassification]:
        """Arbre complet des postes, bilingue, avec liens parent-enfant.

        On demande le dataflow avec ses références pour obtenir la codelist
        CL_CHARACTERISTIC dans la même réponse.
        """
        url = f"{BASE}/dataflow/{AGENCE}/{dataflow}?references=all"
        racine = ET.fromstring(self._structure(url))

        brut: dict[str, dict] = {}
        for cl in racine.iter():
            if not (cl.tag.endswith("Codelist") and cl.get("id") == "CL_CHARACTERISTIC"):
                continue
            for code in cl:
                if not code.tag.endswith("Code"):
                    continue
                noms: dict[str | None, str | None] = {}
                parent = None
                for enfant in code:
                    tag = enfant.tag.split("}")[-1]
                    if tag == "Name":
                        noms[enfant.get(XML_LANG)] = enfant.text
                    elif tag == "Parent":
                        for ref in enfant.iter():
                            if ref.tag.split("}")[-1] == "Ref":
                                parent = ref.get("id")
                brut[code.get("id")] = {
                    "fr": noms.get("fr") or noms.get("en"),
                    "en": noms.get("en"),
                    "parent": parent,
                }
            break

        if not brut:
            raise RuntimeError("CL_CHARACTERISTIC absente de la réponse")

        def profondeur(code: str, vus: frozenset[str] = frozenset()) -> int:
            # vus protège d'un cycle dans les métadonnées, qu'on préfère voir
            # comme une profondeur plafonnée plutôt que comme une récursion infinie.
            parent = brut[code]["parent"]
            if parent is None or parent not in brut or parent in vus:
                return 0
            return 1 + profondeur(parent, vus | {code})

        return [
            PosteClassification(
                code_source=code,
                nom_fr=v["fr"],
                nom_en=v["en"],
                parent_source=v["parent"],
                profondeur=profondeur(code),
            )
            for code, v in brut.items()
        ]

    # ----------------------------------------------------------------- données

    @staticmethod
    def ref_area(dguid: str) -> str:
        """DGUID → REF_AREA : le point devient un souligné."""
        return dguid.replace(".", "_")

    def observations(
        self,
        *,
        niveau_code: str,
        dguids: list[str],
        caracteristiques: list[str] | None = None,
        annee: int = 2021,
        sexe: str = "1",
        statistique: str = "1",
        seuil_joker: int = 100,
    ) -> Reponse:
        """Effectifs pour des territoires et, éventuellement, des postes donnés.

        sexe '1' = Total ; statistique '1' = Effectifs (l'autre valeur, '4',
        donne des taux que le pipeline recalcule lui-même à partir des effectifs).

        caracteristiques=None demande tous les postes du territoire. C'est aussi
        ce qui est fait au-delà de seuil_joker postes : mesuré sur un secteur de
        Montréal, énumérer les 331 postes de la langue maternelle prend 53 s
        contre 43 s pour le joker qui en rapporte 2631 — l'URL longue coûte plus
        au service que le volume de données. Une seule requête joker couvre en
        outre tous les axes à la fois, et le filtrage se fait localement.
        """
        dataflow = DATAFLOW_PAR_NIVEAU[niveau_code]
        version = self.version_dataflow(dataflow)

        joker = caracteristiques is None or len(caracteristiques) > seuil_joker
        # Ordre réel de la clé : FREQ.REF_AREA.GENDER.CHARACTERISTIC.STATISTIC
        cle = ".".join([
            FREQ_RECENSEMENT,
            "+".join(self.ref_area(d) for d in dguids),
            sexe,
            "" if joker else "+".join(caracteristiques),
            statistique,
        ])
        url = f"{BASE}/data/{AGENCE},{dataflow},{version}/{cle}"
        r = self.s.get(
            url,
            params={"startPeriod": annee, "endPeriod": annee},
            headers={"Accept": "application/vnd.sdmx.data+csv"},
            timeout=self.timeout,
        )
        if r.status_code == 404 and b"NoRecordsFound" in r.content:
            return Reponse([], r.content, r.url, version, None)
        r.raise_for_status()

        lignes = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        # publie_le n'est pas renseigné ici : RELEASE_DATE varie selon le thème
        # dans une même réponse (2022-02-09 pour la population, 2022-08-17 pour
        # la langue). Prendre la date de la première ligne venue attribuerait à
        # un axe la date de diffusion d'un autre. C'est à l'appelant, qui sait
        # quels postes il retient, de la déduire — voir dates_diffusion().
        return Reponse(lignes, r.content, r.url, version, None)

    @staticmethod
    def dates_diffusion(reponse: Reponse, caracteristiques: set[str]) -> list[str]:
        """Dates de diffusion distinctes des postes retenus, triées."""
        return sorted({
            l["RELEASE_DATE"] for l in reponse.lignes
            if l.get("CHARACTERISTIC") in caracteristiques and l.get("RELEASE_DATE")
        })

    @staticmethod
    def vers_observations_brutes(reponse: Reponse) -> list[ObservationBrute]:
        out = []
        for l in reponse.lignes:
            valeur = l.get("OBS_VALUE")
            out.append(
                ObservationBrute(
                    territoire_source=l["REF_AREA"],
                    code_variable=l["CHARACTERISTIC"],
                    valeur=float(valeur) if valeur not in (None, "") else None,
                    drapeau=l.get("FLAG") or None,
                    annee=int(l["TIME_PERIOD"]),
                    sexe=l.get("GENDER", "1"),
                    qualite_source=l.get("DATA_QUALITY_FLAG") or None,
                )
            )
        return out

    # ------------------------------------------------------------ géographies

    def geographies(self, dataflow: str) -> list[tuple[str, str]]:
        """(DGUID, nom) des territoires d'un dataflow, lus dans sa codelist géographique.

        Les noms viennent de la source : la carte n'invente aucun toponyme.
        """
        suffixe = dataflow.removeprefix("DF_")
        url = f"{BASE}/dataflow/{AGENCE}/{dataflow}?references=all"
        racine = ET.fromstring(self._structure(url))
        for cl in racine.iter():
            if cl.tag.endswith("Codelist") and cl.get("id") == f"CL_GEO_{suffixe}":
                out = []
                for code in cl:
                    if not code.tag.endswith("Code"):
                        continue
                    noms = {}
                    for enfant in code:
                        if enfant.tag.split("}")[-1] == "Name":
                            noms[enfant.get(XML_LANG)] = enfant.text
                    # Le REF_AREA emploie un souligné ; on rétablit le DGUID.
                    out.append((code.get("id").replace("_", "."), noms.get("fr") or noms.get("en")))
                return out
        raise RuntimeError(f"CL_GEO_{suffixe} absente pour {dataflow}")
