from __future__ import annotations

from ..http import Client
from ..models import Candidate, WorkSpec
from .base import Adapter


class UnpaywallAdapter(Adapter):
    """Open-access copies of DOI-registered papers, as reported by Unpaywall."""

    name = "unpaywall"

    def lookup(self, client: Client, spec: WorkSpec) -> list[Candidate]:
        if not spec.doi or not self.cfg.contact_email:
            return []
        r = client.get(
            f"https://api.unpaywall.org/v2/{spec.doi}",
            params={"email": self.cfg.contact_email},
        )
        if r.status_code != 200:
            return []
        try:
            data = r.json()
        except ValueError:
            return []
        best = data.get("best_oa_location") or {}
        others = [x for x in (data.get("oa_locations") or []) if x and x != best]
        year = data.get("year") or None

        out: list[Candidate] = []
        seen: set[str] = set()
        for i, loc in enumerate([best] + others):
            if not loc:
                continue
            pdf = loc.get("url_for_pdf")
            landing = loc.get("url")
            if pdf:
                url, direct = pdf, True
            elif landing:
                url, direct = landing, False
            else:
                continue
            if url in seen:
                continue
            seen.add(url)
            score = 70 if (i == 0 and direct) else (60 if direct else 50)
            out.append(Candidate(
                source=self.name,
                url=url,
                fmt="pdf",
                title=spec.title,
                year=int(year) if year and str(year).isdigit() else None,
                license=loc.get("license") or data.get("license") or "",
                score=score,
                extra={"host_type": loc.get("host_type"), "doi": spec.doi},
            ))
        return out