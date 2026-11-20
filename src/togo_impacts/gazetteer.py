"""Gazetteer of Togo's administrative units (5 regions, 39 prefectures).

Maps prefecture names and their main towns to (admin1, admin2) so that
places mentioned in French-language news can be placed in a common
spatial framework (compatible with GADM level-2 names after normalisation).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# region -> prefectures
REGIONS: dict[str, list[str]] = {
    "Maritime": ["Golfe", "Agoè-Nyivé", "Lacs", "Bas-Mono", "Vo", "Yoto", "Zio", "Avé"],
    "Plateaux": ["Ogou", "Anié", "Est-Mono", "Akébou", "Wawa", "Amou", "Danyi",
                 "Kloto", "Kpélé", "Agou", "Haho", "Moyen-Mono"],
    "Centrale": ["Tchaoudjo", "Tchamba", "Sotouboua", "Blitta", "Mô"],
    "Kara": ["Kozah", "Binah", "Doufelgou", "Kéran", "Dankpen", "Bassar", "Assoli"],
    "Savanes": ["Tône", "Cinkassé", "Kpendjal", "Kpendjal-Ouest", "Oti", "Oti-Sud", "Tandjouaré"],
}

# town or alternative name -> prefecture
TOWN_ALIASES: dict[str, str] = {
    "Lomé": "Golfe", "Grand Lomé": "Golfe", "Agoè": "Agoè-Nyivé",
    "Aného": "Lacs", "Afagnan": "Bas-Mono", "Vogan": "Vo", "Tabligbo": "Yoto",
    "Tsévié": "Zio", "Kévé": "Avé",
    "Atakpamé": "Ogou", "Elavagnon": "Est-Mono", "Kougnohou": "Akébou", "Badou": "Wawa",
    "Amlamé": "Amou", "Apéyémé": "Danyi", "Kpalimé": "Kloto", "Adéta": "Kpélé",
    "Agou-Gadzépé": "Agou", "Notsé": "Haho", "Tohoun": "Moyen-Mono",
    "Sokodé": "Tchaoudjo", "Sotouboua": "Sotouboua", "Djarkpanga": "Mô",
    "Kara": "Kozah", "Pagouda": "Binah", "Niamtougou": "Doufelgou", "Kandé": "Kéran",
    "Guérin-Kouka": "Dankpen", "Bafilo": "Assoli",
    "Dapaong": "Tône", "Mandouri": "Kpendjal", "Naki-Est": "Kpendjal-Ouest",
    "Mango": "Oti", "Sansanné-Mango": "Oti", "Gando": "Oti-Sud", "Tandjoaré": "Tandjouaré",
}

PREFECTURE_TO_REGION = {p: r for r, ps in REGIONS.items() for p in ps}


def normalize(text: str) -> str:
    """Lower-case, strip accents, unify hyphens/spaces (for robust matching)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[\s\-’']+", " ", text.lower()).strip()


def _build_index() -> list[tuple[re.Pattern, str]]:
    names: dict[str, str] = {p: p for p in PREFECTURE_TO_REGION}
    names.update(TOWN_ALIASES)
    index = []
    # longest names first so "Kpendjal Ouest" wins over "Kpendjal", "Oti Sud" over "Oti"
    for name in sorted(names, key=lambda n: -len(normalize(n))):
        pat = re.compile(r"(?<![a-z])" + re.escape(normalize(name)) + r"(?![a-z])")
        index.append((pat, names[name]))
    return index


_INDEX = _build_index()

# Names that are also common French words or ambiguous: require a place cue before them.
_AMBIGUOUS = {"Vo", "Mô", "Lacs", "Golfe", "Kara", "Oti", "Avé", "Amou", "Agou"}
_AMBIGUOUS_NORM = {normalize(a) for a in _AMBIGUOUS}
# matched against accent-stripped, lower-cased text (see `normalize`)
_CUE = re.compile(
    r"\b(?:a|au|de|du|dans|prefecture|ville|localite|commune|region|fleuve|district|canton)"
    r"\s+(?:la\s+|le\s+|l\s+|de\s+la\s+|des\s+)?$"
)


# Region names count only near the word "région"/"region" (e.g. "région des Savanes",
# "Maritime region" in EM-DAT), since "centrale", "savanes", "plateaux" are common words.
_REGION_PATS = [(re.compile(r"(?<![a-z])" + normalize(r) + r"(?![a-z])"), r) for r in REGIONS]
_REGION_BEFORE = re.compile(r"\bregions?\s+(?:de\s+la\s+|des\s+|du\s+|de\s+)?$")
_REGION_AFTER = re.compile(r"^(?:\s*,?\s*[a-z]+){0,4}\s+regions?\b")


def find_places(text: str) -> list[tuple[str, Optional[str]]]:
    """Return unique (region, prefecture) pairs mentioned in `text`, in order of first mention.

    A region named without any of its prefectures is returned as (region, None).
    """
    norm = normalize(text)
    taken = [False] * len(norm)
    hits: list[tuple[int, str, Optional[str]]] = []
    for pat, pref in _INDEX:
        for m in pat.finditer(norm):
            if any(taken[m.start():m.end()]):
                continue
            if m.group(0) in _AMBIGUOUS_NORM and not _CUE.search(norm[max(0, m.start() - 25):m.start()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            hits.append((m.start(), PREFECTURE_TO_REGION[pref], pref))
    for pat, region in _REGION_PATS:
        for m in pat.finditer(norm):
            if any(taken[m.start():m.end()]):
                continue
            if _REGION_BEFORE.search(norm[max(0, m.start() - 20):m.start()]) or \
               _REGION_AFTER.search(norm[m.end():m.end() + 40]):
                hits.append((m.start(), region, None))
    seen, out = set(), []
    regions_with_pref = {r for _, r, p in hits if p}
    for _, region, pref in sorted(hits, key=lambda h: h[0]):
        key = (region, pref)
        if key in seen or (pref is None and region in regions_with_pref):
            continue
        seen.add(key)
        out.append(key)
    return out
