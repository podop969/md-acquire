from __future__ import annotations

import pytest

from pipeline.spec import load_from, parse_file


def test_parses_frontmatter_and_body(tmp_path, spec_markdown):
    p = tmp_path / "thinking.md"
    p.write_text(spec_markdown, encoding="utf-8")

    spec = parse_file(p)

    assert spec.key == "thinking"
    assert spec.title == "Thinking, Fast and Slow"
    assert spec.authors == ["Daniel Kahneman"]
    assert spec.isbn13 == "9780374533557"          # hyphens stripped
    assert spec.formats == ["epub", "pdf"]
    assert "Why I need this edition." in spec.notes


def test_defaults_when_optional_fields_absent(tmp_path):
    p = tmp_path / "minimal.md"
    p.write_text('---\ntitle: "Bare Minimum"\n---\n', encoding="utf-8")

    spec = parse_file(p)

    assert spec.formats == ["epub", "pdf"]
    assert spec.priority == "open_access"
    assert spec.edition_pref == "latest"
    assert spec.authors == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://doi.org/10.1000/xyz", "10.1000/xyz"),
        ("http://dx.doi.org/10.1000/xyz", "10.1000/xyz"),
        ("doi: 10.1000/xyz", "10.1000/xyz"),
        ("10.1000/xyz", "10.1000/xyz"),
        ("", None),
        (None, None),
    ],
)
def test_doi_normalization(tmp_path, raw, expected):
    body = f'---\ntitle: "T"\ndoi: "{raw}"\n---\n' if raw is not None else '---\ntitle: "T"\n---\n'
    p = tmp_path / "doi.md"
    p.write_text(body, encoding="utf-8")

    assert parse_file(p).doi == expected


def test_missing_frontmatter_rejected(tmp_path):
    p = tmp_path / "noheader.md"
    p.write_text("just prose, no frontmatter\n", encoding="utf-8")

    with pytest.raises(ValueError, match="frontmatter"):
        parse_file(p)


def test_missing_title_rejected(tmp_path):
    p = tmp_path / "notitle.md"
    p.write_text("---\nauthors: [\"X\"]\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="title"):
        parse_file(p)


def test_load_dir_sorted_and_complete(tmp_path):
    (tmp_path / "b.md").write_text('---\ntitle: "B"\n---\n', encoding="utf-8")
    (tmp_path / "a.md").write_text('---\ntitle: "A"\n---\n', encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("nope", encoding="utf-8")

    guides = load_from([tmp_path])          # load_from == this repo's load_dir

    assert [s.key for s in guides] == ["a", "b"]