"""Common event-impact-space schema for flood/drought impact records.

Every source (news extraction, EM-DAT, national reports) is mapped to
`ImpactRecord` so that records can be compared on the same footing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date
from typing import Optional

IMPACT_FIELDS = (
    "deaths",
    "injured",
    "missing",
    "affected",
    "displaced",
    "houses_destroyed",
    "houses_damaged",
)


@dataclass
class ImpactRecord:
    source: str                      # e.g. "news:rules", "news:llm", "emdat"
    hazard: str                      # "flood" | "drought"
    country_iso3: str = "TGO"
    date: Optional[date] = None      # publication date or event start date
    admin1: Optional[str] = None     # region
    admin2: Optional[str] = None     # prefecture
    deaths: Optional[int] = None
    injured: Optional[int] = None
    missing: Optional[int] = None
    affected: Optional[int] = None
    displaced: Optional[int] = None
    houses_destroyed: Optional[int] = None
    houses_damaged: Optional[int] = None
    doc_id: Optional[str] = None     # article URL or source record id
    language: Optional[str] = None
    method: Optional[str] = None     # "rules" | "llm:<model>" | "database"
    evidence: list[str] = field(default_factory=list)  # text spans supporting values

    def impacts(self) -> dict[str, Optional[int]]:
        return {k: getattr(self, k) for k in IMPACT_FIELDS}

    def has_impact(self) -> bool:
        return any(v is not None for v in self.impacts().values())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        d["evidence"] = " | ".join(self.evidence)
        return d

    @classmethod
    def columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]
