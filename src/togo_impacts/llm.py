"""LLM-based impact extraction (multilingual), with schema validation.

Supports the Anthropic Messages API and any OpenAI-compatible chat endpoint
(e.g. DeepSeek). Keys are read from environment variables, never stored in code:
  ANTHROPIC_API_KEY            for provider="anthropic"
  OPENAI_COMPATIBLE_API_KEY    for provider="openai" (+ OPENAI_COMPATIBLE_BASE_URL)

Every value returned by the model must be backed by a verbatim quote that is
actually present in the article; values whose quote cannot be found are dropped.
This guards against hallucinated figures.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

from .gazetteer import PREFECTURE_TO_REGION, find_places, normalize
from .schema import IMPACT_FIELDS, ImpactRecord

PROMPT = """You extract climate-extreme impacts from a news article (any language).
Return ONLY a JSON object with these keys:
  "hazard": "flood" | "drought" | null   (null if the article does not report such an event)
  "event_location": string | null         (most specific place in Togo where impacts occurred)
  "impacts": object whose keys are among {fields},
             each value being {{"value": integer, "quote": "<exact words copied from the article>"}}
Rules: report only figures explicitly stated for this event; no estimates, no sums you compute yourself;
omit impacts that are not reported; quotes must be copied verbatim (they are checked).

ARTICLE:
\"\"\"{text}\"\"\""""


def build_prompt(text: str, max_chars: int = 12000) -> str:
    return PROMPT.format(fields=", ".join(IMPACT_FIELDS), text=text[:max_chars])


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> dict:
    import requests  # imported lazily so the package works offline without it
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def call_anthropic(prompt: str, model: str = "claude-sonnet-5-5") -> str:
    key = os.environ["ANTHROPIC_API_KEY"]
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]},
    )
    return "".join(block.get("text", "") for block in data.get("content", []))


def call_openai_compatible(prompt: str, model: str = "deepseek-chat") -> str:
    key = os.environ["OPENAI_COMPATIBLE_API_KEY"]
    base = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "https://api.deepseek.com")
    data = _post_json(
        f"{base.rstrip('/')}/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}],
         "response_format": {"type": "json_object"}},
    )
    return data["choices"][0]["message"]["content"]


PROVIDERS: dict[str, Callable[[str, str], str]] = {
    "anthropic": call_anthropic,
    "openai": call_openai_compatible,
}


def parse_response(raw: str) -> dict:
    """Extract the first JSON object from a model reply (tolerates code fences)."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def _quote_in_text(quote: str, text: str) -> bool:
    q = normalize(quote)
    return bool(q) and q in normalize(text)


def to_record(parsed: dict, text: str, *, model: str, doc_id=None, pub_date=None) -> Optional[ImpactRecord]:
    hazard = parsed.get("hazard")
    if hazard not in ("flood", "drought"):
        return None
    values, evidence = {}, []
    for key, item in (parsed.get("impacts") or {}).items():
        if key not in IMPACT_FIELDS or not isinstance(item, dict):
            continue
        value, quote = item.get("value"), str(item.get("quote", ""))
        if not isinstance(value, int) or value < 0:
            continue
        if not _quote_in_text(quote, text):      # hallucination guard
            continue
        values[key] = value
        evidence.append(f"{key}: «{quote}»")

    admin1 = admin2 = None
    loc = parsed.get("event_location")
    places = find_places(loc) if loc else []
    if not places:
        places = find_places(text)
    if places:
        admin1, admin2 = places[0]
    assert admin2 is None or admin2 in PREFECTURE_TO_REGION

    return ImpactRecord(source="news:llm", hazard=hazard, date=pub_date, admin1=admin1, admin2=admin2,
                        doc_id=doc_id, method=f"llm:{model}", evidence=evidence, **values)


def extract_record(text: str, *, provider: str = "anthropic", model: Optional[str] = None,
                   doc_id=None, pub_date=None, caller: Optional[Callable[[str], str]] = None):
    """Extract one record with an LLM. `caller` lets tests inject a fake model."""
    fn = PROVIDERS[provider]
    model = model or fn.__defaults__[0]
    raw = caller(build_prompt(text)) if caller else fn(build_prompt(text), model)
    return to_record(parse_response(raw), text, model=model, doc_id=doc_id, pub_date=pub_date)
