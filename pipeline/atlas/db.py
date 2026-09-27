"""Connexion à la base et application du schéma."""

from __future__ import annotations

from pathlib import Path

import duckdb

from . import config


def ouvrir(chemin: Path | None = None, *, appliquer_schema: bool = True) -> duckdb.DuckDBPyConnection:
    """Ouvre la base et, par défaut, s'assure que le schéma et la référence y sont.

    Les scripts du schéma sont idempotents (CREATE TABLE IF NOT EXISTS,
    INSERT OR REPLACE) : les réappliquer à chaque ouverture est sans effet de
    bord et garantit qu'une base ancienne reçoit les tables ajoutées depuis.
    """
    chemin = chemin or config.chemin_db()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(chemin))
    if appliquer_schema:
        for fichier in sorted(config.SQL.glob("*.sql")):
            con.execute(fichier.read_text(encoding="utf-8"))
    return con


def inserer_par_profondeur(
    con: duckdb.DuckDBPyConnection,
    table: str,
    colonnes: list[str],
    lignes: list[tuple],
    *,
    index_profondeur: int,
    cle: str = "code",
) -> int:
    """Insère un arbre en respectant les clés étrangères auto-référencées.

    Deux limitations de DuckDB imposent cette forme :

      * les clés étrangères sont validées par rapport à l'état d'avant
        l'instruction et il n'existe pas de contrainte différée — un parent doit
        donc être inséré dans une instruction antérieure à celle de son enfant,
        d'où le passage profondeur par profondeur ;
      * une ligne référencée par une clé étrangère ne peut être ni supprimée ni
        mise à jour — d'où DO NOTHING plutôt qu'un upsert. Recharger une
        classification modifiée suppose de reconstruire la base.
    """
    placeholders = ", ".join("?" for _ in colonnes)
    sql = (f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({placeholders}) "
           f"ON CONFLICT ({cle}) DO NOTHING")
    total = 0
    for profondeur in sorted({ligne[index_profondeur] for ligne in lignes}):
        lot = [l for l in lignes if l[index_profondeur] == profondeur]
        con.executemany(sql, lot)
        total += len(lot)
    return total
