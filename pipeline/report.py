from __future__ import annotations
from pathlib import Path

from .models import Resolution


def write(resolutions: list[Resolution], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = [r for r in resolutions if r.status in ("ok", "partial")]
    bad = [r for r in resolutions if r.status not in ("ok", "partial")]

    lines = ["# Acquisition report", "", f"- resolved: {len(ok)}", f"- unresolved: {len(bad)}", ""]
    if ok:
        lines += ["| spec | files | source(s) |", "|---|---|---|"]
        for r in ok:
            files = ", ".join(p.name for p in r.saved)
            lines.append(f"| {r.spec.key} | {files} | {r.detail} |")
        lines.append("")

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    wanted = ["# Wanted", "",
              "No open-access copy downloaded for these. Decide each one yourself:",
              "the links are search pages, not downloads.", ""]
    for r in bad:
        wanted.append(f"## {r.spec.title}")
        if r.spec.authors:
            wanted.append(f"- authors: {', '.join(r.spec.authors)}")
        if r.spec.isbn13:
            wanted.append(f"- ISBN-13: {r.spec.isbn13}")
        if r.spec.doi:
            wanted.append(f"- DOI: {r.spec.doi}")
        if r.spec.year_min:
            lo = str(r.spec.year_min)
            hi = str(r.spec.year_max) if r.spec.year_max else ""
            wanted.append(f"- year window: {lo}" + (f"-{hi}" if hi else "+"))
        wanted.append(f"- spec file: {r.spec.source_path}" if r.spec.source_path else "")
        if r.detail:
            wanted.append(f"- detail: {r.detail}")
        for hint in r.hints:
            wanted.append(f"- {hint}")
        if r.manual:
            wanted.append("- search manually:")
            for link in r.manual:
                wanted.append(f"  - [{link['label']}]({link['url']})")
        wanted.append("")
    wanted_path = out_dir / "wanted.md"
    wanted_path.write_text("\n".join(wanted), encoding="utf-8")
    try:
        from .htmlwanted import build as build_html
        build_html(wanted_path)
    except Exception:
        pass  # HTML is a convenience, never a failure mode

    return report_path, wanted_path