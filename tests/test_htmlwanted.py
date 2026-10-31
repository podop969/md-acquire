"""Offline tests for the wanted.html renderer."""
from __future__ import annotations

from pathlib import Path

from pipeline.htmlwanted import build, parse_wanted, render

WANTED_SAMPLE = """# Wanted

No open-access copy downloaded for these. Decide each one yourself:
the links are search pages, not downloads.

## Thinking, Fast and Slow
- authors: Daniel Kahneman
- ISBN-13: 9780374533557
- year window: 2011+
- spec file: specs\\thinking-fast-and-slow.md
- detail: no open-access source had a matching copy
- Open Library has a borrowable copy - borrow manually: https://openlibrary.org/books/OL62456765M
- search manually:
  - [Anna's Archive (public search page)](https://annas-archive.org/search?q=x)
  - [WorldCat by ISBN 9780374533557](https://search.worldcat.org/search?q=bn%3A9780374533557)
"""


def test_parse_wanted_extracts_work():
    works = parse_wanted(WANTED_SAMPLE)
    assert len(works) == 1
    w = works[0]
    assert w["title"] == "Thinking, Fast and Slow"
    assert [l[0] for l in w["links"]] == [
        "Anna's Archive (public search page)", "WorldCat by ISBN 9780374533557"]
    assert w["spec"].endswith("thinking-fast-and-slow.md")
    assert w["detail"] == "no open-access source had a matching copy"
    assert any("borrowable" in m for m in w["meta"])


def test_parse_wanted_empty():
    assert parse_wanted("# Wanted\n\nNothing here.\n") == []


def test_render_escapes():
    html_out = render([{"title": 'Book "X" & <More>', "meta": ["meta<1>"],
                        "links": [("Go", "https://a.b/c?x=1&y=2")],
                        "detail": "why", "spec": "s.md"}])
    assert "Book &quot;X&quot; &amp; &lt;More&gt;" in html_out
    assert 'href="https://a.b/c?x=1&amp;y=2"' in html_out
    assert 'class="btn"' in html_out


def test_render_nothing_wanted():
    assert "Nothing wanted" in render([])


def test_render_turns_borrow_url_into_a_link():
    html_out = render([{
        "title": "Thinking, Fast and Slow",
        "meta": ["Open Library has a borrowable copy - borrow manually: "
                 "https://openlibrary.org/books/OL62456765M"],
        "links": [],
        "detail": "",
        "spec": "specs/thinking-fast-and-slow.md",
    }])
    assert 'href="https://openlibrary.org/books/OL62456765M"' in html_out
    assert ">https://openlibrary.org/books/OL62456765M</a>" in html_out
    assert "borrow manually:" in html_out


def test_build_writes_html(tmp_path: Path):
    p = tmp_path / "wanted.md"
    p.write_text(WANTED_SAMPLE, encoding="utf-8")
    out = build(p)
    assert out.name == "wanted.html"
    text = out.read_text(encoding="utf-8")
    assert "Thinking, Fast and Slow" in text
    assert "annas-archive.org/search" in text