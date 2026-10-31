"""Best-effort metadata enrichment: fills a missing ISBN on a WorkSpec.

crossref has been unreachable from some networks, so enrichment is
openlibrary-only and always wrapped in try/except by the caller: an enrichment
failure must never fail a run.
"""
from __future__ import annotations

from .http import Client
from .models import WorkSpec


def _isbn_from_openlibrary(client: Client, spec: WorkSpec) -> str | None:
    params = {"title": spec.title, "limit": 3, "fields": "title,isbn"}
    if spec.authors:
        params["author"] = spec.authors[0]
    r = client.get("https://openlibrary.org/search.json", params=params)
    if r.status_code != 200:
        return None
    for doc in r.json().get("docs") or []:
        for isbn in doc.get("isbn") or []:
            if len(str(isbn)) == 13:
                return str(isbn)
    return None


def enrich(client: Client, spec: WorkSpec) -> list[str]:
    """Mutates spec in place. Returns notes about what was filled."""
    notes: list[str] = []
    if not spec.isbn13:
        try:
            isbn = _isbn_from_openlibrary(client, spec)
            if isbn:
                spec.isbn13 = isbn
                notes.append(f"isbn13 <- {isbn}")
        except Exception:
            pass
    return notes