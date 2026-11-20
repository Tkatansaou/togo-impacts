"""Group article-level records into events (hazard x place x time window)."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .schema import IMPACT_FIELDS, ImpactRecord


def records_to_frame(records: list[ImpactRecord]) -> pd.DataFrame:
    df = pd.DataFrame([r.to_dict() for r in records], columns=ImpactRecord.columns())
    df["date"] = pd.to_datetime(df["date"])
    return df


def cluster_events(df: pd.DataFrame, window_days: int = 15) -> pd.DataFrame:
    """Assign an `event_id` to article records.

    Two records belong to the same event if they share hazard and prefecture
    (region when the prefecture is unknown) and are at most `window_days` apart
    from the previous record of the chain. Impacts are aggregated with `max`,
    since articles typically report successive, cumulative tolls.
    """
    if df.empty:
        return df.assign(event_id=pd.Series(dtype=str))
    df = df.copy()
    df["place_key"] = df["admin2"].fillna(df["admin1"]).fillna("TGO")
    df = df.sort_values(["hazard", "place_key", "date"])
    ids = []
    window = timedelta(days=window_days)
    for (hazard, place), g in df.groupby(["hazard", "place_key"], sort=False):
        start, prev = None, None
        for d in g["date"]:
            if prev is None or pd.isna(d) or pd.isna(prev) or d - prev > window:
                start = d
            prev = d
            stamp = start.strftime("%Y%m%d") if pd.notna(start) else "nodate"
            ids.append(f"TGO-{hazard[:2].upper()}-{stamp}-{place}")
    df["event_id"] = ids
    return df.drop(columns="place_key")


def aggregate_events(df: pd.DataFrame) -> pd.DataFrame:
    """One row per event: first/last report date, max of each impact, n of articles."""
    if df.empty:
        return pd.DataFrame()
    named = {f: (f, "max") for f in IMPACT_FIELDS}
    named.update(
        hazard=("hazard", "first"), admin1=("admin1", "first"), admin2=("admin2", "first"),
        start_date=("date", "min"), last_report=("date", "max"), n_articles=("doc_id", "nunique"),
    )
    out = df.groupby("event_id").agg(**named)
    out["source"] = "news"
    return out.reset_index()
