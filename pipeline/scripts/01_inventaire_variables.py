#!/usr/bin/env python3
"""Inventaire des variables linguistiques canadiennes (phase 0, tâche 4).

Interroge les deux sources et produit le tableau des axes disponibles, leurs
postes racines et la taille de leur classification. Écrit un rapport Markdown
sous docs/ si --ecrire est passé.

    python pipeline/scripts/01_inventaire_variables.py [--ecrire]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import config
from atlas.connectors.censusmapper import CensusMapper
from atlas.connectors.statcan_sdmx import StatCanSdmx

MOTIF_AXE = re.compile(r"^Total\s*-\s*(Langue|Première langue|Connaissance)", re.I)


def inventaire_sdmx(cx: StatCanSdmx) -> list[dict]:
    postes = cx.classification("DF_CT")
    idx = {p.code_source: p for p in postes}
    enfants: dict[str | None, list[str]] = {}
    for p in postes:
        enfants.setdefault(p.parent_source, []).append(p.code_source)

    def taille(code: str) -> int:
        return 1 + sum(taille(e) for e in enfants.get(code, []))

    racines = [p for p in postes if p.profondeur == 0 and MOTIF_AXE.match(p.nom_fr or "")]
    return [{"code": p.code_source, "nom": p.nom_fr, "postes": taille(p.code_source)}
            for p in sorted(racines, key=lambda p: int(p.code_source))]


def main(*args: str) -> int:
    config.charger_env()
    cx = StatCanSdmx()

    print("=== Service SDMX — axes linguistiques, recensement 2021 ===")
    axes = inventaire_sdmx(cx)
    for a in axes:
        print(f"  racine {a['code']:>5}  {a['postes']:>4} postes  {a['nom'][:80]}")

    print("\n=== CensusMapper — recensements disponibles ===")
    cm = CensusMapper(config.cle_censusmapper())
    jeux = [j for j in cm.jeux() if j["dataset"].startswith("CA") and "x" not in j["dataset"]]
    for j in jeux:
        print(f"  {j['dataset']:<8} {j['description']}")
    print(f"\n  clé API CensusMapper : {'configurée' if cm.cle else 'absente (non requise pour 2021)'}")

    if "--ecrire" in args:
        cible = Path(config.RACINE) / "docs" / "inventaire-variables.md"
        lignes = ["# Inventaire des variables linguistiques — Canada 2021", "",
                  "Produit par `pipeline/scripts/01_inventaire_variables.py`.", "",
                  "| Poste racine | Postes | Axe |", "|---|---|---|"]
        lignes += [f"| `{a['code']}` | {a['postes']} | {a['nom']} |" for a in axes]
        lignes += ["", "## Recensements disponibles via CensusMapper", "",
                   "| Jeu | Description |", "|---|---|"]
        lignes += [f"| `{j['dataset']}` | {j['description']} |" for j in jeux]
        cible.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"\nrapport écrit : {cible}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
