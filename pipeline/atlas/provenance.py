"""Journal de provenance.

Règle du projet : aucune observation n'entre dans la base sans extraction_id.
Une extraction enregistre la requête exacte, l'empreinte de la réponse brute et
la version du pipeline — de quoi rejouer et vérifier n'importe quel chiffre
affiché sur la carte. Voir docs/provenance.md.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import __version__, config


def empreinte(donnees: bytes | str) -> str:
    if isinstance(donnees, str):
        donnees = donnees.encode("utf-8")
    return hashlib.sha256(donnees).hexdigest()


def identifiant(source_code: str, requete: str, horodatage: datetime) -> str:
    """Identifiant lisible et stable : source, instant, empreinte de la requête.

    L'empreinte de la requête (et non un compteur) rend l'identifiant
    reproductible et permet de repérer deux extractions de la même requête.
    """
    return f"{source_code}:{horodatage:%Y%m%dT%H%M%SZ}:{empreinte(requete)[:12]}"


def enregistrer(
    con: duckdb.DuckDBPyConnection,
    *,
    source_code: str,
    requete: str,
    reponse: bytes | None = None,
    nb_lignes: int | None = None,
    tableau_source: str | None = None,
    version_source: str | None = None,
    publie_le: str | None = None,
    notes: str | None = None,
    conserver_brut: bool = True,
) -> str:
    """Crée une extraction et renvoie son identifiant.

    conserver_brut : écrit la réponse telle que reçue sous data/raw/, nommée par
    l'identifiant. Sans cela, l'empreinte ne serait vérifiable contre rien.
    """
    maintenant = datetime.now(timezone.utc)
    ext_id = identifiant(source_code, requete, maintenant)

    sha = empreinte(reponse) if reponse is not None else None
    if conserver_brut and reponse is not None:
        dossier = config.BRUT / source_code
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / f"{ext_id.replace(':', '_')}.bin").write_bytes(reponse)

    con.execute(
        """
        INSERT OR REPLACE INTO extraction
          (id, source_code, extrait_le, requete, reponse_sha256, nb_lignes,
           tableau_source, version_source, publie_le, outil_version, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [ext_id, source_code, maintenant.replace(tzinfo=None), requete, sha, nb_lignes,
         tableau_source, version_source, publie_le, __version__, notes],
    )
    return ext_id


def tracer(con: duckdb.DuckDBPyConnection, territoire_id: str, annee: int, axe_code: str) -> list[tuple]:
    """Remonte d'une valeur affichée à sa source. Sert de test de traçabilité."""
    return con.execute(
        """
        SELECT o.langue_code, o.effectif, o.qualite,
               s.nom, e.tableau_source, e.version_source, e.extrait_le, e.requete
        FROM observation o
        JOIN extraction e ON e.id = o.extraction_id
        JOIN source s ON s.code = e.source_code
        WHERE o.territoire_id = ? AND o.annee = ? AND o.axe_code = ?
        ORDER BY o.langue_code
        """,
        [territoire_id, annee, axe_code],
    ).fetchall()
