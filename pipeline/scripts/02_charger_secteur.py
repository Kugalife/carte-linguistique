#!/usr/bin/env python3
"""Critère de fin de la phase 0.

Récupère les données d'un secteur de recensement, les charge dans la base selon
le schéma générique, avec provenance, puis vérifie la cohérence et remonte
chaque valeur jusqu'à sa source.

    python pipeline/scripts/02_charger_secteur.py [code_secteur] [--recreer]

Par défaut : 4620001.00, dans la RMR de Montréal.
--recreer : repart d'une base vide. C'est la façon de prendre en compte une
modification des données de référence ou de la classification, DuckDB
n'autorisant pas la mise à jour d'une ligne référencée (voir 002_reference_canada.sql).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, loaders, provenance
from atlas.connectors.statcan_sdmx import StatCanSdmx

AXES = ["CA.langue_maternelle", "CA.plop"]


def main(*args: str) -> int:
    recreer = "--recreer" in args
    positionnels = [a for a in args if not a.startswith("--")]
    code_secteur = positionnels[0] if positionnels else "4620001.00"

    config.charger_env()
    if recreer and config.chemin_db().exists():
        config.chemin_db().unlink()
        print("base supprimée, reconstruction")
    con = db.ouvrir()
    cx = StatCanSdmx()

    print(f"base : {config.chemin_db()}")
    print(f"secteur : {code_secteur}\n")

    # 1. Classifications et correspondance des variables.
    #    Les trois axes canadiens sont catalogués ; seuls AXES sont chargés.
    loaders.charger_classifications(con, cx)
    n_langues = con.execute("SELECT count(*) FROM langue").fetchone()[0]
    n_var = con.execute("SELECT count(*) FROM variable_source").fetchone()[0]
    print(f"classifications : {n_langues} postes, {n_var} correspondances de variables")

    # 2. Hiérarchie des territoires, du haut vers le bas : un parent doit exister
    #    avant son enfant (clé étrangère auto-référencée).
    pr = loaders.charger_territoire(
        con, cx, niveau_code="CA.PR", dguid_cible=loaders.dguid("CA.PR", "24"))
    rmr = loaders.charger_territoire(
        con, cx, niveau_code="CA.CMACA", dguid_cible=loaders.dguid("CA.CMACA", "462"),
        parent_id=pr)
    ct = loaders.charger_territoire(
        con, cx, niveau_code="CA.CT", dguid_cible=loaders.dguid("CA.CT", code_secteur),
        parent_id=rmr)
    for r in con.execute("""
        SELECT t.id, n.nom_fr, t.nom, t.parent_id FROM territoire t
        JOIN niveau_geo n ON n.code = t.niveau_code ORDER BY n.rang""").fetchall():
        print(f"  {r[1]:<40} {r[2]:<12} {r[0]}")

    # 3. Observations.
    print()
    for axe in AXES:
        n = loaders.charger_observations(
            con, cx, niveau_code="CA.CT", dguids=[ct], axe_code=axe)
        print(f"observations {axe:<24} {n}")

    # 4. Cohérence : la somme des postes d'un niveau doit redonner son parent.
    print("\n--- cohérence ---")
    ok = True
    for axe in AXES:
        ecart = con.execute("""
            SELECT o.total_reference,
                   sum(CASE WHEN l.profondeur = 1 THEN o.effectif END)
            FROM observation o JOIN langue l ON l.code = o.langue_code
            WHERE o.territoire_id = ? AND o.axe_code = ? AND l.profondeur > 0
            GROUP BY o.total_reference""", [ct, axe]).fetchone()
        total, somme = ecart
        conforme = somme is not None and abs(total - somme) < 0.5
        ok &= conforme
        print(f"  {axe:<24} total={total:>9,.0f}  somme niveau 1={somme:>9,.0f}  "
              f"{'conforme' if conforme else 'ÉCART'}")

    pop, tnr = con.execute(
        "SELECT population, tnr_questionnaire_abrege FROM territoire WHERE id = ?", [ct]).fetchone()
    univers = con.execute(
        "SELECT total_reference FROM observation WHERE territoire_id = ? AND axe_code = ? LIMIT 1",
        [ct, AXES[0]]).fetchone()[0]
    print(f"  population {pop:,} ; univers linguistique {univers:,.0f} "
          f"(écart {pop - univers:,.0f} = résidents des établissements institutionnels)")
    print(f"  taux de non-réponse (questionnaire abrégé) : {tnr} %")

    # 5. Traçabilité : toute valeur affichée doit remonter à sa source.
    print("\n--- provenance (extrait) ---")
    for r in provenance.tracer(con, ct, 2021, "CA.plop"):
        print(f"  {r[0]:<34} {r[1]:>8,.0f}  {r[2]:<9} {r[4]} v{r[5]}  extrait {r[6]:%Y-%m-%d %H:%M}")
    orphelines = con.execute(
        "SELECT count(*) FROM observation WHERE extraction_id IS NULL").fetchone()[0]
    print(f"  observations sans provenance : {orphelines}")

    # 6. Composition linguistique, pour montrer que le modèle répond à la question.
    print("\n--- langue maternelle : postes non nuls, du plus grand au plus petit ---")
    for r in con.execute("""
        SELECT l.nom_fr, o.effectif, o.effectif / o.total_reference * 100, l.type_noeud
        FROM observation o JOIN langue l ON l.code = o.langue_code
        WHERE o.territoire_id = ? AND o.axe_code = ?
          AND l.type_noeud IN ('langue', 'multiple', 'residuel')
          AND o.effectif > 0
        ORDER BY o.effectif DESC LIMIT 12""", [ct, "CA.langue_maternelle"]).fetchall():
        print(f"  {r[0][:44]:<46} {r[1]:>7,.0f}  {r[2]:5.1f} %  [{r[3]}]")

    con.close()
    print(f"\n{'phase 0 : critère de fin satisfait' if ok and not orphelines else 'ÉCHEC des vérifications'}")
    return 0 if (ok and not orphelines) else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
