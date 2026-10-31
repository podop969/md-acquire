"""Import citations from MD files into md-acquire specs.

One citation per line or markdown bullet. Supported shapes:

    Title | Author | 2011 | 978-0-374-53355-7 | doi:10.1/x     (pipe/semicolon fields)
    Title | Author                                             (2-field row)
    Surname, A. (2011). Title. Venue. ISBN 978-0-374-53355-7   (APA-ish prose)
    Title -- Author, 2006                                      (dash prose)

DOI / ISBN anchors are picked out of any shape; runtime enrichment fills
missing ISBNs later, so only the title matters for acceptance. A line with no
usable title goes to ``specs/citations-unparsed.txt`` - review that file after
importing. Re-importing is idempotent: same slug -> same file contents;
intra-run duplicates get -2, -3 suffixes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from .models import WorkSpec

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"']+)", re.I)
_ISBN13_RE = re.compile(r"\b(97[89][0-9\- ]{9,13}[0-9Xx])\b")
_ISBN10_RE = re.compile(r"\bISBN(?:-10)?[:\s]+([0-9][0-9\- ]{7,12}[0-9Xx])", re.I)
_YEAR_PAREN_RE = re.compile(r"\(((?:19|20)\d{2})\)")
_YEAR_BARE_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_BULLET_RE = re.compile(r"^\s*(?:[-*+>]|\d+[.)])\s*")


def _digits(text: str) -> str:
    return re.sub(r"[^0-9Xx]", "", text)


def _clean(text: str) -> str:
    text = _BULLET_RE.sub("", text.strip())
    text = re.sub(r"[*`]+", "", text)                    # markdown emphasis / backticks
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)          # snake_case -> spaces
    text = re.sub(r"^[*_`\s]+|[*_`\s]+$", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,;-")


def _first_author(authors_raw: str) -> str | None:
    """Conservative: one author for lookup quality (adapters query authors[0])."""
    s = _clean(authors_raw).rstrip(",;")
    if not s:
        return None
    low = s.lower()
    for sep in (" et al.", " and ", " & ", " + "):
        i = low.find(sep)
        if i > 0:
            s = s[:i].rstrip(",;")
            break
    if "," in s:
        s = re.split(r",\s*", s)[0]
    s = s.strip()
    if not s or len(s.split()) > 5:
        return None
    return s


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "spec"


def _isbn_from_text(text: str) -> str | None:
    digits = None
    m13 = _ISBN13_RE.search(text)
    if m13:
        d = _digits(m13.group(1))
        digits = d if len(d) == 13 else None
    if not digits:
        m10 = _ISBN10_RE.search(text)
        if m10:
            d = _digits(m10.group(1))
            digits = d if len(d) == 10 else None
    return digits


def _doi_from_text(text: str) -> str | None:
    m = _DOI_RE.search(text)
    return m.group(1).rstrip(".),") if m else None


def _year_from_text(text: str) -> int | None:
    m = _YEAR_PAREN_RE.search(text) or _YEAR_BARE_RE.search(text)
    return int(m.group(1)) if m else None


def parse_line(raw: str) -> WorkSpec | None:
    """Return a WorkSpec from one citation line, or None when the title is unrecognizable."""
    line = _clean(raw)
    if len(line) < 3:
        return None

    isbn = _isbn_from_text(line)
    doi = _doi_from_text(line)

    title: str | None = None
    authors_raw: str | None = None
    year: int | None = None
    title_explicit = False      # True when an explicit column named the title

    # Shape 1: pipe/semicolon field rows (2+ fields; parts[0] is the title)
    if "|" in line or ";" in line:
        parts = [p for p in (s.strip() for s in re.split(r"\s*[|;]\s*", line)) if p]
        if len(parts) >= 2 and len(parts[0]) >= 3:
            title = parts[0]
            title_explicit = True
            p1 = parts[1]
            if _YEAR_BARE_RE.fullmatch(p1):
                year = int(p1)                      # second column is a year, not an author
            else:
                authors_raw = p1
                if year is None:
                    year = _year_from_text(p1)
                if not isbn:
                    isbn = _isbn_from_text(p1)
                if not doi:
                    doi = _doi_from_text(p1)
            for p in parts[2:]:
                ym = _YEAR_BARE_RE.fullmatch(p)
                if ym:
                    if year is None:
                        year = int(p)
                    continue
                if not isbn:
                    isbn = _isbn_from_text(p)
                if not doi:
                    doi = _doi_from_text(p)

    # Shape 2: APA-ish prose with a parenthesized year
    if title is None:
        ym = _YEAR_PAREN_RE.search(line)
        if ym:
            authors_raw = line[: ym.start()].rstrip(" .,-:")
            rest = line[ym.end():].lstrip(". ")
            year = int(ym.group(1))
            title = (rest.split(". ")[0] if ". " in rest else rest).rstrip(".")
            if len(title.split()) < 2:
                title = None                        # too short to be a real title

    # Shape 3: "Title -- Author, 2006"
    if title is None:
        dash = re.search(r"\s(--|–|—)\s", line)
        if dash:
            title = line[: dash.start()].rstrip(",;- ")
            after = line[dash.end():]
            authors_raw = _YEAR_BARE_RE.split(after)[0].strip(" ,;-")
            year = _year_from_text(after)
            if len(title.split()) < 2:
                title = None

    if not title or (not title_explicit and len(title.split()) < 2):
        return None

    authors = []
    if authors_raw:
        a = _first_author(authors_raw)
        if a and a.lower() not in title.lower():    # never "the title itself" as an author
            authors = [a]

    note = f"Imported by pipeline.citations from a citations file. Original line: {line}"
    return WorkSpec(
        key=_slug(title),          # final unique key applied by the caller
        title=title,
        authors=authors,
        isbn13=isbn,
        doi=doi,
        year_min=year,
        edition_pref="any",
        formats=["epub", "pdf"],
        priority="open_access",
        notes=note,
    )


def _spec_md(spec: WorkSpec) -> str:
    fm: dict = {"title": spec.title}
    if spec.authors:
        fm["authors"] = spec.authors
    if spec.isbn13:
        fm["isbn13"] = spec.isbn13
    if spec.doi:
        fm["doi"] = spec.doi
    if spec.year_min:
        fm["year_min"] = spec.year_min
    fm["edition_pref"] = spec.edition_pref
    fm["formats"] = spec.formats
    fm["priority"] = spec.priority
    return ("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip("\n")
            + "\n---\n\n" + spec.notes + "\n")


def import_lines(lines: list[str], out_dir: Path,
                 source_label: str = "citations") -> tuple[list[str], list[tuple[int, str, str]]]:
    """Write one spec per recognized line. Returns (written_slugs, unparsed[(ln, text, reason)])."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    used: dict[str, int] = {}
    unparsed: list[tuple[int, str, str]] = []
    for i, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            spec = parse_line(raw)
        except Exception:
            spec = None
        if spec is None:
            unparsed.append((i, raw.strip(), "no recognizable title shape"))
            continue
        slug = spec.key
        if slug in used:
            used[slug] += 1
            slug = f"{slug}-{used[slug]}"
        else:
            used[slug] = 1
        spec.key = slug
        dest = out_dir / f"{slug}.md"
        dest.write_text(_spec_md(spec), encoding="utf-8")
        written.append(slug)
    if unparsed:
        rep = out_dir / "citations-unparsed.txt"
        with open(rep, "a", encoding="utf-8") as fh:
            fh.write(f"# from {source_label}\n")
            for ln, text, why in unparsed:
                fh.write(f"line {ln} ({why}): {text}\n")
    return written, unparsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        "md-acquire-citations",
        description="Turn MD citation lists into md-acquire spec files (one citation per line/bullet).",
    )
    parser.add_argument("files", nargs="+", help="MD files with citation lines")
    parser.add_argument("--out", default="specs", help="spec output directory (default specs/)")
    args = parser.parse_args(argv)

    total_written: list[str] = []
    unparsed_count = 0
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"missing: {f}")
            return 1
        written, unparsed = import_lines(
            p.read_text(encoding="utf-8").splitlines(), Path(args.out), source_label=p.name
        )
        total_written += written
        unparsed_count += len(unparsed)
        print(f"{p.name}: {len(written)} spec(s) written, {len(unparsed)} line(s) unparsed")

    if unparsed_count:
        print(f"review: {Path(args.out) / 'citations-unparsed.txt'}")
    print(f"total: {len(total_written)} specs in {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())