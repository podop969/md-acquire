from dataclasses import dataclass
from pathlib import Path
import os

import yaml

DEFAULTS = {
    "specs_dir": "specs",
    "out_dir": "library",
    "contact_email": "",
    "min_interval": 1.0,
    "timeout": 30,
    "retries": 3,
    "adapters": ["arxiv", "openlibrary", "gutenberg", "unpaywall"],
}


@dataclass
class Config:
    specs_dir: Path
    out_dir: Path
    contact_email: str
    min_interval: float
    timeout: int
    retries: int
    adapters: list[str]

    @classmethod
    def load(cls, path: str = "config.yaml") -> "Config":
        p = Path(path)
        data = dict(DEFAULTS)
        if p.exists():
            data.update(yaml.safe_load(p.read_text("utf-8")) or {})
        data["contact_email"] = os.environ.get("ACQUIRE_EMAIL", data["contact_email"]) or ""
        return cls(
            specs_dir=Path(data["specs_dir"]),
            out_dir=Path(data["out_dir"]),
            contact_email=data["contact_email"],
            min_interval=float(data["min_interval"]),
            timeout=int(data["timeout"]),
            retries=int(data["retries"]),
            adapters=list(data["adapters"]),
        )