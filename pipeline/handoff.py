"""Manual-handoff links for works the pipeline will not fetch automatically.

The pipeline only downloads from open/public-domain sources. Everything else
lands here: a wanted entry gets one-click search links so a human decides which
copy to take, from which source, in their own browser.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .models import WorkSpec


def _q(spec: WorkSpec) -> str:
    parts = [spec.title]
    if spec.authors:
        parts.append(spec.authors[0])
    return quote_plus(" ".join(parts))


def manual_links(spec: WorkSpec) -> list[dict]:
    """Search pages only. No site here is fetched by the pipeline itself."""
    links: list[dict] = [
        {"source": "annas-archive", "label": "Anna's Archive (public search page)",
         "url": f"https://annas-archive.org/search?q={_q(spec)}"},
        {"source": "openlibrary-search", "label": "Open Library (editions + borrowing)",
         "url": f"https://openlibrary.org/search?q={_q(spec)}"},
        {"source": "worldcat", "label": "WorldCat (library copies / ILL)",
         "url": f"https://search.worldcat.org/search?q={_q(spec)}"},
        {"source": "google-books", "label": "Google Books",
         "url": f"https://www.google.com/search?q={_q(spec)}+book&tbm=bks"},
        {"source": "google-scholar", "label": "Google Scholar (papers)",
         "url": f"https://scholar.google.com/scholar?q={_q(spec)}"},
    ]
    if spec.isbn13:
        isbn = spec.isbn13
        links.append({"source": "worldcat-isbn", "label": f"WorldCat by ISBN {isbn}",
                      "url": f"https://search.worldcat.org/search?q=bn%3A{isbn}"})
        links.append({"source": "annas-archive-isbn", "label": f"Anna's Archive by ISBN {isbn}",
                      "url": f"https://annas-archive.org/search?q={isbn}"})
    if spec.doi:
        links.append({"source": "doi", "label": f"DOI landing page {spec.doi}",
                      "url": f"https://doi.org/{spec.doi}"})
    return links