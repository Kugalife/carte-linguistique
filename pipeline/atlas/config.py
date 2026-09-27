"""Chemins et réglages. Aucune valeur codée en dur ailleurs dans le pipeline."""

from __future__ import annotations

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SQL = RACINE / "pipeline" / "sql"
DATA = RACINE / "data"
BRUT = DATA / "raw"          # réponses brutes, telles que reçues
INTERIM = DATA / "interim"
DB_DEFAUT = DATA / "db" / "atlas.duckdb"


def chemin_db() -> Path:
    """Emplacement de la base. ATLAS_DB permet de pointer ailleurs (tests, essais)."""
    p = os.environ.get("ATLAS_DB")
    return Path(p) if p else DB_DEFAUT


def cle_censusmapper() -> str | None:
    """Clé CensusMapper, si elle est configurée.

    Le connecteur SDMX, source primaire, n'en a pas besoin ; seuls les
    recensements antérieurs à 2021 et les géométries CensusMapper l'exigent.
    """
    return os.environ.get("CENSUSMAPPER_API_KEY") or None


def charger_env() -> None:
    """Lit un fichier .env sommaire, sans dépendance externe."""
    f = RACINE / ".env"
    if not f.exists():
        return
    for ligne in f.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, val = ligne.partition("=")
        os.environ.setdefault(cle.strip(), val.strip())
