"""Offline tests for the citations importer."""
from __future__ import annotations

from pathlib import Path

from pipeline.citations import _slug, import_lines, parse_line
from pipeline.spec import parse_file


def test_slug():
    assert _slug("Attention Is All You Need") == "attention-is-all-you-need"
    assert _slug("It's a  Book?!") == "it-s-a-book"


def test_pipe_record_full():
    s = parse_line("Thinking, Fast and Slow | Daniel Kahneman | 2011 | 978-0-374-53355-7")
    assert s is not None
    assert s.title == "Thinking, Fast and Slow"
    assert s.authors == ["Daniel Kahneman"]
    assert s.isbn13 == "9780374533557"
    assert s.year_min == 2011


def test_two_field_pipe():
    s = parse_line("The Wealth of Networks | Yochai Benkler")
    assert s is not None and s.title == "The Wealth of Networks"
    assert s.authors == ["Yochai Benkler"]


def test_apa_prose():
    s = parse_line("Kahneman, D. (2011). Thinking, Fast and Slow. Farrar, Straus.")
    assert s is not None
    assert s.title == "Thinking, Fast and Slow"
    assert s.authors == ["Kahneman"]
    assert s.year_min == 2011


def test_dash_prose():
    s = parse_line("The Wealth of Networks -- Yochai Benkler, 2006")
    assert s is not None
    assert s.title == "The Wealth of Networks"
    assert s.authors == ["Yochai Benkler"]
    assert s.year_min == 2006


def test_anchors_from_prose():
    s = parse_line("Benkler, Y. (2006). The Wealth of Networks. Yale UP. doi:10.1000/xyz.1")
    assert s is not None
    assert s.title == "The Wealth of Networks"
    assert s.authors == ["Benkler"]
    assert s.year_min == 2006
    assert s.doi == "10.1000/xyz.1"


def test_bullets_and_markup_stripped():
    s = parse_line("- *Pride and Prejudice* | Jane Austen | 1813")
    assert s is not None
    assert s.title == "Pride and Prejudice"


def test_garbage_is_unparsed():
    assert parse_line("hi") is None
    assert parse_line("") is None


def test_short_title_rejected():
    # explicit columns keep even one-word titles; bare prose needs 2+ words
    s = parse_line("Dune | Frank Herbert")
    assert s is not None and s.title == "Dune"
    assert parse_line("Dune") is None  # single word, no shape -> unparsed


def test_import_roundtrip(tmp_path: Path):
    lines = [
        "Thinking, Fast and Slow | Daniel Kahneman | 2011 | 978-0-374-53355-7",
        "",
        "Kahneman, D. (2011). Thinking, Fast and Slow. Publisher.",  # dupe slug -> -2
        "The Wealth of Networks | Yochai Benkler",
        "hello there",
    ]
    specs = tmp_path / "specs"
    written, unparsed = import_lines(lines, specs)
    assert written == ["thinking-fast-and-slow", "thinking-fast-and-slow-2",
                       "the-wealth-of-networks"]
    assert len(unparsed) == 1 and unparsed[0][2].startswith("no")
    parsed = parse_file(specs / "thinking-fast-and-slow.md")
    assert parsed.title == "Thinking, Fast and Slow"
    assert parsed.isbn13 == "9780374533557"
    unparsed_txt = (specs / "citations-unparsed.txt").read_text("utf-8")
    assert "line 5" in unparsed_txt


def test_import_idempotent_content(tmp_path: Path):
    lines = ["The Wealth of Networks | Yochai Benkler"]
    import_lines(lines, tmp_path / "s")  # writes the same spec twice? no - two runs
    first = (tmp_path / "s" / "the-wealth-of-networks.md").read_text("utf-8")
    import_lines(lines, tmp_path / "s")
    again = (tmp_path / "s" / "the-wealth-of-networks.md").read_text("utf-8")
    assert first == again  # same slug overwrites with same bytes, no -2