import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from togo_impacts import compare, harmonize, llm, rules
from togo_impacts.gazetteer import find_places

DATA = Path(__file__).resolve().parents[1] / "data" / "sample_articles.jsonl"


def load_sample():
    return [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------- gazetteer ----------
def test_town_maps_to_prefecture():
    assert find_places("Inondations à Vogan et Aného") == [("Maritime", "Vo"), ("Maritime", "Lacs")]


def test_longest_name_wins():
    assert find_places("dans la préfecture de Kpendjal-Ouest") == [("Savanes", "Kpendjal-Ouest")]


def test_ambiguous_names_need_a_place_cue():
    assert find_places("le vo du concert") == []          # no place cue
    assert find_places("la préfecture de Vo") == [("Maritime", "Vo")]


def test_region_names_need_the_word_region():
    assert find_places("Maritime, Plateaux, Savanes regions") == [
        ("Maritime", None), ("Plateaux", None), ("Savanes", None)]
    assert find_places("la région des Savanes") == [("Savanes", None)]
    assert find_places("une centrale solaire dans les savanes") == []
    assert find_places("région des Savanes, à Dapaong") == [("Savanes", "Tône")]


# ---------- rules ----------
@pytest.mark.parametrize("raw,expected", [
    ("1 200", 1200), ("1.200", 1200), ("une trentaine", 30), ("3,5 millions", 3_500_000), ("deux", 2)])
def test_parse_number(raw, expected):
    assert rules.parse_number(raw) == expected


def test_rules_extract_article():
    rec = rules.extract_record(load_sample()[1]["text"], doc_id="x")
    assert rec.hazard == "flood" and rec.admin2 == "Vo"
    assert (rec.deaths, rec.affected, rec.displaced) == (3, 1850, 400)
    assert (rec.houses_destroyed, rec.houses_damaged) == (45, 120)
    assert rec.evidence  # every value is traceable to a text span


def test_rules_ignore_non_hazard_article():
    assert rules.extract_record(load_sample()[3]["text"]) is None


def test_no_number_word_inside_other_words():
    rec = rules.extract_record("Inondation à Lomé : aucun mort signalé.")
    assert rec.deaths is None


# ---------- LLM output validation (no network: fake model) ----------
def test_llm_hallucinated_quote_is_dropped():
    text = load_sample()[0]["text"]
    fake = json.dumps({"hazard": "flood", "event_location": "Vogan", "impacts": {
        "deaths": {"value": 2, "quote": "2 morts"},
        "displaced": {"value": 900, "quote": "900 personnes déplacées"}}})  # not in text
    rec = llm.extract_record(text, caller=lambda prompt: fake, model="fake")
    assert rec.deaths == 2 and rec.displaced is None and rec.admin2 == "Vo"


# ---------- harmonisation ----------
def sample_records():
    out = []
    for d in load_sample():
        r = rules.extract_record(d["title"] + "\n" + d["text"], doc_id=d["doc_id"],
                                 pub_date=date.fromisoformat(d["date"]))
        if r:
            out.append(r)
    return out


def test_articles_cluster_into_events():
    df = harmonize.cluster_events(harmonize.records_to_frame(sample_records()))
    events = harmonize.aggregate_events(df)
    assert len(events) == 2                                 # Vo (2 articles) + Oti
    vo = events[events["admin2"] == "Vo"].iloc[0]
    assert vo["n_articles"] == 2 and vo["deaths"] == 3 and vo["affected"] == 1850


# ---------- comparison with EM-DAT (synthetic table) ----------
def test_gap_summary(tmp_path):
    emdat_csv = tmp_path / "emdat.csv"
    pd.DataFrame([{
        "DisNo.": "2024-0001-TGO", "Disaster Type": "Flood", "ISO": "TGO", "Location": "Maritime region",
        "Start Year": 2024, "Start Month": 9, "Start Day": None, "Total Deaths": 4,
        "No. Injured": None, "No. Affected": 3000, "No. Homeless": None}]).to_csv(emdat_csv, index=False)
    events = harmonize.aggregate_events(harmonize.cluster_events(harmonize.records_to_frame(sample_records())))
    em = compare.load_emdat(emdat_csv)
    matches = compare.match_events(events, em)
    summary = compare.gap_summary(events, em, matches)
    assert summary["news_events_in_emdat"] == 1              # Vo matched, Oti (Savanes) not
    assert summary["share_news_events_missing_from_emdat"] == 0.5
