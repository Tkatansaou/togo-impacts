# togo-impacts

**Bias-aware extraction of flood and drought impacts from French-language news in Togo, and comparison with global impact databases (EM-DAT).**

![tests](https://github.com/Tkatansaou/togo-impacts/actions/workflows/tests.yml/badge.svg)

## Why

Global impact databases shape our picture of where climate extremes hurt people. In Francophone West Africa, many flood impacts are reported only in local French-language media, at sub-national scale, and never reach these databases. This project builds a small, transparent pipeline to:

1. **collect** French-language news on floods in Togo (GDELT + full-text extraction),
2. **extract** impacts (deaths, injured, missing, affected, displaced, houses destroyed/damaged) with
   - a transparent **rule-based** French extractor (offline baseline), and
   - an **LLM extractor** (Anthropic or any OpenAI-compatible API, e.g. DeepSeek) whose figures are kept **only if backed by a verbatim quote found in the article** (hallucination guard),
3. **georeference** each report to Togo's 5 regions / 39 prefectures (gazetteer with town aliases and ambiguity rules),
4. **harmonise** article-level records into events in a common *event–impact–space* schema,
5. **compare** news-derived events with EM-DAT and quantify reporting gaps.

## Pipeline

```
GDELT search ──► article text ──► extraction (rules | LLM + quote check)
                                         │
                       gazetteer (region / prefecture)
                                         │
                       ImpactRecord (common schema, with evidence spans)
                                         │
             event clustering (hazard × prefecture × 15-day window, max of cumulative tolls)
                                         │
             matching with EM-DAT (hazard, ±45 days, region overlap) ──► gap metrics
```

## Quick start

```bash
pip install -e ".[dev,fetch]"
pytest -q                                   # 15 tests, no network or API key needed

# 1. collect articles (needs internet)
togo-impacts fetch --out data/corpus.jsonl --start 20240101000000 --end 20241231235959

# 2. extract impacts
togo-impacts extract data/corpus.jsonl --method rules --out outputs/records_rules.csv
export ANTHROPIC_API_KEY=...                # or OPENAI_COMPATIBLE_API_KEY (+ _BASE_URL) with --provider openai
togo-impacts extract data/corpus.jsonl --method llm --provider anthropic --out outputs/records_llm.csv

# 3. group into events, 4. compare with EM-DAT (download the public export from emdat.be)
togo-impacts events outputs/records_rules.csv --out outputs/events.csv
togo-impacts compare outputs/events.csv --emdat emdat_export.xlsx --out outputs/matches.csv
```

Example output on the bundled sample (`data/sample_articles.jsonl`):

```json
{
  "news_events": 2,
  "emdat_events": 1,
  "news_events_in_emdat": 1,
  "share_news_events_missing_from_emdat": 0.5,
  "median_deaths_ratio_news_over_emdat": 0.75
}
```

> ⚠️ `data/sample_articles.jsonl` contains **synthetic, clearly labelled example texts** written for testing only. They do not describe real events. The EM-DAT table used in the tests is also synthetic. EM-DAT data are not redistributed here.

## Design choices

- **Traceability first:** every extracted value carries the text span it comes from (`evidence` column), so that rule-based and LLM outputs can be audited and compared.
- **Conservative aggregation:** articles often publish successive, cumulative tolls; events keep the maximum reported value per impact type rather than a sum.
- **Explicit date precision:** EM-DAT records lacking a day or month are placed mid-period and flagged (`date_precision`).
- **Ambiguous toponyms** (e.g. *Vo*, *Lacs*, *Kara*) require a place cue ("préfecture de", "à", …); region names (*Savanes*, *Centrale*, *Plateaux*) require the word *région*.

## Known limitations

- Rule-based extraction does not distinguish households from persons ("100 ménages sinistrés" is counted as 100 affected) and does not record explicit zeros ("aucune perte en vie humaine").
- One location per article (the first mentioned); multi-prefecture events are not yet split.
- The matching uses regions, not flood extents; a hazard reference layer (e.g. satellite flood maps, GloFAS) is the natural next step.
- No validation set yet: precision/recall of each extractor still has to be measured on manually annotated articles.

## Roadmap

- [ ] Manually annotate ~100 real articles (Togo, 2010–2024) and report precision/recall for rules vs LLM.
- [ ] Add household → person conversion using census household size.
- [ ] Model the probability that a detected flood appears in each source as a function of HDI, remoteness and language.
- [ ] Extend to Benin and Burkina Faso; add drought impacts.

## Author

Tchaa Katansaou — sanitary & environmental engineer, field epidemiologist (FELTP). Related work: *Climatic factors associated with malaria in Togo, 2008–2022* (MSc thesis, VAR time-series models in R).

License: MIT
