"""Construction de la table des langues à partir de la classification d'une source.

Trois problèmes à résoudre ici :

1. **Un code interne stable.** Les identifiants de la source changent d'un
   recensement à l'autre : « Anglais » est la caractéristique 382 en 2021 et
   porte un autre numéro en 2016. Un code interne dérivé du libellé français
   survit à ces renumérotations, ce qui est la condition pour comparer des
   années (roadmap phase 3).

2. **La nature de chaque poste.** L'arbre mêle des totaux, des regroupements
   administratifs, des familles, des langues, des catégories résiduelles
   (« n.d.a. ») et des réponses multiples. La carte doit les traiter
   différemment : une réponse multiple n'est pas une langue et ne doit jamais
   être répartie silencieusement (PRD 6.6).

3. **Le regroupement pour la légende.** Il n'est pas déductible d'une
   profondeur fixe. La profondeur 4 donne 32 familles utilisables, mais
   « langues indo-européennes » y couvre à elle seule le français, l'italien,
   le russe, l'hindi et le grec — inexploitable comme entrée de légende. On
   part donc de la profondeur 4 puis on éclate une courte liste explicite de
   nœuds trop larges, jusqu'aux familles que le PRD nomme (langues slaves,
   langues indo-aryennes). C'est un choix éditorial, assumé comme tel, et à
   revalider en phase 1 contre les effectifs réels de Montréal.
"""

from __future__ import annotations

import re
import unicodedata

from .connectors import PosteClassification

# Nœuds à éclater en leurs enfants pour la légende : trop hétérogènes pour
# porter une seule couleur. Exprimés en codes internes, donc stables.
NOEUDS_ECLATES = {
    "langues-indo-europeennes",
    "langues-balto-slaves",
    "langues-indo-iraniennes",
}

PROFONDEUR_FAMILLE = 4  # sous « langues non officielles » / « langues autochtones »

# Correspondance ISO 639-3, amorcée pour les langues qui pèsent à Montréal et
# pour les langues autochtones du Québec. Les 331 postes ne sont pas tous
# mappables : une famille ou un résiduel (« langues chinoises, n.i.a. ») n'a pas
# de code ISO, et la colonne reste nulle — c'est l'état correct, pas un trou.
ISO639_3 = {
    "anglais": "eng", "francais": "fra",
    "arabe": "ara", "espagnol": "spa", "italien": "ita", "portugais": "por",
    "roumain": "ron", "grec": "ell", "russe": "rus", "ukrainien": "ukr",
    "polonais": "pol", "allemand": "deu", "neerlandais": "nld",
    "mandarin": "cmn", "cantonais": "yue", "vietnamien": "vie",
    "khmer-cambodgien": "khm", "lao": "lao", "thai": "tha",
    "tagalog-pilipino-filipino": "tgl", "japonais": "jpn", "coreen": "kor",
    "pendjabi-panjabi": "pan", "hindi": "hin", "ourdou": "urd",
    "gujarati": "guj", "bengali": "ben", "tamoul": "tam", "telougou": "tel",
    "malayalam": "mal", "marathe": "mar", "nepalais": "nep", "sinhala": "sin",
    "persan-farsi": "fas", "pachto": "pus", "kurde": "kur",
    "turc": "tur", "azerbaidjanais": "aze", "ouzbek": "uzb",
    "armenien": "hye", "georgien": "kat", "albanais": "sqi",
    "hebreu": "heb", "yiddish": "yid", "amharique": "amh", "somali": "som",
    "tigrigna": "tir", "haoussa": "hau", "yoruba": "yor", "igbo": "ibo",
    "swahili": "swa", "lingala": "lin", "kinyarwanda": "kin",
    "akan-twi": "aka", "wolof": "wol", "creole-haitien": "hat",
    "hongrois": "hun", "finnois": "fin", "estonien": "est",
    "tchetchene": "che", "mongol": "mon", "birman": "mya", "indonesien": "ind",
    # Langues autochtones présentes au Québec
    "atikamekw": "atj", "innu-montagnais": "moe", "naskapi": "nsk",
    "inuktitut": "iku", "mohawk": "moh", "anicinabemowin-algonquin": "alq",
    "mikmaq": "mic", "oji-cri": "ojs", "michif": "crg",
}


def slug(nom: str) -> str:
    """Code interne à partir d'un libellé français : sans accents, sans ponctuation.

    « Cri, n.d.a. » → 'cri-nda' ; « Pendjabi (panjabi) » → 'pendjabi-panjabi'.
    """
    s = unicodedata.normalize("NFKD", nom)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("'", "-").replace("’", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def _type_noeud(nom: str, a_des_enfants: bool, profondeur: int, sous_multiples: bool) -> str:
    """Nature d'un poste. Voir la colonne type_noeud dans 001_schema.sql.

    Les catégories qui ne sont pas des langues sont reconnues par leur libellé,
    pas par leur place dans l'arbre : la PLOP n'a pas de branche « Réponses
    multiples » sous laquelle les ranger, alors que « Français et anglais » y est
    tout autant une combinaison et « Ni français ni anglais » une absence de
    langue officielle. Les confondre avec des langues les ferait entrer dans le
    calcul de la langue dominante, ce que le PRD interdit (section 6.6).
    """
    if profondeur == 0:
        return "total"
    if nom in ("Réponses uniques", "Réponses multiples", "Langues officielles",
               "Langues non officielles"):
        return "regroupement"
    if re.match(r"^Ni\b", nom):
        return "aucune"
    if sous_multiples or re.search(r"\bmultiples?\b", nom, re.I) \
            or re.match(r"^(Français|Anglais)\b.*\bet\b", nom):
        return "multiple"
    if re.search(r"n\.d\.a\.|n\.i\.a\.", nom):
        return "residuel"
    return "famille" if a_des_enfants else "langue"


class ArbreClassification:
    """Sous-arbre d'une classification, prêt à charger dans la table langue."""

    def __init__(self, postes: list[PosteClassification], racine: str, classification_code: str):
        self.idx = {p.code_source: p for p in postes}
        if racine not in self.idx:
            raise KeyError(f"poste racine {racine} absent de la classification")
        self.racine = racine
        self.classification_code = classification_code

        self.enfants: dict[str | None, list[str]] = {}
        for p in postes:
            self.enfants.setdefault(p.parent_source, []).append(p.code_source)
        for v in self.enfants.values():
            v.sort(key=lambda c: int(c) if c.isdigit() else 0)

        self.membres = self._parcourir()

    def _parcourir(self) -> list[dict]:
        """Parcours en profondeur : l'ordre du parcours devient l'ordre d'affichage."""
        out: list[dict] = []

        def descendre(code: str, profondeur: int, sous_multiples: bool, chemin: list[str]) -> None:
            p = self.idx[code]
            nom = p.nom_fr or p.nom_en or code
            enfants = self.enfants.get(code, [])
            multiples = sous_multiples or nom == "Réponses multiples"
            out.append({
                "code_source": code,
                "nom_fr": nom,
                "nom_en": p.nom_en,
                "profondeur": profondeur,
                # sous_multiples, non multiples : le nœud « Réponses multiples »
                # est le regroupement, ce sont ses enfants qui sont des réponses
                # multiples.
                "type_noeud": _type_noeud(nom, bool(enfants), profondeur, sous_multiples),
                "chemin": chemin + [slug(nom)],
                "parent_source": p.parent_source if profondeur else None,
            })
            for e in enfants:
                descendre(e, profondeur + 1, multiples, chemin + [slug(nom)])

        descendre(self.racine, 0, False, [])
        return out

    def _codes_internes(self) -> dict[str, str]:
        """Attribue un code interne unique à chaque poste.

        Le libellé seul ne suffit pas : « Langues autochtones, n.d.a. » et
        d'autres résiduels se répètent. En cas de collision on préfixe par le
        slug du parent, ce qui reste stable d'un recensement à l'autre — au
        contraire d'un compteur, qui dépendrait de l'ordre de lecture.
        """
        vus: dict[str, str] = {}
        codes: dict[str, str] = {}
        prefixe = self.classification_code
        for m in self.membres:
            # Le libellé d'un total est une phrase entière (« Total - Langue
            # maternelle pour la population... ») : inexploitable comme code.
            base = "total" if m["type_noeud"] == "total" else m["chemin"][-1]
            candidat = base
            if candidat in vus:
                parent = m["chemin"][-2] if len(m["chemin"]) > 1 else "x"
                candidat = f"{parent}-{base}"
            n = 2
            while candidat in vus:
                candidat = f"{m['chemin'][-2] if len(m['chemin']) > 1 else 'x'}-{base}-{n}"
                n += 1
            vus[candidat] = m["code_source"]
            codes[m["code_source"]] = f"{prefixe}.{candidat}"
        return codes

    def familles_legende(self, codes: dict[str, str]) -> dict[str, str]:
        """famille_affichage de chaque poste : son ancêtre porteur de couleur.

        Profondeur 4 par défaut ; les nœuds de NOEUDS_ECLATES cèdent la place à
        leurs enfants. Les langues officielles sont leur propre famille : le
        français et l'anglais gardent chacun une couleur fixe.
        """
        par_source = {m["code_source"]: m for m in self.membres}

        # Les nœuds éclatés ne sont pas des familles ; leurs enfants le deviennent.
        eclates = {
            m["code_source"] for m in self.membres
            if codes[m["code_source"]].split(".")[-1] in NOEUDS_ECLATES
        }

        def est_famille(m: dict) -> bool:
            if m["code_source"] in eclates:
                return False
            if m["profondeur"] == PROFONDEUR_FAMILLE:
                return True
            # enfant direct d'un nœud éclaté : promu famille
            return m["parent_source"] in eclates

        familles = {m["code_source"] for m in self.membres if est_famille(m)}

        out: dict[str, str] = {}
        for m in self.membres:
            # Langues officielles et réponses multiples : leur propre entrée.
            if m["type_noeud"] in ("total", "regroupement"):
                continue
            if m["profondeur"] <= 3 and m["type_noeud"] in ("langue", "multiple", "aucune"):
                out[m["code_source"]] = codes[m["code_source"]]
                continue
            courant: str | None = m["code_source"]
            while courant is not None and courant not in familles:
                courant = par_source.get(courant, {}).get("parent_source")
            if courant is not None:
                out[m["code_source"]] = codes[courant]
        return out

    def lignes_langue(self, extraction_id: str | None = None) -> list[tuple]:
        """Lignes prêtes pour INSERT dans langue, ordonnées par profondeur croissante."""
        codes = self._codes_internes()
        familles = self.familles_legende(codes)
        lignes = []
        for ordre, m in enumerate(self.membres):
            interne = codes[m["code_source"]]
            feuille = interne.split(".")[-1]
            lignes.append((
                interne,
                self.classification_code,
                m["nom_fr"],
                m["nom_en"],
                codes[m["parent_source"]] if m["parent_source"] else None,
                m["profondeur"],
                m["type_noeud"],
                ISO639_3.get(feuille),
                None,                                   # glottocode : phase ultérieure
                familles.get(m["code_source"]),
                ordre,
                "CA" if feuille in ("anglais", "francais") and m["profondeur"] == 3 else None,
                extraction_id,
            ))
        return lignes

    def correspondance_variables(self) -> dict[str, str]:
        """code de variable de la source → code interne de langue."""
        return self._codes_internes()


COLONNES_LANGUE = [
    "code", "classification_code", "nom_fr", "nom_en", "parent_code", "profondeur",
    "type_noeud", "iso639_3", "glottocode", "famille_affichage", "ordre_affichage",
    "officielle_pays", "extraction_id",
]
