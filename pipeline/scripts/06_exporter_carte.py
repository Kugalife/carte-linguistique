#!/usr/bin/env python3
"""Phase 1 — fichiers de la carte : tuiles vectorielles et compositions.

Produit, sous web/public/donnees/ :

  <rmr>.pmtiles           tuiles vectorielles, trois couches : rmr, secteurs, aires ;
                          chaque entité porte les indicateurs de atlas.indicateurs
  composition/<ct>.json   composition linguistique complète d'un secteur et de
                          ses aires, lue par le panneau de détail au clic
  langues.json            noms bilingues, type et famille de chaque poste
  sources.json            provenance des chiffres affichés

    python pipeline/scripts/06_exporter_carte.py [code_rmr]

Exige tippecanoe (https://github.com/felt/tippecanoe).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config, db, indicateurs, loaders

SORTIE = config.RACINE / "web" / "public" / "donnees"
TRAVAIL = config.INTERIM / "carte"

# Zooms des tuiles. Les secteurs couvrent la vue d'ensemble, les aires le
# quartier ; le site choisit ensuite la couche affichée selon le zoom. Au-delà de
# ZOOM_MAX, MapLibre agrandit les tuiles du dernier niveau.
ZOOM_MIN, ZOOM_MAX = 8, 14
ZOOM_AIRES = 11

# Postes détaillés du panneau : les langues, résiduels et réponses multiples
# non nuls. Les familles et regroupements se recalculent à partir de l'arbre.
TYPES_DETAIL = ("langue", "residuel", "multiple", "aucune")


def ecrire_couche(con, chemin: Path, ids: list[str], props: dict[str, dict],
                  minzoom: int) -> int:
    """GeoJSON délimité par lignes, le format que tippecanoe lit en flux."""
    n = 0
    with chemin.open("w", encoding="utf-8") as f:
        for tid, geojson in con.execute("""
            SELECT territoire_id, ST_AsGeoJSON(ST_GeomFromWKB(geometrie))
            FROM territoire_geometrie WHERE territoire_id IN (SELECT unnest(?))""",
                [ids]).fetchall():
            f.write(json.dumps({
                "type": "Feature",
                "tippecanoe": {"minzoom": minzoom, "maxzoom": ZOOM_MAX},
                "properties": props.get(tid, {"id": tid}),
                "geometry": json.loads(geojson),
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


def compositions(con, rmr: str) -> int:
    """Un fichier par secteur : le secteur et ses aires, postes non nuls."""
    dossier = SORTIE / "composition"
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)

    detail: dict[str, dict] = {}
    for tid, axe, code, eff, total in con.execute("""
        SELECT o.territoire_id, o.axe_code, o.langue_code, o.effectif, o.total_reference
        FROM observation o JOIN langue l ON l.code = o.langue_code
        JOIN territoire t ON t.id = o.territoire_id
        WHERE (t.parent_id = ? OR t.parent_id IN
               (SELECT id FROM territoire WHERE parent_id = ?))
          AND l.type_noeud IN (SELECT unnest(?)) AND o.effectif > 0
        ORDER BY o.effectif DESC""", [rmr, rmr, list(TYPES_DETAIL)]).fetchall():
        axes = detail.setdefault(tid, {})
        cle = "lm" if axe == "CA.langue_maternelle" else "plop"
        bloc = axes.setdefault(cle, {"total": total, "postes": []})
        bloc["postes"].append([code, eff])

    infos = {r[0]: r[1:] for r in con.execute("""
        SELECT id, niveau_code, parent_id, population, tnr_questionnaire_abrege,
               superficie_km2
        FROM territoire WHERE parent_id = ? OR parent_id IN
              (SELECT id FROM territoire WHERE parent_id = ?)""", [rmr, rmr]).fetchall()}

    def fiche(tid: str) -> dict:
        niveau, _, pop, tnr, sup = infos[tid]
        return {"id": tid, "niveau": niveau, "population": pop,
                "non_reponse_pct": tnr, "superficie_km2": sup,
                "axes": detail.get(tid, {})}

    secteurs = [t for t, i in infos.items() if i[0] == "CA.CT"]
    for ct in secteurs:
        contenu = {"secteur": fiche(ct),
                   "aires": {t: fiche(t) for t, i in infos.items() if i[1] == ct}}
        code = ct.removeprefix("2021S0507")
        (dossier / f"{code}.json").write_text(
            json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(secteurs)


def langues(con) -> int:
    lignes = con.execute("""
        SELECT code, nom_fr, nom_en, type_noeud, parent_code, famille_affichage,
               ordre_affichage, iso639_3
        FROM langue ORDER BY classification_code, ordre_affichage""").fetchall()
    (SORTIE / "langues.json").write_text(json.dumps({
        code: {"fr": fr, "en": en, "type": typ, "parent": parent, "famille": fam,
               "ordre": ordre, "iso639_3": iso}
        for code, fr, en, typ, parent, fam, ordre, iso in lignes
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(lignes)


def sources(con, rmr: str) -> None:
    """Provenance affichée sur la carte : une ligne par source et tableau."""
    lignes = con.execute("""
        SELECT s.nom, s.organisme, s.licence, s.licence_url, e.tableau_source,
               e.version_source, max(e.publie_le), min(e.extrait_le), max(e.extrait_le),
               count(*)
        FROM extraction e JOIN source s ON s.code = e.source_code
        WHERE e.id IN (SELECT extraction_id FROM observation
                       UNION SELECT extraction_id FROM territoire_geometrie)
        GROUP BY ALL ORDER BY s.nom, e.tableau_source""").fetchall()
    (SORTIE / "sources.json").write_text(json.dumps([
        {"source": nom, "organisme": org, "licence": lic, "licence_url": url,
         "tableau": tab, "version": ver,
         "publie_le": pub.isoformat() if pub else None,
         "extrait_du": deb.isoformat(timespec="minutes"),
         "extrait_au": fin.isoformat(timespec="minutes"), "extractions": n}
        for nom, org, lic, url, tab, ver, pub, deb, fin, n in lignes
    ], ensure_ascii=False, indent=1), encoding="utf-8")


def main(*args: str) -> int:
    code_rmr = args[0] if args else "462"
    tippecanoe = shutil.which("tippecanoe")
    if not tippecanoe:
        print("tippecanoe introuvable : voir https://github.com/felt/tippecanoe")
        return 1

    con = db.ouvrir()
    db.charger_spatial(con)
    rmr = loaders.dguid("CA.CMACA", code_rmr)

    def ids(niveau: str) -> list[str]:
        return [r[0] for r in con.execute("""
            SELECT id FROM territoire WHERE niveau_code = ? AND (id = ? OR parent_id = ?
                OR parent_id IN (SELECT id FROM territoire WHERE parent_id = ?))""",
            [niveau, rmr, rmr, rmr]).fetchall()]

    secteurs, aires = ids("CA.CT"), ids("CA.DA")
    reglages = indicateurs.Reglages.lire()
    props = indicateurs.proprietes(con, secteurs + aires, reglages)

    TRAVAIL.mkdir(parents=True, exist_ok=True)
    SORTIE.mkdir(parents=True, exist_ok=True)
    couches = {
        "rmr": ecrire_couche(con, TRAVAIL / "rmr.geojsonl", [rmr],
                             {rmr: {"id": rmr}}, ZOOM_MIN),
        "secteurs": ecrire_couche(con, TRAVAIL / "secteurs.geojsonl", secteurs, props, ZOOM_MIN),
        "aires": ecrire_couche(con, TRAVAIL / "aires.geojsonl", aires, props, ZOOM_AIRES),
    }
    print("entités : " + ", ".join(f"{k} {v}" for k, v in couches.items()))

    pmtiles = SORTIE / f"rmr-{code_rmr}.pmtiles"
    commande = [
        tippecanoe, "-o", str(pmtiles), "--force",
        "-Z", str(ZOOM_MIN), "-z", str(ZOOM_MAX),
        # Aucune entité ne doit disparaître : une aire manquante serait un trou
        # dans la carte, pas une simplification.
        "--no-feature-limit", "--no-tile-size-limit",
        # Les aires voisines partagent leurs limites : les simplifier ensemble
        # évite les interstices et les chevauchements entre polygones.
        "--no-simplification-of-shared-nodes",
        "--name", f"Atlas des langues, RMR {code_rmr}",
        "--attribution", "Statistique Canada, Recensement de 2021",
        "--quiet",
    ]
    for couche in couches:
        commande += ["-L", json.dumps({"file": str(TRAVAIL / f"{couche}.geojsonl"),
                                       "layer": couche})]
    subprocess.run(commande, check=True)
    print(f"tuiles : {pmtiles.relative_to(config.RACINE)} "
          f"({pmtiles.stat().st_size / 1e6:.1f} Mo)")

    print(f"compositions : {compositions(con, rmr)} fichiers de secteur")
    print(f"langues : {langues(con)} postes")
    sources(con, rmr)
    print(f"sortie : {SORTIE.relative_to(config.RACINE)}/")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
