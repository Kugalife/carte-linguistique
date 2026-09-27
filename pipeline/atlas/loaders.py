"""Chargement : traduction d'une source vers le modèle générique.

Toute écriture passe par ici et porte un extraction_id : les observations
(colonne NOT NULL, donc la règle est tenue par le schéma), mais aussi les
territoires, la classification des langues et la correspondance des variables,
qui viennent également d'une source et changent d'un recensement à l'autre.
Voir docs/provenance.md.
"""

from __future__ import annotations

import duckdb

from . import db, provenance
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
    corr = dict(con.execute(
        "SELECT code_variable, langue_code FROM variable_source WHERE axe_code = ? AND jeu = ?",
        [axe_code, f"CP{annee}"],
    ).fetchall())
    if not corr:
        raise RuntimeError(f"aucune correspondance de variables pour {axe_code} : "
                           "charger_classifications() d'abord")

    reponse = connecteur.observations(
        niveau_code=niveau_code, dguids=dguids,
        caracteristiques=sorted(corr, key=int), annee=annee,
    )
    brutes = connecteur.vers_observations_brutes(reponse)
    # Une requête joker rapporte tous les postes du territoire : on ne garde que
    # ceux de l'axe demandé, et l'on en profite pour lire au passage la
    # population et les taux de non-réponse, qui sont dans la même réponse.
    _completer_depuis_reponse(con, reponse)

    # La date de diffusion est celle des postes de cet axe, non celle de la
    # première ligne de la réponse : une requête joker mêle plusieurs thèmes,
    # diffusés à des dates différentes.
    dates = connecteur.dates_diffusion(reponse, set(corr))
    notes = f"Axe {axe_code}, {len(dguids)} territoire(s), {annee}."
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

    racine = RACINE_AXE[axe_code]
    totaux = {o.territoire_source: o.valeur for o in brutes if o.code_variable == racine}

    lignes = []
    for o in brutes:
        if o.code_variable not in corr:
            continue
        territoire_id = o.territoire_source.replace("_", ".")
        if o.valeur is None:
            qualite = "supprime"
        elif o.drapeau:
            qualite = "arrondi"
        else:
            qualite = "ok"
        lignes.append((
            territoire_id, o.annee, axe_code, corr[o.code_variable],
            "T" if o.sexe == "1" else o.sexe,
            o.valeur, totaux.get(o.territoire_source), qualite, o.drapeau, ext,
        ))

    # Une observation n'est référencée par rien : elle peut, elle, être mise à
    # jour. Une réextraction rafraîchit donc la valeur et sa provenance.
    con.executemany(
        """INSERT INTO observation
           (territoire_id, annee, axe_code, langue_code, sexe, effectif,
            total_reference, qualite, drapeau_source, extraction_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (territoire_id, annee, axe_code, langue_code, sexe) DO UPDATE SET
             effectif = excluded.effectif,
             total_reference = excluded.total_reference,
             qualite = excluded.qualite,
             drapeau_source = excluded.drapeau_source,
             extraction_id = excluded.extraction_id""",
        lignes,
    )

    return len(lignes)


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


def charger_limites(
    con: duckdb.DuckDBPyConnection,
    connecteur: StatCanLimites,
    *,
    rmr_id: str,
    annee_limites: int = 2021,
) -> dict[str, int]:
    """Crée les secteurs et aires de diffusion d'une RMR et pose leurs géométries.

    La RMR doit déjà exister (charger_territoire), puisqu'elle est le parent des
    secteurs. Ses propres limites sont posées au passage.

    Les aires de diffusion sont rattachées à leur secteur par position : le
    fichier des aires ne porte ni le secteur ni la RMR (voir le connecteur). Une
    aire appartient au secteur qui contient un point intérieur de son polygone
    (ST_PointOnSurface, toujours dans le polygone, contrairement au centroïde).
    Les aires de diffusion s'emboîtent exactement dans les secteurs, donc chaque
    aire doit trouver un secteur et un seul : c'est vérifié par l'appelant.

    Les géométries sont stockées en WGS 84 (EPSG:4326), la projection des tuiles
    vectorielles. Le calcul de position se fait avant, dans la projection
    d'origine, en mètres.
    """
    db.charger_spatial(con)
    con.begin()   # tout ou rien : un échec ne laisse pas une RMR à moitié chargée
    code_rmr = con.execute(
        "SELECT code_local FROM territoire WHERE id = ?", [rmr_id]).fetchone()[0]
    f = {n: connecteur.fichier(n) for n in FICHIER_PAR_NIVEAU}

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _rmr AS
        -- Une RMR à cheval sur deux provinces (Ottawa-Gatineau) a une ligne par
        -- partie provinciale : on les réunit.
        SELECT any_value(DGUID) AS id, sum(LANDAREA) AS superficie,
               ST_Union_Agg(geom) AS geom
        FROM ST_Read('{f["CA.CMACA"].couche}') WHERE CMAUID = ?
        GROUP BY CMAUID""", [code_rmr])
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _ct AS
        SELECT DGUID AS id, CTUID AS code_local, LANDAREA AS superficie, PRUID, geom
        FROM ST_Read('{f["CA.CT"].couche}') WHERE CTUID LIKE ? || '%'""", [code_rmr])
    # Filtre par province d'abord : il réduit de 57 000 à quelques milliers les
    # aires à situer.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _da AS
        SELECT da.DGUID AS id, da.DAUID AS code_local, da.LANDAREA AS superficie,
               da.geom, ct.id AS parent_id
        FROM ST_Read('{f["CA.DA"].couche}') da
        JOIN _ct ct ON ST_Within(ST_PointOnSurface(da.geom), ct.geom)
        WHERE da.PRUID IN (SELECT DISTINCT PRUID FROM _ct)""")

    ext = {}
    for niveau, table in (("CA.CMACA", "_rmr"), ("CA.CT", "_ct"), ("CA.DA", "_da")):
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        ext[niveau] = provenance.enregistrer(
            con,
            source_code=connecteur.code_source,
            requete=f[niveau].url,
            reponse_sha256=f[niveau].sha256,
            nb_lignes=n,
            tableau_source=f[niveau].nom,
            version_source=str(annee_limites),
            notes=(f"Limites cartographiques, RMR {code_rmr}. Archive conservée sous "
                   f"data/raw/statcan_limites/{f[niveau].nom}.zip."),
            conserver_brut=False,
        )

    # Secteurs, puis aires : un parent doit exister avant son enfant.
    # DO NOTHING : un territoire déjà chargé (par 02_charger_secteur.py) garde sa
    # ligne ; seule sa géométrie est posée ci-dessous.
    con.execute("""
        INSERT INTO territoire
          (id, pays_code, niveau_code, code_local, nom, parent_id, annee_limites, extraction_id)
        SELECT id, 'CA', 'CA.CT', code_local, code_local, ?, ?, ?
        FROM _ct
        ON CONFLICT (id) DO NOTHING""", [rmr_id, annee_limites, ext["CA.CT"]])
    con.execute("""
        INSERT INTO territoire
          (id, pays_code, niveau_code, code_local, nom, parent_id, annee_limites, extraction_id)
        SELECT id, 'CA', 'CA.DA', code_local, code_local, parent_id, ?, ?
        FROM _da
        ON CONFLICT (id) DO NOTHING""", [annee_limites, ext["CA.DA"]])

    # superficie_km2 : colonne ordinaire, qu'un UPDATE peut poser même sur une
    # ligne référencée. La géométrie et sa provenance vont dans leur propre table.
    for niveau, table in (("CA.CMACA", "_rmr"), ("CA.CT", "_ct"), ("CA.DA", "_da")):
        con.execute(f"""
            UPDATE territoire t SET superficie_km2 = s.superficie
            FROM {table} s WHERE t.id = s.id""")
        con.execute(f"""
            INSERT OR REPLACE INTO territoire_geometrie (territoire_id, geometrie, extraction_id)
            -- ST_MakeValid : le fichier source contient des polygones invalides
            -- (secteur 4620732.04 et une de ses aires). La correction ne
            -- change pas la superficie.
            SELECT id, ST_AsWKB(ST_Transform(ST_MakeValid(geom), '{PROJECTION}', 'EPSG:4326',
                                             always_xy := true)), ?
            FROM {table}""", [ext[niveau]])

    con.commit()
    return {niveau: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for niveau, t in (("CA.CMACA", "_rmr"), ("CA.CT", "_ct"), ("CA.DA", "_da"))}
