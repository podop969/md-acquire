from __future__ import annotations
import re

from ..http import Client
from ..models import Candidate, WorkSpec
from .base import Adapter

# Project Gutenberg (via Gutendex when it answers, gutenberg.org directly otherwise).
# Public domain in the US; gutendex.com is a read-only metadata API.


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class GutenbergAdapter(Adapter):
    name = "gutenberg"

    def lookup(self, client: Client, spec: WorkSpec) -> list[Candidate]:
        out: list[Candidate] = []
        exact: dict[str, Candidate] = {}
        for book in self._via_gutendex(client, spec) or self._via_gutenberg_org(client, spec):
            title = book.get("title", "")
            exactness = 90 if _norm(title) == _norm(spec.title) else 55
            fmts = self._formats_of(book)
            for fmt, url, lic in fmts:
                cand = Candidate(
                    source=self.name, url=url, fmt=fmt, title=title,
                    year=int(book["year"]) if book.get("year") else None,
                    license=lic, score=exactness,
                    extra={"gutenberg_id": book.get("id")},
                )
                if exactness >= 90:
                    exact.setdefault(fmt, cand)
                else:
                    out.append(cand)
        fuzzy = out
        out = list(exact.values())
        for cand in fuzzy:
            if not any(c.fmt == cand.fmt for c in out):
                out.append(cand)
        out.sort(key=lambda c: (-c.score, spec.formats.index(c.fmt) if c.fmt in spec.formats else 99))
        return out

    def _via_gutendex(self, client: Client, spec: WorkSpec) -> list[dict]:
        try:
            r = client.get("https://gutendex.com/books", params={"search": spec.title})
            if r.status_code != 200:
                return []
            results = []
            for book in (r.json().get("results") or [])[:8]:
                results.append({
                    "id": book.get("id"), "title": book.get("title", ""),
                    "formats": book.get("formats") or {}, "year": None,
                })
            return results
        except Exception:
            return []

    def _via_gutenberg_org(self, client: Client, spec: WorkSpec) -> list[dict]:
        try:
            r = client.get("https://www.gutenberg.org/ebooks/search/?query=" + spec.title)
            if r.status_code != 200:
                return []
            books: list[dict] = []
            for m in re.finditer(
                r'href="(/ebooks/(\d+))"[^>]*>\s*<b>(.*?)</b>', r.text, re.S
            ):
                path, gid, title = m.group(1), m.group(2), re.sub(r"<[^>]+>", "", m.group(3))
                books.append({
                    "id": int(gid), "title": " ".join(title.split()),
                    "formats": {
                        # .epub.images / .epub.noimages and .pdf.images patterns
                        "application/epub+zip": f"https://www.gutenberg.org{path}.epub3.images",
                        "application/pdf": f"https://www.gutenberg.org{path}.pdf.images",
                    },
                    "year": None,
                })
            return books[:8]
        except Exception:
            return []

    def _formats_of(self, book: dict) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        fmts = book.get("formats") or {}
        for mime, url in fmts.items():
            if mime == "application/epub+zip":
                out.append(("epub", url, "Public domain (Project Gutenberg)"))
            elif mime == "application/pdf":
                out.append(("pdf", url, "Public domain (Project Gutenberg)"))
        return out