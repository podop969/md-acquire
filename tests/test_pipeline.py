"""Offline tests: no network. Fake Client, canned adapter payloads, real files."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from pipeline.adapters.gutenberg import GutenbergAdapter
from pipeline.adapters.openlibrary import OpenLibraryAdapter
from pipeline.config import Config
from pipeline.download import filename_for, looks_like_html, safe_name, validate
from pipeline.handoff import manual_links
from pipeline.http import Client
from pipeline.models import Candidate, WorkSpec
from pipeline.report import write
from pipeline.spec import parse_file


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeClient:
    """Records requested params; returns queued responses per URL substring."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self.queue: dict[str, FakeResponse] = {}

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, params))
        for key, resp in self.queue.items():
            if key in url:
                return resp
        raise AssertionError(f"unexpected URL: {url}")


# -- spec parsing --

def test_parse_spec_full(tmp_path: Path):
    p = tmp_path / "t.md"
    p.write_text(
        "---\ntitle: 'Book One'\nauthors: ['A. Author']\nisbn13: '978-0-306-40615-7'\n"
        "doi: 'https://doi.org/10.1/xyz'\nyear_min: 1999\nformats: ['pdf']\n---\n\nnotes here\n",
        encoding="utf-8",
    )
    spec = parse_file(p)
    assert spec.title == "Book One"
    assert spec.isbn13 == "9780306406157"
    assert spec.doi == "10.1/xyz"
    assert spec.formats == ["pdf"]


def test_parse_spec_requires_title(tmp_path: Path):
    p = tmp_path / "bad.md"
    p.write_text("---\nauthors: ['x']\n---\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(p)


# -- naming / validation --

def test_safe_name_windows_reserved():
    assert safe_name("CON") == "_CON"
    assert safe_name('a<b>c:"d/e\\f|g?h*i') == "a_b_c__d_e_f_g_h_i"
    assert safe_name("  spaced. .") == "spaced"


def test_filename_for():
    spec = WorkSpec(key="k", title="My Book", authors=["Jo, Longname "])
    cand = Candidate(source="s", url="u", fmt="epub")
    assert filename_for(spec, cand) == "My Book - Jo, Longname.epub"


def test_validate_pdf_magic(tmp_path: Path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.7 rest")
    validate(p, "pdf")
    p.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        validate(p, "pdf")


def test_validate_epub(tmp_path: Path):
    p = tmp_path / "a.epub"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", "<x/>")
    validate(p, "epub")
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/zip")
    with pytest.raises(ValueError):
        validate(p, "epub")


def test_looks_like_html(tmp_path: Path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"  <html><body>rate limited</body></html>")
    assert looks_like_html(p)


# -- adapters (offline, canned payloads) --

ARXIV_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T17:57:34Z</published>
  </entry>
</feed>"""


def test_arxiv_lookup_scores_and_parses():
    from pipeline.adapters.arxiv import ArxivAdapter
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["arxiv"])
    fc = FakeClient()
    fc.queue["export.arxiv.org"] = FakeResponse(200, ARXIV_ATOM)
    spec = WorkSpec(key="k", title="Attention Is All You Need", formats=["pdf"])
    cands = ArxivAdapter(cfg).lookup(fc, spec)
    assert len(cands) == 1
    assert cands[0].url == "https://arxiv.org/pdf/1706.03762v7"
    assert cands[0].year == 2017
    assert cands[0].score == 85


GUT = {"results": [{
    "id": 1342, "title": "Pride and Prejudice",
    "authors": [{"name": "Austen, Jane", "birth_year": 1775, "death_year": 1817}],
    "formats": {"application/epub+zip": "https://www.gutenberg.org/ebooks/1342.epub3.images",
                "application/pdf": "https://www.gutenberg.org/ebooks/1342.pdf.images"},
}]}


def test_gutenberg_exact_match_two_formats():
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["gutenberg"])
    fc = FakeClient()
    fc.queue["gutendex.com"] = FakeResponse(json_data=GUT)
    spec = WorkSpec(key="k", title="Pride and Prejudice", formats=["epub", "pdf"])
    cands = GutenbergAdapter(cfg).lookup(fc, spec)
    fmts = {c.fmt for c in cands}
    assert fmts == {"epub", "pdf"}
    assert all(c.score == 90 for c in cands)


def test_gutenberg_gutendex_failure_returns_empty():
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["gutenberg"])
    fc = FakeClient()
    fc.queue["gutendex.com"] = FakeResponse(503)
    spec = WorkSpec(key="k", title="Whatever", formats=["epub"])
    assert GutenbergAdapter(cfg).lookup(fc, spec) == []


OL = {"docs": [{
    "title": "A Public Book", "author_name": ["An Author"],
    "first_publish_year": 1955, "ebook_access": "public",
    "edition_key": ["OL123M"], "ia": ["apublicbook0000auth"],
}]}


def test_openlibrary_only_public():
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["openlibrary"])
    fc = FakeClient()
    fc.queue["openlibrary.org"] = FakeResponse(json_data=OL)
    spec = WorkSpec(key="k", title="A Public Book", year_min=1950, formats=["pdf"])
    cands = OpenLibraryAdapter(cfg).lookup(fc, spec)
    assert len(cands) == 1
    assert cands[0].url.startswith("https://archive.org/download/")
    assert cands[0].year == 1955 and cands[0].score == 93  # 88 exact + 5 year


OL_BORROW = {"docs": [{"title": "Borrow Book", "ebook_access": "borrowable",
                       "ia": ["x1"], "edition_key": ["OL9M"]}]}


def test_openlibrary_borrowable_becomes_hint_not_candidate():
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["openlibrary"])
    fc = FakeClient()
    fc.queue["openlibrary.org"] = FakeResponse(json_data=OL_BORROW)
    spec = WorkSpec(key="k", title="Borrow Book", formats=["pdf"])
    adapter = OpenLibraryAdapter(cfg)
    assert adapter.lookup(fc, spec) == []
    assert adapter.borrow_hints and "openlibrary.org/books/OL9M" in adapter.borrow_hints[0]


UP = {"best_oa_location": {"url_for_pdf": "https://oa.example/paper.pdf",
                           "host_type": "repository", "license": "cc-by"},
      "oa_locations": [{"url_for_pdf": "https://oa.example/paper.pdf"},
                       {"url": "https://landing.example/paper"}],
      "year": 2017}


def test_unpaywall_prefers_best_pdf_dedupes():
    from pipeline.adapters.unpaywall import UnpaywallAdapter
    cfg = Config(Path("."), Path("."), "e@x.org", 1.0, 5, 1, ["unpaywall"])
    fc = FakeClient()
    fc.queue["api.unpaywall.org"] = FakeResponse(json_data=UP)
    spec = WorkSpec(key="k", title="A Paper", doi="10.1/x", formats=["pdf"])
    cands = UnpaywallAdapter(cfg).lookup(fc, spec)
    urls = [c.url for c in cands]
    assert urls[0] == "https://oa.example/paper.pdf"
    assert cands[0].score == 70 and cands[0].year == 2017
    assert len(urls) == len(set(urls)) == 2


def test_unpaywall_needs_doi_and_email():
    from pipeline.adapters.unpaywall import UnpaywallAdapter
    cfg = Config(Path("."), Path("."), "", 1.0, 5, 1, ["unpaywall"])
    fc = FakeClient()
    spec = WorkSpec(key="k", title="A Paper", doi="10.1/x")
    assert UnpaywallAdapter(cfg).lookup(fc, spec) == []


# -- handoff links --

def test_manual_links_present_and_never_downloaded():
    spec = WorkSpec(key="k", title="Thinking, Fast and Slow",
                    authors=["Daniel Kahneman"], isbn13="9780374533557")
    links = manual_links(spec)
    sources = [l["source"] for l in links]
    assert "annas-archive" in sources and "openlibrary-search" in sources
    assert any("annas-archive.org/search" in l["url"] for l in links)
    assert any("9780374533557" in l["url"] for l in links)
    # adapters/__init__ whitelists fetch targets; none of these may be fetchable
    from pipeline.adapters import CLASSES
    for l in links:
        assert l["source"] not in CLASSES


# -- report --

def test_report_writes_wanted_with_links(tmp_path: Path):
    from pipeline.models import Resolution
    spec = WorkSpec(key="k", title="Nonopen Book", authors=["A. Writer"])
    res = Resolution(spec, "not_found", detail="nothing open",
                     manual=manual_links(spec))
    rp, wp = write([res], tmp_path)
    text = wp.read_text(encoding="utf-8")
    assert "annas-archive" in text and "[Anna's Archive" in text
    report = rp.read_text(encoding="utf-8")
    assert "unresolved: 1" in report


def test_manifest_entry(tmp_path: Path):
    from pipeline.manifest import Manifest
    spec = WorkSpec(key="k", title="T")
    cand = Candidate(source="gutenberg", url="u", fmt="epub", license="PD")
    m = Manifest(tmp_path / "manifest.jsonl")
    m.record(spec, cand, Path("f.epub"), "abc")
    entry = json.loads((tmp_path / "manifest.jsonl").read_text("utf-8"))
    assert entry["source"] == "gutenberg" and entry["sha256"] == "abc"