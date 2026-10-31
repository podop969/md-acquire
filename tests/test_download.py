# Offline tests for download/, validation, and cleanup semantics.
from __future__ import annotations

import zipfile

import pytest

from pipeline.download import download, filename_for, looks_like_html, safe_name, validate
from pipeline.models import Candidate
from tests.conftest import FakeResponse


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("normal title", "normal title"),
        ("a/b:c*?", "a_b_c__"),
        ("  padded  ", "padded"),
        ("CON", "_CON"),
        ("lpt1", "_lpt1"),
        ("", "untitled"),
    ],
)
def test_safe_name(raw, expected):
    assert safe_name(raw) == expected


def test_safe_name_truncates():
    assert len(safe_name("x" * 500)) == 120


def test_filename_for_composes_title_author_format(make_spec):
    spec = make_spec()
    cand = Candidate(source="mock", url="http://x", fmt="epub")

    assert filename_for(spec, cand) == "Thinking, Fast and Slow - Daniel Kahneman.epub"


def test_filename_for_without_authors(make_spec):
    spec = make_spec(authors=[])
    cand = Candidate(source="mock", url="http://x", fmt="pdf")

    assert filename_for(spec, cand) == "Thinking, Fast and Slow.pdf"


# --- validate ---


def test_validate_accepts_pdf(tmp_path, pdf_bytes):
    p = tmp_path / "ok.pdf"
    p.write_bytes(pdf_bytes)

    validate(p, "pdf")                              # no raise


def test_validate_rejects_non_pdf(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"<html>nope</html>")

    with pytest.raises(ValueError, match="not a PDF"):
        validate(p, "pdf")


def test_validate_accepts_epub(make_epub):
    validate(make_epub(), "epub")


def test_validate_rejects_wrong_mimetype(make_epub):
    with pytest.raises(ValueError, match="mimetype"):
        validate(make_epub(mimetype=b"text/plain"), "epub")


def test_validate_rejects_missing_mimetype(tmp_path):
    p = tmp_path / "nomime.epub"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("content.opf", "<package/>")

    with pytest.raises(ValueError, match="mimetype"):
        validate(p, "epub")


def test_validate_rejects_non_zip(tmp_path):
    p = tmp_path / "text.epub"
    p.write_text("not a zip")

    with pytest.raises(ValueError, match="zip"):
        validate(p, "epub")


def test_validate_rejects_unknown_format(tmp_path):
    p = tmp_path / "x.mobi"
    p.write_bytes(b"x")

    with pytest.raises(ValueError, match="unsupported"):
        validate(p, "mobi")


def test_looks_like_html_detects_error_pages(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"   <html><body>rate limited</body></html>")

    assert looks_like_html(p)


# --- download ---


def test_download_writes_file_and_sha(fake_client, tmp_path, make_spec, pdf_bytes):
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf")

    saved, sha = download(client, cand, make_spec(), tmp_path)

    assert saved.exists()
    assert saved.read_bytes() == pdf_bytes
    assert len(sha) == 64
    assert not list(tmp_path.glob("*.part"))


def test_download_skips_existing_file(fake_client, tmp_path, make_spec, pdf_bytes):
    client = fake_client({})
    spec = make_spec()
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf")
    existing = tmp_path / filename_for(spec, cand)
    existing.write_bytes(pdf_bytes)

    saved, sha = download(client, cand, spec, tmp_path)

    assert saved == existing
    assert len(sha) == 64


def test_download_rejects_html_payload(fake_client, tmp_path, make_spec):
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=b"<html>", headers={"content-type": "text/html"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf")

    with pytest.raises(ValueError, match="HTML"):
        download(client, cand, make_spec(), tmp_path)

    assert not list(tmp_path.iterdir())


def test_download_cleans_up_partial_on_validation_failure(fake_client, tmp_path, make_spec):
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=b"garbage", headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf")

    with pytest.raises(ValueError):
        download(client, cand, make_spec(), tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_download_skips_network_when_file_exists(fake_client, tmp_path, make_spec, pdf_bytes):
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf")

    download(client, cand, make_spec(), tmp_path)   # first: real call
    first_calls = len(client.calls)
    saved, _ = download(client, cand, make_spec(), tmp_path)  # second: cache hit

    assert len(client.calls) == first_calls         # no second network hit
    assert saved.exists()