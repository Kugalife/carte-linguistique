#!/usr/bin/env python3
"""Fichiers de la carte d'une province : tuiles vectorielles et compositions.

Produit, sous web/public/donnees/ :

  pr-<code>.pmtiles       tuiles vectorielles, une couche par niveau (COUCHES) ;
                          chaque entité porte les indicateurs de atlas.indicateurs
  composition/<xx>.json   composition linguistique complète de chaque territoire,
                          répartie en 256 fichiers selon une empreinte de son
                          identifiant (décision 0006), lue au clic
  langues.json            noms bilingues, type et famille de chaque poste
  sources.json            provenance des chiffres affichés

    python pipeline/scripts/06_exporter_carte.py [code_province]

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
from atlas.connectors.statcan_limites import StatCanLimites

SORTIE = config.RACINE / "web" / "public" / "donnees"
TRAVAIL = config.INTERIM / "carte"

# Couche de tuiles → (niveau, zoom minimal, zoom maximal des tuiles). Le site
# choisit ensuite, dans ces plages, le niveau affiché selon le zoom ; au-delà du
# zoom maximal, MapLibre agrandit les tuiles du dernier niveau. Les aires
# commencent tôt : hors des RMR, sans secteurs, elles succèdent directement aux
# municipalités.
#
# Plafond au zoom 12 : une tuile de zoom 12 a une précision d'environ 2,4 m,
# largement suffisante pour des limites d'aires. Au-delà, les grandes aires
# rurales du Nord se découpent en centaines de milliers de tuiles : mesuré, les
# zooms 13 et 14 pesaient les deux tiers d'un fichier de 75 Mo.
COUCHES = {
    "regions": ("CA.ER", 3, 7),
    "mrc": ("CA.CD", 5, 9),
    "municipalites": ("CA.CSD", 7, 11),
    # Découpage construit (07_charger_arrondissements.py) : remplace, au même
    # zoom, la municipalité qu'il subdivise (propriété « subdivise »).
    "arrondissements": ("CA.ARR", 7, 11),
    "secteurs": ("CA.CT", 9, 12),
    "aires": ("CA.DA", 9, 12),
}
ZOOM_MIN = min(z for _, z, _ in COUCHES.values())
ZOOM_MAX = max(z for _, _, z in COUCHES.values())

# Postes détaillés du panneau : les langues, résiduels et réponses multiples
# non nuls. Les familles et regroupements se recalculent à partir de l'arbre.
TYPES_DETAIL = ("langue", "residuel", "multiple", "aucune")
NB_FICHIERS = 256

# Types de subdivision qui désignent une communauté autochtone : réserve
# indienne, établissement indien, terres réservées cries, naskapies et inuites.
# Statistique Canada n'a pu dénombrer entièrement certaines d'entre elles
# (Kahnawake, Akwesasne, Doncaster…) : leurs données sont absentes, et la carte
# doit dire pourquoi plutôt qu'afficher un simple « non disponible ».
TYPES_AUTOCHTONES = ("IRI", "S-É", "TC", "TK", "TI")


def fichier_composition(territoire_id: str) -> str:
    """Nom du fichier de composition d'un territoire : FNV-1a 32 bits, modulo 256.

    Le site calcule la même empreinte (web/src/donnees.ts) : les deux doivent
    rester identiques.
    """
    h = 0x811C9DC5
    for octet in territoire_id.encode("utf-8"):
        h = ((h ^ octet) * 0x01000193) & 0xFFFFFFFF
    return f"{h % NB_FICHIERS:02x}"


def ecrire_couche(con, chemin: Path, ids: list[str], props: dict[str, dict],
                  minzoom: int, maxzoom: int) -> int:
    """GeoJSON délimité par lignes, le format que tippecanoe lit en flux."""
    n = 0
    with chemin.open("w", encoding="utf-8") as f:
        for tid, geojson in con.execute("""
            SELECT territoire_id, ST_AsGeoJSON(ST_GeomFromWKB(geometrie))
            FROM territoire_geometrie WHERE territoire_id IN (SELECT unnest(?))""",
                [ids]).fetchall():
            f.write(json.dumps({
                "type": "Feature",
                "tippecanoe": {"minzoom": minzoom, "maxzoom": maxzoom},
                "properties": props.get(tid, {"id": tid}),
                "geometry": json.loads(geojson),
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


def compositions(con, ids: list[str]) -> int:
    """Composition de chaque territoire, postes non nuls, en NB_FICHIERS fichiers."""
    # Écraser plutôt que supprimer le dossier : le serveur de développement de
    # Vite ne voit plus les fichiers d'un dossier supprimé puis recréé.
    dossier = SORTIE / "composition"
    dossier.mkdir(parents=True, exist_ok=True)

    fiches: dict[str, dict] = {
        tid: {"id": tid, "niveau": niv, "nom": nom, "population": pop,
              "non_reponse_pct": tnr, "superficie_km2": sup, "axes": {}}
        for tid, niv, nom, pop, tnr, sup in con.execute("""
            SELECT id, niveau_code, nom, population, tnr_questionnaire_abrege, superficie_km2
            FROM territoire WHERE id IN (SELECT unnest(?))""", [ids]).fetchall()
    }
    for tid, axe, code, eff, total in con.execute("""
        SELECT o.territoire_id, o.axe_code, o.langue_code, o.effectif, o.total_reference
        FROM observation o JOIN langue l ON l.code = o.langue_code
        WHERE o.territoire_id IN (SELECT unnest(?))
          AND l.type_noeud IN (SELECT unnest(?)) AND o.effectif > 0
        ORDER BY o.effectif DESC""", [ids, list(TYPES_DETAIL)]).fetchall():
        cle = "lm" if axe == "CA.langue_maternelle" else "plop"
        bloc = fiches[tid]["axes"].setdefault(cle, {"total": total, "postes": []})
        bloc["postes"].append([code, eff])

    lots: dict[str, dict] = {}
    for tid, fiche in fiches.items():
        lots.setdefault(fichier_composition(tid), {})[tid] = fiche
    for nom, contenu in lots.items():
        (dossier / f"{nom}.json").write_text(
            json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for perime in dossier.glob("*.json"):
        if perime.stem not in lots:
            perime.unlink()
    return len(lots)


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


def sources(con) -> None:
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
    code_pr = args[0] if args else "24"
    tippecanoe = shutil.which("tippecanoe")
    if not tippecanoe:
        print("tippecanoe introuvable : voir https://github.com/felt/tippecanoe")
        return 1

    con = db.ouvrir()
    db.charger_spatial(con)
    province = loaders.dguid("CA.PR", code_pr)

    def ids(niveau: str) -> list[str]:
        return [r[0] for r in con.execute("""
            WITH RECURSIVE d(id) AS (
                SELECT ? UNION ALL
                SELECT t.id FROM territoire t JOIN d ON t.parent_id = d.id)
            SELECT t.id FROM territoire t JOIN d USING (id) WHERE t.niveau_code = ?""",
            [province, niveau]).fetchall()]

    par_couche = {c: ids(niv) for c, (niv, _, _) in COUCHES.items()}
    tous = [i for liste in par_couche.values() for i in liste]
    reglages = indicateurs.Reglages.lire()
    props = indicateurs.proprietes(con, tous, reglages)

    # Nom des territoires qui en ont un (municipalités, MRC, régions) ; secteur
    # d'une aire, s'il existe : une aire hors secteur s'affiche plus tôt.
    for tid, nom, niveau in con.execute(
            "SELECT id, nom, niveau_code FROM territoire WHERE id IN (SELECT unnest(?))",
            [tous]).fetchall():
        if niveau in ("CA.ER", "CA.CD", "CA.CSD", "CA.ARR") and nom:
            props[tid]["nom"] = nom
    for (csd,) in con.execute("""
            SELECT DISTINCT parent_id FROM territoire WHERE niveau_code = 'CA.ARR'""").fetchall():
        if csd in props:
            props[csd]["subdivise"] = True
    # Communautés autochtones : la subdivision et ses aires.
    fichier_csd = StatCanLimites().fichier("CA.CSD")
    autochtones = {r[0] for r in con.execute(f"""
        SELECT DGUID FROM ST_Read('{fichier_csd.couche}')
        WHERE PRUID = ? AND CSDTYPE IN (SELECT unnest(?))""",
        [code_pr, list(TYPES_AUTOCHTONES)]).fetchall()}
    for tid, parent in con.execute(
            "SELECT id, parent_id FROM territoire WHERE id IN (SELECT unnest(?))", [tous]).fetchall():
        if tid in autochtones or parent in autochtones:
            props[tid]["auto"] = True

    for aire, secteur in con.execute("""
            SELECT i.territoire_id, i.englobant_id FROM territoire_inclusion i
            JOIN territoire e ON e.id = i.englobant_id WHERE e.niveau_code = 'CA.CT'""").fetchall():
        if aire in props:
            props[aire]["ct"] = secteur

    TRAVAIL.mkdir(parents=True, exist_ok=True)
    SORTIE.mkdir(parents=True, exist_ok=True)
    comptes = {
        c: ecrire_couche(con, TRAVAIL / f"{c}.geojsonl", par_couche[c], props, zmin, zmax)
        for c, (_, zmin, zmax) in COUCHES.items()
    }
    print("entités : " + ", ".join(f"{k} {v}" for k, v in comptes.items()))

    pmtiles = SORTIE / f"pr-{code_pr}.pmtiles"
    commande = [
        tippecanoe, "-o", str(pmtiles), "--force",
        "-Z", str(ZOOM_MIN), "-z", str(ZOOM_MAX),
        # Aucune entité ne doit disparaître : une aire manquante serait un trou
        # dans la carte, pas une simplification.
        "--no-feature-limit", "--no-tile-size-limit",
        # Les territoires voisins partagent leurs limites : les simplifier
        # ensemble évite les interstices et les chevauchements.
        "--no-simplification-of-shared-nodes",
        "--name", f"Atlas des langues, province {code_pr}",
        "--attribution", "Statistique Canada, Recensement de 2021 ; Ville de Montréal (arrondissements)",
        "--quiet",
    ]
    for couche in COUCHES:
        commande += ["-L", json.dumps({"file": str(TRAVAIL / f"{couche}.geojsonl"),
                                       "layer": couche})]
    subprocess.run(commande, check=True)
    print(f"tuiles : {pmtiles.relative_to(config.RACINE)} "
          f"({pmtiles.stat().st_size / 1e6:.1f} Mo)")

    # Anciennes tuiles de la phase 1 (RMR seule), remplacées par la province.
    for ancien in SORTIE.glob("rmr-*.pmtiles"):
        ancien.unlink()

    print(f"compositions : {len(tous)} territoires en {compositions(con, tous)} fichiers")
    print(f"langues : {langues(con)} postes")
    sources(con)
    print(f"sortie : {SORTIE.relative_to(config.RACINE)}/")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
