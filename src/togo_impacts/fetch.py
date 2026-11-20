"""Collect candidate French-language news articles on floods in Togo.

Uses the free GDELT DOC 2.0 API to list article URLs, then (optionally)
`trafilatura` to download the main text. Respect each site's terms of use;
only store the text needed for research and cite the URLs.
"""
from __future__ import annotations

import json
from pathlib import Path

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def gdelt_search(query: str = '(inondation OR inondations OR "pluies diluviennes") Togo sourcelang:french',
                 start: str = "20240101000000", end: str = "20241231235959", max_records: int = 250) -> list[dict]:
    import requests
    params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": max_records,
              "startdatetime": start, "enddatetime": end, "sort": "DateAsc"}
    r = requests.get(GDELT_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("articles", [])


def download_text(url: str) -> str | None:
    import trafilatura
    html = trafilatura.fetch_url(url)
    return trafilatura.extract(html, include_comments=False) if html else None


def build_corpus(out_path: str | Path, **search_kwargs) -> int:
    """Write a JSONL corpus: {doc_id, date, title, domain, text}. Returns n articles written."""
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for art in gdelt_search(**search_kwargs):
            text = download_text(art["url"])
            if not text:
                continue
            seen = art.get("seendate", "")  # e.g. 20240915T120000Z
            rec = {"doc_id": art["url"], "date": f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}" if seen else None,
                   "title": art.get("title"), "domain": art.get("domain"), "text": text}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n
