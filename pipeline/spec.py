from __future__ import annotations

from pathlib import Path
import re

import yaml

from .models import WorkSpec
from .annas_archive import record_md5

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def _norm_isbn(v) -> str | None:
    if not v:
        return None
    digits = re.sub(r"[^0-9Xx]", "", str(v)).upper()
    return digits or None


def _norm_doi(v) -> str | None:
    if not v:
        return None
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", str(v).strip(), flags=re.I) or None


def parse_file(path: Path) -> WorkSpec:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    title = data.get("title")
    if not title:
        raise ValueError(f"{path.name}: 'title' is required")
    source = str(data.get('source') or '')
    source_url = str(data.get('source_url') or '')
    source_format = str(data.get('source_format') or '')
    if source == 'annas_archive':
        record_md5(source_url)
        if source_format not in ('pdf', 'epub'):
            raise ValueError("Anna's Archive specs require source_format: pdf or epub. Re-add a supported search result.")
    return WorkSpec(
        key=path.stem,
        title=str(title),
        authors=[str(a) for a in (data.get("authors") or [])],
        isbn13=_norm_isbn(data.get("isbn13")),
        doi=_norm_doi(data.get("doi")),
        year_min=data.get("year_min"),
        year_max=data.get("year_max"),
        edition_pref=str(data.get("edition_pref", "latest")),
        formats=[str(f).lower() for f in (data.get("formats") or ["epub", "pdf"])],
        priority=str(data.get("priority", "open_access")),
        notes=m.group(2).strip(),
        source_path=path,
        source=source, source_url=source_url, source_format=source_format,
    )


def load_from(paths: list[Path]) -> list[WorkSpec]:
    """Load specs from a mix of files and directories (directories: top-level *.md)."""
    specs: list[WorkSpec] = []
    seen: set[Path] = set()
    for p in paths:
        if p.is_dir():
            entries = sorted(p.glob("*.md"))
        elif p.exists() and p.suffix.lower() == ".md":
            entries = [p]
        else:
            raise FileNotFoundError(f"spec path not found or not .md: {p}")
        for f in entries:
            if f.resolve() not in seen:
                seen.add(f.resolve())
                specs.append(parse_file(f))
    return specs
