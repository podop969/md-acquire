# Offline tests for every adapter, through the conftest FakeClient seam.
# openlibrary is included: it is this repo's 4th adapter (absent from the
# integration guide, which predates it).
from __future__ import annotations

import pytest

from pipeline.adapters.arxiv import ArxivAdapter
from pipeline.adapters.gutenberg import GutenbergAdapter
from pipeline.adapters.openlibrary import OpenLibraryAdapter
from pipeline.adapters.unpaywall import UnpaywallAdapter
from tests.conftest import FakeResponse

ARXIV_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Thinking, Fast and Slow</title>
    <published>2024-01-02T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>Something Else Entirely</title>
    <published>2023-06-01T00:00:00Z</published>
  </entry>
</feed>
"""


def test_arxiv_builds_pdf_candidates_and_scores_exact_match(fake_client, make_config, make_spec):
    client = fake_client({"export.arxiv.org": FakeResponse(text=ARXIV_XML)})
    adapter = ArxivAdapter(make_config())

    out = adapter.lookup(client, make_spec())

    assert len(out) == 2
    assert out[0].url == "https://arxiv.org/pdf/2401.00001v1"
    assert out[0].fmt == "pdf"
    assert out[0].year == 2024
    assert out[0].score == 85                       # exact title
    assert out[1].score == 55                       # partial


def test_arxiv_returns_empty_on_non_200(fake_client, make_config, make_spec):
    client = fake_client({"export.arxiv.org": FakeResponse(503)})

    assert ArxivAdapter(make_config()).lookup(client, make_spec()) == []


def test_arxiv_queries_title_and_first_author(fake_client, make_config, make_spec):
    client = fake_client({"export.arxiv.org": FakeResponse(text=ARXIV_XML)})

    ArxivAdapter(make_config()).lookup(client, make_spec())

    url, kwargs = client.calls[0]
    assert "export.arxiv.org" in url
    q = kwargs["params"]["search_query"]
    assert 'ti:"Thinking, Fast and Slow"' in q
    assert 'au:"Daniel Kahneman"' in q


# --- unpaywall ---


def test_unpaywall_requires_doi_and_email(fake_client, make_config, make_spec):
    cfg = make_config(contact_email="")
    client = fake_client({})

    assert UnpaywallAdapter(cfg).lookup(client, make_spec(doi="10.1/x")) == []
    assert client.calls == []


def test_unpaywall_puts_best_location_first(fake_client, make_config, make_spec):
    cfg = make_config()
    payload = {
        "best_oa_location": {"url_for_pdf": "https://repo/best.pdf", "license": "cc-by", "host_type": "repository"},
        "oa_locations": [
            {"url": "https://repo/other", "license": "cc-by-nc", "host_type": "repository"},
            {"url_for_pdf": "https://repo/best.pdf", "license": "cc-by", "host_type": "repository"},
        ],
        "license": "cc-by",
    }
    client = fake_client({"api.unpaywall.org": FakeResponse(json_data=payload)})

    out = UnpaywallAdapter(cfg).lookup(client, make_spec(doi="10.1/x"))

    assert out[0].url == "https://repo/best.pdf"
    assert out[0].score == 70
    assert all(c.fmt == "pdf" for c in out)
    urls = [c.url for c in out]
    assert len(urls) == len(set(urls))              # deduped


def test_unpaywall_empty_when_no_oa(fake_client, make_config, make_spec):
    client = fake_client({"api.unpaywall.org": FakeResponse(json_data={"oa_locations": []})})

    assert UnpaywallAdapter(make_config()).lookup(client, make_spec(doi="10.1/x")) == []


def test_unpaywall_passes_contact_email(fake_client, make_config, make_spec):
    client = fake_client({"api.unpaywall.org": FakeResponse(json_data={})})
    cfg = make_config(contact_email="me@example.org")

    UnpaywallAdapter(cfg).lookup(client, make_spec(doi="10.1/x"))

    url, kwargs = client.calls[0]
    assert kwargs["params"]["email"] == "me@example.org"


# --- gutenberg ---


def test_gutenberg_extracts_epub_and_pdf_only(fake_client, make_config, make_spec):
    payload = {
        "results": [
            {
                "id": 1661,
                "title": "Thinking, Fast and Slow",
                "formats": {
                    "application/epub+zip": "https://gutenberg/1.epub",
                    "application/pdf": "https://gutenberg/1.pdf",
                    "text/plain; charset=us-ascii": "https://gutenberg/1.txt",
                },
            }
        ]
    }
    client = fake_client({"gutendex.com": FakeResponse(json_data=payload)})

    out = GutenbergAdapter(make_config()).lookup(client, make_spec())

    formats = sorted(c.fmt for c in out)
    assert formats == ["epub", "pdf"]
    assert all(c.score == 90 for c in out)
    assert all("Public domain" in c.license for c in out)


def test_gutenberg_empty_on_error(fake_client, make_config, make_spec):
    client = fake_client({"gutendex.com": FakeResponse(502)})

    assert GutenbergAdapter(make_config()).lookup(client, make_spec()) == []


def test_gutenberg_nonexact_never_shadows_exact(fake_client, make_config, make_spec):
    payload = {
        "results": [
            {"id": 1, "title": "Something Else Entirely",
             "formats": {"application/epub+zip": "https://g/else.epub"}},
            {"id": 2, "title": "Thinking, Fast and Slow",
             "formats": {"application/epub+zip": "https://g/exact.epub"}},
        ]
    }
    client = fake_client({"gutendex.com": FakeResponse(json_data=payload)})

    out = GutenbergAdapter(make_config()).lookup(client, make_spec())

    assert [c.url for c in out if c.fmt == "epub"] == ["https://g/exact.epub"]
    assert all(c.score == 90 for c in out)


# --- openlibrary (repo-specific adapter) ---


def test_openlibrary_public_scan_scores_exact_plus_year(fake_client, make_config, make_spec):
    payload = {"docs": [{
        "title": "Thinking, Fast and Slow",
        "first_publish_year": 2011,
        "ebook_access": "public",
        "edition_key": ["OL1M"],
        "ia": ["scan0000aaa"],
    }]}
    client = fake_client({"openlibrary.org": FakeResponse(json_data=payload)})
    spec = make_spec(year_min=2010, formats=["pdf"])

    out = OpenLibraryAdapter(make_config()).lookup(client, spec)

    assert len(out) == 1
    assert out[0].url == "https://archive.org/download/scan0000aaa/scan0000aaa.pdf"
    assert out[0].score == 93                       # 88 exact + 5 year window
    assert out[0].fmt == "pdf"


def test_openlibrary_borrowable_becomes_hint_not_candidate(fake_client, make_config, make_spec):
    payload = {"docs": [{"title": "Borrow Book", "ebook_access": "borrowable",
                         "ia": ["x1"], "edition_key": ["OL9M"]}]}
    client = fake_client({"openlibrary.org": FakeResponse(json_data=payload)})
    adapter = OpenLibraryAdapter(make_config())

    out = adapter.lookup(client, make_spec(title="Borrow Book"))

    assert out == []                                # never a fetch candidate
    assert adapter.borrow_hints
    assert "openlibrary.org/books/OL9M" in adapter.borrow_hints[0]


def test_openlibrary_nonpublic_is_skipped_silently(fake_client, make_config, make_spec):
    payload = {"docs": [{"title": "Print Disabled Book",
                         "ebook_access": "printdisabled", "ia": ["x"]}]}
    client = fake_client({"openlibrary.org": FakeResponse(json_data=payload)})
    adapter = OpenLibraryAdapter(make_config())

    assert adapter.lookup(client, make_spec(title="Print Disabled Book")) == []
    assert adapter.borrow_hints                     # still surfaced as a hint


def test_openlibrary_retries_title_only_when_author_narrows_to_zero(fake_client, make_config, make_spec):
    hits = {"docs": [{"title": "Thinking, Fast and Slow", "ebook_access": "public",
                      "edition_key": ["OL2M"], "ia": ["ia2"]}]}
    # first (with author) -> no docs; retry (without author) -> one hit
    responses = iter([FakeResponse(json_data={"docs": []}), FakeResponse(json_data=hits)])
    client = fake_client({})
    client.handler = lambda url, kwargs: next(responses)
    adapter = OpenLibraryAdapter(make_config())

    out = adapter.lookup(client, make_spec())

    assert len(out) == 1
    assert len(client.calls) == 2                   # author query + title-only retry