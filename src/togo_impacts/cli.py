"""Command-line interface.

  togo-impacts fetch    --out data/corpus.jsonl --start 20240101000000 --end 20241231235959
  togo-impacts extract  data/corpus.jsonl --method rules|llm [--provider anthropic|openai] --out outputs/records.csv
  togo-impacts events   outputs/records.csv --out outputs/events.csv
  togo-impacts compare  outputs/events.csv --emdat path/to/emdat_export.xlsx --out outputs/matches.csv
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import harmonize, rules
from .schema import ImpactRecord


def _read_corpus(path: str):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def cmd_fetch(a):
    from .fetch import build_corpus
    n = build_corpus(a.out, start=a.start, end=a.end)
    print(f"{n} articles written to {a.out}")


def cmd_extract(a):
    records: list[ImpactRecord] = []
    for doc in _read_corpus(a.corpus):
        pub = date.fromisoformat(doc["date"]) if doc.get("date") else None
        text = f"{doc.get('title') or ''}\n{doc['text']}"
        if a.method == "rules":
            rec = rules.extract_record(text, doc_id=doc["doc_id"], pub_date=pub)
        else:
            from . import llm
            rec = llm.extract_record(text, provider=a.provider, model=a.model, doc_id=doc["doc_id"], pub_date=pub)
        if rec is not None:
            records.append(rec)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    harmonize.records_to_frame(records).to_csv(a.out, index=False)
    print(f"{len(records)} hazard-related articles -> {a.out}")


def cmd_events(a):
    df = pd.read_csv(a.records, parse_dates=["date"])
    events = harmonize.aggregate_events(harmonize.cluster_events(df, window_days=a.window))
    events.to_csv(a.out, index=False)
    print(f"{len(events)} events -> {a.out}")


def cmd_compare(a):
    from . import compare
    news = pd.read_csv(a.events, parse_dates=["start_date"])
    emdat = compare.load_emdat(a.emdat)
    if a.start_year:
        emdat = emdat[emdat["year"] >= a.start_year]
    matches = compare.match_events(news, emdat, max_days=a.max_days)
    matches.to_csv(a.out, index=False)
    print(json.dumps(compare.gap_summary(news, emdat, matches), indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="togo-impacts", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)

    f = sub.add_parser("fetch"); f.set_defaults(func=cmd_fetch)
    f.add_argument("--out", required=True); f.add_argument("--start", default="20240101000000")
    f.add_argument("--end", default="20241231235959")

    e = sub.add_parser("extract"); e.set_defaults(func=cmd_extract)
    e.add_argument("corpus"); e.add_argument("--out", required=True)
    e.add_argument("--method", choices=["rules", "llm"], default="rules")
    e.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    e.add_argument("--model", default=None)

    v = sub.add_parser("events"); v.set_defaults(func=cmd_events)
    v.add_argument("records"); v.add_argument("--out", required=True); v.add_argument("--window", type=int, default=15)

    c = sub.add_parser("compare"); c.set_defaults(func=cmd_compare)
    c.add_argument("events"); c.add_argument("--emdat", required=True); c.add_argument("--out", required=True)
    c.add_argument("--max-days", type=int, default=45); c.add_argument("--start-year", type=int)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
