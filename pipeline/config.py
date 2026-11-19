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
    "annas_archive_url": "https://annas-archive.gl",
    "annas_archive_mode": "http",
    "annas_archive_browser_channel": "chrome",
    "annas_archive_browser_timeout": 120,
    "annas_archive_profile_dir": ".browser/annas-archive",
    "annas_archive_download_timeout": 300,
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
    annas_archive_url: str = "https://annas-archive.gl"
    annas_archive_mode: str = "http"
    annas_archive_browser_channel: str = "chrome"
    annas_archive_browser_timeout: float = 120
    annas_archive_profile_dir: Path = Path('.browser/annas-archive')
    annas_archive_download_timeout: float = 300

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
            annas_archive_url=str(data["annas_archive_url"]),
            annas_archive_mode=str(data["annas_archive_mode"]),
            annas_archive_browser_channel=str(data["annas_archive_browser_channel"]),
            annas_archive_browser_timeout=float(data["annas_archive_browser_timeout"]),
            annas_archive_profile_dir=p.parent / Path(data["annas_archive_profile_dir"]),
            annas_archive_download_timeout=float(data['annas_archive_download_timeout']),
        )
