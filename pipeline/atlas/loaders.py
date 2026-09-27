"""Chargement : traduction d'une source vers le modèle générique.

Toute écriture passe par ici et porte un extraction_id : les observations
(colonne NOT NULL, donc la règle est tenue par le schéma), mais aussi les
territoires, la classification des langues et la correspondance des variables,
qui viennent également d'une source et changent d'un recensement à l'autre.
Voir docs/provenance.md.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import duckdb

from . import config, db, provenance
from .connectors.statcan_limites import FICHIER_PAR_NIVEAU, PROJECTION, StatCanLimites
from .connectors.statcan_sdmx import DATAFLOW_PAR_NIVEAU, RACINE_AXE, StatCanSdmx
from .languages import COLONNES_LANGUE, ArbreClassification

# DGUID : l'année et le schéma géographique sont en préfixe.
SCHEMA_DGUID = {"CA.PR": "A0002", "CA.CMACA": "S0503", "CA.CT": "S0507", "CA.DA": "S0512"}


def dguid(niveau_code: str, code_local: str, annee_limites: int = 2021) -> str:
    return f"{annee_limites}{SCHEMA_DGUID[niveau_code]}{code_local}"


def charger_classifications(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanSdmx,
    *,
    annee: int = 2021,
    axes: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Charge l'arbre des langues et la correspondance des variables.

    Renvoie, par axe, la correspondance code de variable → code interne de langue.
    """
    axes = axes or list(RACINE_AXE)
    postes = connecteur.classification("DF_CT")

    ext = provenance.enregistrer(
        con,
        source_code=connecteur.code_source,
        requete=f"dataflow/STC_CP/DF_CT?references=all (CL_CHARACTERISTIC, {len(postes)} postes)",
        nb_lignes=len(postes),
        tableau_source="CL_CHARACTERISTIC",
        version_source=connecteur.version_dataflow("DF_CT"),
        notes="Classification des langues, libellés bilingues et liens parent-enfant.",
        conserver_brut=False,
    )

    correspondances: dict[str, dict[str, str]] = {}
    deja_chargees: set[str] = set()
    for axe_code in axes:
        classification_code = con.execute(
            "SELECT classification_code FROM axe WHERE code = ?", [axe_code]
        ).fetchone()[0]
        arbre = ArbreClassification(postes, RACINE_AXE[axe_code], classification_code)
        lignes = arbre.lignes_langue(ext)

        # Deux axes peuvent partager une classification (langue maternelle et
        # langue parlée à la maison) : ne l'écrire qu'une fois.
        if classification_code not in deja_chargees:
            # profondeur en position 5 : l'arbre doit entrer par niveaux (cf. db.py)
            db.inserer_par_profondeur(con, "langue", COLONNES_LANGUE, lignes, index_profondeur=5)
            con.execute(
                "UPDATE classification SET nb_postes = ? WHERE code = ?",
                [len(lignes), classification_code],
            )
            deja_chargees.add(classification_code)

        corr = arbre.correspondance_variables()
        racine = RACINE_AXE[axe_code]
        con.executemany(
            """INSERT INTO variable_source
               (source_code, jeu, code_variable, axe_code, langue_code, est_total,
                extraction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_code, jeu, code_variable) DO NOTHING""",
            [(connecteur.code_source, f"CP{annee}", src, axe_code, interne,
              src == racine, ext)
             for src, interne in corr.items()],
        )
        correspondances[axe_code] = corr
    return correspondances


def charger_territoire(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanSdmx,
    *,
    niveau_code: str,
    dguid_cible: str,
    parent_id: str | None = None,
    annee_limites: int = 2021,
) -> str:
    """Crée ou met à jour un territoire, nom lu dans la source."""
    dataflow = DATAFLOW_PAR_NIVEAU[niveau_code]
    geos = dict(connecteur.geographies(dataflow))
    if dguid_cible not in geos:
        raise KeyError(f"{dguid_cible} absent de CL_GEO pour {dataflow}")

    ext = provenance.enregistrer(
        con,
        source_code=connecteur.code_source,
        requete=f"dataflow/STC_CP/{dataflow}?references=all (CL_GEO, {len(geos)} territoires)",
        nb_lignes=len(geos),
        tableau_source=f"CL_GEO_{dataflow.removeprefix('DF_')}",
        version_source=connecteur.version_dataflow(dataflow),
        notes="Nom et existence du territoire.",
        conserver_brut=False,
    )

    code_local = dguid_cible[len(f"{annee_limites}{SCHEMA_DGUID[niveau_code]}"):]
    # DO NOTHING : un territoire est référencé par ses enfants et par les
    # observations, et DuckDB interdit de mettre à jour une ligne référencée.
    con.execute(
        """INSERT INTO territoire
           (id, pays_code, niveau_code, code_local, nom, parent_id, annee_limites, extraction_id)
           VALUES (?, 'CA', ?, ?, ?, ?, ?, ?)
           ON CONFLICT (id) DO NOTHING""",
        [dguid_cible, niveau_code, code_local, geos[dguid_cible], parent_id, annee_limites, ext],
    )
    return dguid_cible


def _correspondance(con: duckdb.DuckDBPyConnection, axe_code: str, annee: int) -> dict[str, str]:
    """Code de variable de la source → code interne de langue, pour un axe."""
    corr = dict(con.execute(
        "SELECT code_variable, langue_code FROM variable_source WHERE axe_code = ? AND jeu = ?",
        [axe_code, f"CP{annee}"],
    ).fetchall())
    if not corr:
        raise RuntimeError(f"aucune correspondance de variables pour {axe_code} : "
                           "charger_classifications() d'abord")
    return corr


def charger_observations(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanSdmx,
    *,
    niveau_code: str,
    dguids: list[str],
    axe_code: str,
    annee: int = 2021,
) -> int:
    """Charge les effectifs d'un axe pour des territoires donnés.

    La qualité de chaque valeur est déduite ici et non à l'affichage : une valeur
    absente est 'supprime' et non zéro. Confondre les deux est l'erreur que la
    carte ne doit jamais commettre (PRD section 10).
    """
    corr = _correspondance(con, axe_code, annee)
    reponse = connecteur.observations(
        niveau_code=niveau_code, dguids=dguids,
        caracteristiques=sorted(corr, key=int), annee=annee,
    )
    return _enregistrer_reponse(con, connecteur, reponse, niveau_code=niveau_code,
                                nb_territoires=len(dguids), correspondances={axe_code: corr},
                                annee=annee)[axe_code]


def charger_observations_lot(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanSdmx,
    *,
    niveau_code: str,
    dguids: list[str],
    axes: list[str],
    annee: int = 2021,
) -> dict[str, int]:
    """Plusieurs territoires et plusieurs axes en une seule requête.

    Les postes des axes sont énumérés plutôt que demandés par joker. Sur un
    territoire isolé le joker est plus rapide (phase 0), mais il rapporte 2 631
    postes par territoire : mesuré sur 10 aires de diffusion, 22 s en joker
    contre 7 s en énumérant les 337 postes utiles. La liste des territoires doit
    tenir dans une URL : voir StatCanSdmx.lots().
    """
    corr = {axe: _correspondance(con, axe, annee) for axe in axes}
    codes = sorted(set().union(*corr.values()) | {CARACTERISTIQUE_POPULATION}, key=int)
    reponse = connecteur.observations(
        niveau_code=niveau_code, dguids=dguids, caracteristiques=codes, annee=annee,
        seuil_joker=len(codes),
    )
    return _enregistrer_reponse(con, connecteur, reponse, niveau_code=niveau_code,
                                nb_territoires=len(dguids), correspondances=corr, annee=annee)


def _enregistrer_reponse(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanSdmx,
    reponse,
    *,
    niveau_code: str,
    nb_territoires: int,
    correspondances: dict[str, dict[str, str]],
    annee: int,
) -> dict[str, int]:
    """Écrit une réponse : une extraction, puis les observations de chaque axe."""
    brutes = connecteur.vers_observations_brutes(reponse)
    # La réponse porte aussi la population et les taux de non-réponse : on les
    # lit au passage plutôt que de les redemander.
    _completer_depuis_reponse(con, reponse)

    # La date de diffusion est celle des postes des axes chargés, non celle de
    # la première ligne de la réponse : une requête peut mêler plusieurs thèmes,
    # diffusés à des dates différentes.
    tous = set().union(*correspondances.values())
    dates = connecteur.dates_diffusion(reponse, tous)
    notes = f"Axe(s) {', '.join(correspondances)}, {nb_territoires} territoire(s), {annee}."
    if len(dates) > 1:
        notes += f" Dates de diffusion multiples : {', '.join(dates)}."

    ext = provenance.enregistrer(
        con,
        source_code=connecteur.code_source,
        requete=reponse.url,
        reponse=reponse.octets,
        nb_lignes=len(brutes),
        tableau_source=DATAFLOW_PAR_NIVEAU[niveau_code],
        version_source=reponse.version_dataflow,
        publie_le=dates[-1] if dates else None,
        notes=notes,
    )

    resultat = {}
    for axe_code, corr in correspondances.items():
        racine = RACINE_AXE[axe_code]
        totaux = {o.territoire_source: o.valeur for o in brutes if o.code_variable == racine}
        lignes = []
        for o in brutes:
            if o.code_variable not in corr:
                continue
            if o.valeur is None:
                qualite = "supprime"
            elif o.drapeau:
                qualite = "arrondi"
            else:
                qualite = "ok"
            lignes.append((
                o.territoire_source.replace("_", "."), o.annee, axe_code, corr[o.code_variable],
                "T" if o.sexe == "1" else o.sexe,
                o.valeur, totaux.get(o.territoire_source), qualite, o.drapeau, ext,
            ))

        _inserer_observations(con, lignes)
        resultat[axe_code] = len(lignes)
    return resultat


COLONNES_OBSERVATION = {
    "territoire_id": "VARCHAR", "annee": "INTEGER", "axe_code": "VARCHAR",
    "langue_code": "VARCHAR", "sexe": "VARCHAR", "effectif": "DOUBLE",
    "total_reference": "DOUBLE", "qualite": "VARCHAR", "drapeau_source": "VARCHAR",
    "extraction_id": "VARCHAR",
}


def _inserer_observations(con: duckdb.DuckDBPyConnection, lignes: list[tuple]) -> None:
    """Insère des observations en bloc, par un CSV temporaire.

    executemany insère ligne par ligne : mesuré, 445 s pour les 67 000
    observations d'un lot de 200 aires de diffusion. Relire un CSV est
    l'insertion en bloc de DuckDB, sans dépendance supplémentaire.

    Une observation n'est référencée par rien : elle peut, elle, être mise à
    jour. Une réextraction rafraîchit donc la valeur et sa provenance.
    """
    if not lignes:
        return
    config.INTERIM.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", dir=config.INTERIM,
                                     newline="", encoding="utf-8", delete=False) as f:
        csv.writer(f).writerows(lignes)
        chemin = Path(f.name)
    try:
        colonnes = ", ".join(COLONNES_OBSERVATION)
        types = ", ".join(f"'{c}': '{t}'" for c, t in COLONNES_OBSERVATION.items())
        con.execute(f"""
            INSERT INTO observation ({colonnes})
            SELECT {colonnes} FROM read_csv(?, header = false, columns = {{{types}}})
            ON CONFLICT (territoire_id, annee, axe_code, langue_code, sexe) DO UPDATE SET
              effectif = excluded.effectif,
              total_reference = excluded.total_reference,
              qualite = excluded.qualite,
              drapeau_source = excluded.drapeau_source,
              extraction_id = excluded.extraction_id""", [str(chemin)])
    finally:
        chemin.unlink()


CARACTERISTIQUE_POPULATION = "1"


def _completer_depuis_reponse(con, reponse) -> None:
    """Population totale et taux de non-réponse, lus dans une réponse déjà obtenue.

    Ces valeurs accompagnent chaque ligne renvoyée par le service ; les demander
    dans une requête séparée serait un appel de plus pour une donnée déjà en main.
    """
    for l in reponse.lignes:
        if l.get("CHARACTERISTIC") != CARACTERISTIQUE_POPULATION:
            continue
        con.execute(
            """UPDATE territoire
               SET population = ?, tnr_questionnaire_abrege = ?, tnr_questionnaire_long = ?
               WHERE id = ?""",
            [
                int(float(l["OBS_VALUE"])) if l.get("OBS_VALUE") else None,
                float(l["TNR_SF"]) if l.get("TNR_SF") else None,
                float(l["TNR_LF"]) if l.get("TNR_LF") else None,
                l["REF_AREA"].replace("_", "."),
            ],
        )


# Chaîne administrative, du plus large au plus fin, puis chaîne métropolitaine.
# Voir docs/decisions/0006-deux-emboitements.md.
NIVEAUX_PROVINCE = ["CA.PR", "CA.ER", "CA.CD", "CA.CSD", "CA.CMACA", "CA.CT", "CA.DA"]
TABLE_TEMP = {n: "_" + n.split(".")[1].lower() for n in NIVEAUX_PROVINCE}


def charger_limites_province(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanLimites,
    *,
    code_province: str,
    annee_limites: int = 2021,
) -> dict[str, int]:
    """Crée les territoires d'une province, tous niveaux, et pose leurs géométries.

    Rattachements (décision 0006) :

      parent_id    province ← région économique ← division ← subdivision ← aire
                   province ← RMR ← secteur
      inclusion    aire ∈ secteur, subdivision ∈ RMR

    Par code quand le code le dit (une subdivision 2466023 est dans la division
    2466, un secteur 4620001.00 dans la RMR 462), par position sinon : un
    territoire appartient à celui qui contient un point intérieur de son polygone
    (ST_PointOnSurface, toujours dans le polygone, contrairement au centroïde).
    La position se calcule dans la projection d'origine, en mètres ; les
    géométries sont stockées en WGS 84, la projection des tuiles.
    """
    db.charger_spatial(con)
    f = {n: connecteur.fichier(n) for n in NIVEAUX_PROVINCE}

    con.begin()   # tout ou rien : un échec ne laisse pas une province à moitié chargée
    for niveau in NIVEAUX_PROVINCE:
        fi = f[niveau]
        nom = fi.colonne_nom or fi.colonne_code
        # Une RMR à cheval sur deux provinces a une ligne par partie : on ne
        # garde que celle de la province, sous l'identifiant de la RMR entière.
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE {TABLE_TEMP[niveau]} AS
            SELECT any_value(DGUID) AS id, {fi.colonne_code} AS code_local,
                   any_value({nom}) AS nom, sum(LANDAREA) AS superficie,
                   ST_Union_Agg(geom) AS geom,
                   CAST(NULL AS VARCHAR) AS parent_id
            FROM ST_Read('{fi.couche}') WHERE PRUID = ?
            GROUP BY {fi.colonne_code}""", [code_province])

    # --- parents : chaîne administrative
    con.execute("UPDATE _er SET parent_id = (SELECT id FROM _pr)")
    con.execute("UPDATE _cmaca SET parent_id = (SELECT id FROM _pr)")
    con.execute("""
        UPDATE _cd SET parent_id = er.id FROM _er er
        WHERE ST_Within(ST_PointOnSurface(_cd.geom), er.geom)""")
    con.execute("""
        UPDATE _csd SET parent_id = cd.id FROM _cd cd
        WHERE cd.code_local = left(_csd.code_local, 4)""")
    con.execute("""
        UPDATE _da SET parent_id = csd.id FROM _csd csd
        WHERE ST_Within(ST_PointOnSurface(_da.geom), csd.geom)""")
    con.execute("""
        UPDATE _ct SET parent_id = cma.id FROM _cmaca cma
        WHERE cma.code_local = left(_ct.code_local, 3)""")

    # --- inclusions : chaîne métropolitaine
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _inclusion AS
        SELECT da.id AS territoire_id, ct.id AS englobant_id, 'CA.CT' AS niveau
        FROM _da da JOIN _ct ct ON ST_Within(ST_PointOnSurface(da.geom), ct.geom)
        UNION ALL
        SELECT csd.id, cma.id, 'CA.CMACA'
        FROM _csd csd JOIN _cmaca cma ON ST_Within(ST_PointOnSurface(csd.geom), cma.geom)""")

    ext = {}
    for niveau in NIVEAUX_PROVINCE:
        n = con.execute(f"SELECT count(*) FROM {TABLE_TEMP[niveau]}").fetchone()[0]
        ext[niveau] = provenance.enregistrer(
            con,
            source_code=connecteur.code_source,
            requete=f[niveau].url,
            reponse_sha256=f[niveau].sha256,
            nb_lignes=n,
            tableau_source=f[niveau].nom,
            version_source=str(annee_limites),
            notes=(f"Limites cartographiques, province {code_province}. Archive conservée "
                   f"sous data/raw/statcan_limites/{f[niveau].nom}.zip."),
            conserver_brut=False,
        )

    # Dans l'ordre de NIVEAUX_PROVINCE : un parent existe avant son enfant.
    # DO NOTHING : un territoire déjà chargé garde sa ligne ; sa géométrie et sa
    # superficie sont reposées ci-dessous.
    for niveau in NIVEAUX_PROVINCE:
        con.execute(f"""
            INSERT INTO territoire
              (id, pays_code, niveau_code, code_local, nom, parent_id, annee_limites,
               superficie_km2, extraction_id)
            SELECT id, 'CA', ?, code_local, nom, parent_id, ?, superficie, ?
            FROM {TABLE_TEMP[niveau]}
            ON CONFLICT (id) DO NOTHING""", [niveau, annee_limites, ext[niveau]])
        # ST_MakeValid : les fichiers source contiennent des polygones invalides
        # (ex. secteur 4620732.04). La correction ne change pas la superficie.
        con.execute(f"""
            INSERT OR REPLACE INTO territoire_geometrie (territoire_id, geometrie, extraction_id)
            SELECT id, ST_AsWKB(ST_Transform(ST_MakeValid(geom), '{PROJECTION}', 'EPSG:4326',
                                             always_xy := true)), ?
            FROM {TABLE_TEMP[niveau]}""", [ext[niveau]])

    for niveau in ("CA.CT", "CA.CMACA"):
        con.execute("""
            INSERT OR REPLACE INTO territoire_inclusion (territoire_id, englobant_id, extraction_id)
            SELECT territoire_id, englobant_id, ? FROM _inclusion WHERE niveau = ?""",
            [ext[niveau], niveau])
    con.commit()

    return {n: con.execute(f"SELECT count(*) FROM {TABLE_TEMP[n]}").fetchone()[0]
            for n in NIVEAUX_PROVINCE}
