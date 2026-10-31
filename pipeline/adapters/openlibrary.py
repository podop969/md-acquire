from __future__ import annotations

from ..http import Client
from ..models import Candidate, WorkSpec
from .base import Adapter


class OpenLibraryAdapter(Adapter):
    """Public full-text scans hosted on archive.org, as reported by Open Library.

    Only items Open Library itself marks public/readable are emitted; borrowable
    (controlled digital lending) copies become hints for the wanted list instead.
    """

    name = "openlibrary"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.borrow_hints: list[str] = []

    def lookup(self, client: Client, spec: WorkSpec) -> list[Candidate]:
        self.borrow_hints = []
        params = {"title": spec.title, "limit": 8,
                  "fields": "title,author_name,first_publish_year,ebook_access,"
                            "edition_key,ia,lending_edition_s,has_fulltext"}
        if spec.authors:
            params["author"] = spec.authors[0]
        r = client.get("https://openlibrary.org/search.json", params=params)
        if r.status_code != 200:
            return []
        try:
            docs = r.json().get("docs") or []
        except ValueError:
            return []
        if not docs and "author" in params:
            # Author narrowing can zero out real editions; retry title-only once.
            params.pop("author")
            r = client.get("https://openlibrary.org/search.json", params=params)
            if r.status_code == 200:
                try:
                    docs = r.json().get("docs") or []
                except ValueError:
                    docs = []
        out: list[Candidate] = []
        for doc in docs:
            access = doc.get("ebook_access") or ""
            ed = doc.get("edition_key") or []
            ed_id = ed[0] if ed else None
            if access in ("borrowable", "printdisabled"):
                # Controlled digital lending: a human borrows it; we never fetch it.
                self.borrow_hints.append(
                    f"Open Library has a {access} copy - borrow manually: "
                    + (f"https://openlibrary.org/books/{ed_id}" if ed_id
                       else "https://openlibrary.org")
                )
                continue
            if access != "public":
                continue
            ia_ids = doc.get("ia") or []
            year = doc.get("first_publish_year")
            for ia in ia_ids[:3]:
                pdf_url = f"https://archive.org/download/{ia}/{ia}.pdf"
                score = 80
                if doc.get("title", "").strip().lower() == spec.title.strip().lower():
                    score = 88
                if spec.year_min and year and year >= spec.year_min:
                    score += 5
                out.append(Candidate(
                    source=self.name, url=pdf_url, fmt="pdf",
                    title=doc.get("title", ""),
                    year=year,
                    license="Public domain / open scan (Internet Archive via Open Library)",
                    score=score,
                    extra={"ia_id": ia, "ol_edition": ed_id, "ebook_access": access},
                ))
        return out