from __future__ import annotations
import re
import xml.etree.ElementTree as ET

from ..http import Client
from ..models import Candidate, WorkSpec
from .base import Adapter

NS = {"a": "http://www.w3.org/2005/Atom"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class ArxivAdapter(Adapter):
    name = "arxiv"

    def lookup(self, client: Client, spec: WorkSpec) -> list[Candidate]:
        query = f'ti:"{spec.title}"'
        if spec.authors:
            query += f' AND au:"{spec.authors[0]}"'
        r = client.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": query, "max_results": 5},
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        out: list[Candidate] = []
        for entry in root.findall("a:entry", NS):
            title = " ".join((entry.findtext("a:title", "", NS) or "").split())
            abs_id = (entry.findtext("a:id", "", NS) or "").rsplit("/abs/", 1)[-1]
            if not abs_id:
                continue
            published = entry.findtext("a:published", "", NS) or ""
            score = 85 if _norm(title) == _norm(spec.title) else 55
            out.append(
                Candidate(
                    source=self.name,
                    url=f"https://arxiv.org/pdf/{abs_id}",
                    fmt="pdf",
                    title=title,
                    year=int(published[:4]) if published[:4].isdigit() else None,
                    license="arXiv (author license, see abs page)",
                    score=score,
                    extra={"arxiv_id": abs_id},
                )
            )
        return out