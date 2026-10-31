from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class WorkSpec:
    key: str
    title: str
    authors: list[str] = field(default_factory=list)
    isbn13: Optional[str] = None
    doi: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    edition_pref: str = "latest"
    formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])
    priority: str = "open_access"
    notes: str = ""
    source_path: Optional[Path] = None


@dataclass
class Candidate:
    source: str
    url: str
    fmt: str                       # "pdf" | "epub"
    title: str = ""
    year: Optional[int] = None
    license: str = ""
    score: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class Resolution:
    spec: WorkSpec
    status: str                    # ok | partial | not_found | failed
    saved: list[Path] = field(default_factory=list)
    detail: str = ""
    hints: list[str] = field(default_factory=list)
    manual: list[dict] = field(default_factory=list)