"""Connecteurs de sources.

Un connecteur traduit une source nationale vers le modèle générique. Ajouter un
pays consiste à ajouter un connecteur et des lignes de référence — jamais à
modifier le schéma (PRD section 4, roadmap phase 6).

Un connecteur expose :
    code_source   : la clé dans la table source
    classification() -> list[PosteClassification]
    observations(...) -> (list[ObservationBrute], octets_bruts, metadonnees)

et ne touche jamais la base directement : le chargement passe par les scripts,
de sorte que toute écriture soit accompagnée d'une extraction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PosteClassification:
    """Un poste de la classification d'une source (langue, famille, total, résiduel)."""

    code_source: str          # identifiant dans la source ('382', 'v_CA21_1183')
    nom_fr: str
    nom_en: str | None
    parent_source: str | None
    profondeur: int


@dataclass(frozen=True)
class ObservationBrute:
    """Une valeur lue dans une source, avant traduction vers le modèle."""

    territoire_source: str
    code_variable: str
    valeur: float | None
    drapeau: str | None
    annee: int
    sexe: str
    qualite_source: str | None = None
