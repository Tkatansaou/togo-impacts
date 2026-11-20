"""Rule-based extraction of flood impacts from French-language news text.

Transparent baseline, runs offline, and serves as a reference against which
LLM-based extraction can be validated. Each value keeps the text span it came from.
"""
from __future__ import annotations

import re
from typing import Optional

from .gazetteer import find_places
from .schema import ImpactRecord

NUMBER_WORDS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "cent": 100, "mille": 1000,
    "une dizaine": 10, "une vingtaine": 20, "une trentaine": 30, "une cinquantaine": 50,
    "une centaine": 100, "des centaines": 200, "un millier": 1000, "des milliers": 2000,
}

_WORD_ALT = "|".join(sorted((re.escape(w) for w in NUMBER_WORDS), key=len, reverse=True))
# "1 200", "1.200", "1200", "12 000", "3,5 millions" (decimal + scale)
NUM = rf"(?<![\w])(?P<num>\d{{1,3}}(?:[ \u00a0\u202f.]\d{{3}})+|\d+(?:,\d+)?(?:\s*(?:millions?|mille))?|{_WORD_ALT})"
GAP = r"(?:\s+(?:[\w'’\-]+\s+){0,3}?)"   # up to 3 filler words: "personnes", "au moins", ...

HAZARD_TERMS = {
    "flood": r"inond\w*|crue\w*|pluies? diluviennes?|débordement|montée des eaux|submersion",
    "drought": r"sécheresse\w*|déficit pluviométrique|pénurie d.eau|tarissement",
}

PATTERNS: dict[str, list[str]] = {
    "deaths": [rf"{NUM}{GAP}(?:morts?|décès|décédé(?:e)?s?|tué(?:e)?s?|victimes? mortelles?|pertes? en vies? humaines?)",
               r"(?:bilan|fait|faisant|causé)\s+(?:de\s+|d'au moins\s+|au moins\s+)?" + NUM + r"\s+morts?"],
    "injured": [rf"{NUM}{GAP}blessé(?:e)?s?"],
    "missing": [rf"{NUM}{GAP}disparu(?:e)?s?"],
    "affected": [rf"{NUM}{GAP}(?:sinistré(?:e)?s?|personnes? (?:affectées|touchées|impactées)|ménages? (?:sinistrés|touchés|affectés))"],
    "displaced": [rf"{NUM}{GAP}(?:déplacé(?:e)?s?|sans[\s\-]abri|personnes? relogées|évacué(?:e)?s?)"],
    "houses_destroyed": [rf"{NUM}{GAP}(?:maisons?|habitations?|cases?|logements?|bâtiments?)\s+(?:[\w'’]+\s+){{0,2}}?(?:détruit(?:e)?s?|effondré(?:e)?s?|écroulé(?:e)?s?|emporté(?:e)?s?)"],
    "houses_damaged": [rf"{NUM}{GAP}(?:maisons?|habitations?|cases?|logements?|bâtiments?)\s+(?:[\w'’]+\s+){{0,2}}?(?:endommagé(?:e)?s?|inondé(?:e)?s?|fissuré(?:e)?s?)"],
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in PATTERNS.items()}


def parse_number(raw: str) -> Optional[int]:
    s = raw.strip().lower()
    if s in NUMBER_WORDS:
        return NUMBER_WORDS[s]
    scale = 1
    if re.search(r"millions?$", s):
        scale, s = 1_000_000, re.sub(r"\s*millions?$", "", s)
    elif s.endswith("mille"):
        scale, s = 1000, s[:-5].strip()
    s = re.sub(r"[ \u00a0\u202f.]", "", s).replace(",", ".")
    try:
        return int(round(float(s) * scale))
    except ValueError:
        return None


def detect_hazard(text: str) -> Optional[str]:
    for hazard, pat in HAZARD_TERMS.items():
        if re.search(pat, text, re.IGNORECASE):
            return hazard
    return None


def extract_impacts(text: str) -> tuple[dict[str, int], list[str]]:
    """Return {impact_field: max value found} and the supporting text spans."""
    values: dict[str, int] = {}
    evidence: list[str] = []
    for fieldname, patterns in _COMPILED.items():
        for pat in patterns:
            for m in pat.finditer(text):
                n = parse_number(m.group("num"))
                if n is None:
                    continue
                # keep the largest figure: articles often repeat partial then total counts
                if n > values.get(fieldname, -1):
                    values[fieldname] = n
                evidence.append(f"{fieldname}: «{m.group(0).strip()}»")
    return values, evidence


def extract_record(text: str, *, doc_id: str | None = None, pub_date=None) -> Optional[ImpactRecord]:
    """Build one ImpactRecord from an article; None if no hazard term is present."""
    hazard = detect_hazard(text)
    if hazard is None:
        return None
    values, evidence = extract_impacts(text)
    places = find_places(text)
    admin1, admin2 = places[0] if places else (None, None)
    return ImpactRecord(
        source="news:rules", hazard=hazard, date=pub_date, admin1=admin1, admin2=admin2,
        doc_id=doc_id, language="fr", method="rules", evidence=evidence, **values,
    )
