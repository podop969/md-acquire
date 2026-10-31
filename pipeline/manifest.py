from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Candidate, WorkSpec


class Manifest:
    def __init__(self, path: Path):
        self.path = path

    def record(self, spec: WorkSpec, cand: Candidate, saved: Path, sha256: str) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "key": spec.key,
            "title": spec.title,
            "authors": spec.authors,
            "source": cand.source,
            "url": cand.url,
            "format": cand.fmt,
            "license": cand.license,
            "year": cand.year,
            "saved_as": saved.name,
            "sha256": sha256,
            "extra": cand.extra,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")