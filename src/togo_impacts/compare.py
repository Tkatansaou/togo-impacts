"""Compare news-derived events with EM-DAT records to quantify reporting gaps.

EM-DAT data are not redistributed here: download the public export
(https://www.emdat.be, free registration), filter on Togo, and pass the .xlsx/.csv path.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .gazetteer import find_places

EMDAT_COLUMNS = {
    "DisNo.": "emdat_id", "Disaster Type": "disaster_type", "ISO": "iso3", "Location": "location",
    "Start Year": "year", "Start Month": "month", "Start Day": "day",
    "Total Deaths": "deaths", "No. Injured": "injured", "No. Affected": "affected",
    "No. Homeless": "displaced",
}
HAZARD_MAP = {"Flood": "flood", "Drought": "drought"}


def load_emdat(path: str | Path, iso3: str = "TGO") -> pd.DataFrame:
    path = Path(path)
    raw = pd.read_excel(path) if path.suffix in (".xlsx", ".xls") else pd.read_csv(path)
    df = raw.rename(columns=EMDAT_COLUMNS)[list(EMDAT_COLUMNS.values())]
    df = df[(df["iso3"] == iso3) & df["disaster_type"].isin(HAZARD_MAP)].copy()
    df["hazard"] = df["disaster_type"].map(HAZARD_MAP)
    # EM-DAT often lacks day (or month): use mid-period and flag the precision
    df["date_precision"] = "day"
    df.loc[df["day"].isna(), "date_precision"] = "month"
    df.loc[df["month"].isna(), "date_precision"] = "year"
    df["start_date"] = pd.to_datetime(dict(
        year=df["year"].astype(int), month=df["month"].fillna(7).astype(int),
        day=df["day"].fillna(15).astype(int)))
    df["admin1_list"] = df["location"].fillna("").map(lambda s: sorted({r for r, _ in find_places(s)}))
    return df.reset_index(drop=True)


def match_events(news: pd.DataFrame, emdat: pd.DataFrame, max_days: int = 45) -> pd.DataFrame:
    """For each news event, find the closest EM-DAT event of the same hazard.

    A match requires |start_date difference| <= max_days and, when both sides
    have spatial information, overlap at region (admin1) level.
    """
    rows = []
    for _, ev in news.iterrows():
        cands = emdat[emdat["hazard"] == ev["hazard"]].copy()
        cands["lag_days"] = (cands["start_date"] - ev["start_date"]).dt.days.abs()
        cands = cands[cands["lag_days"] <= max_days]
        if pd.notna(ev.get("admin1")):
            cands = cands[cands["admin1_list"].map(lambda l: not l or ev["admin1"] in l)]
        best = cands.sort_values("lag_days").head(1)
        rows.append({
            "event_id": ev["event_id"],
            "emdat_id": best["emdat_id"].iloc[0] if len(best) else None,
            "lag_days": best["lag_days"].iloc[0] if len(best) else None,
            "deaths_news": ev.get("deaths"),
            "deaths_emdat": best["deaths"].iloc[0] if len(best) else None,
        })
    return pd.DataFrame(rows)


def gap_summary(news: pd.DataFrame, emdat: pd.DataFrame, matches: pd.DataFrame) -> dict:
    n_news = len(news)
    n_matched = int(matches["emdat_id"].notna().sum()) if n_news else 0
    both = matches.dropna(subset=["deaths_news", "deaths_emdat"])
    return {
        "news_events": n_news,
        "emdat_events": len(emdat),
        "news_events_in_emdat": n_matched,
        "share_news_events_missing_from_emdat": round(1 - n_matched / n_news, 3) if n_news else None,
        "emdat_events_matched_by_news": int(matches["emdat_id"].dropna().nunique()),
        "median_deaths_ratio_news_over_emdat":
            round(float((both["deaths_news"] / both["deaths_emdat"].replace(0, pd.NA)).median()), 2)
            if len(both) else None,
    }
