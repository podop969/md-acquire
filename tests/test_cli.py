# Offline end-to-end orchestration tests through pipeline.cli.run.
# Adapted from the integration guide to this repo's signature:
#   cli.run(cfg, spec_paths, only=None, dry_run=False)
from __future__ import annotations

from pathlib import Path

from pipeline import cli
from pipeline.models import Candidate
from tests.conftest import FakeResponse, wire_cli


SPEC_MD = """---
title: "Thinking, Fast and Slow"
authors: ["Daniel Kahneman"]
formats: ["pdf"]
---
Body.
"""


def test_end_to_end_saves_one_file_and_manifest(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")

    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)

    assert len(resolutions) == 1
    assert resolutions[0].status == "ok"
    saved = list(cfg.out_dir.glob("*.pdf"))
    assert len(saved) == 1 and saved[0].read_bytes() == pdf_bytes
    assert (cfg.out_dir / "manifest.jsonl").exists()
    assert (cfg.out_dir / "report.md").exists()
    assert (cfg.out_dir / "wanted.md").exists()


def test_dry_run_does_not_download(monkeypatch, make_config, fake_client, mock_adapter):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")
    client = fake_client(
        {"openlibrary.org": FakeResponse(json_data={"docs": []})}  # dry-run still enriches
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=True)

    assert resolutions[0].status == "ok"
    assert not list(cfg.out_dir.glob("*.pdf"))
    # The dry-run guarantee: no CANDIDATE url is ever touched.
    assert all("example.org" not in url for url, _ in client.calls)


def test_dry_run_enriches_missing_isbn_but_no_download(monkeypatch, make_config, fake_client, mock_adapter):
    """Dry-run must enrich (metadata is offline-usable) yet never fetch a candidate."""
    cfg = make_config()
    spec_md_no_isbn = SPEC_MD.replace('authors: ["Daniel Kahneman"]\n', "")  # isbn comes only from enrichment
    _ = spec_md_no_isbn
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")
    client = fake_client(
        {"openlibrary.org": FakeResponse(json_data={"docs": [{"isbn": ["9780374533557"]}]})}
    )
    wire_cli(monkeypatch, client, [mock_adapter([])])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=True)

    assert resolutions[0].status == "not_found"          # no candidates -> wanted.md path
    assert all("example.org" not in url for url, _ in client.calls)


def test_not_found_flows_into_wanted(monkeypatch, make_config, fake_client, mock_adapter):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")
    client = fake_client({})
    wire_cli(monkeypatch, client, [mock_adapter([])])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)

    assert resolutions[0].status == "not_found"
    wanted = (cfg.out_dir / "wanted.md").read_text(encoding="utf-8")
    assert "Thinking, Fast and Slow" in wanted
    assert "annas-archive" in wanted                 # manual handoff links included


def test_adapter_exception_recorded_not_fatal(monkeypatch, make_config, fake_client, mock_adapter):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")
    client = fake_client({})
    wire_cli(monkeypatch, client, [mock_adapter(raises=RuntimeError("boom"), name="broken")])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)

    assert resolutions[0].status == "not_found"
    assert "broken: boom" in resolutions[0].detail


def test_multiple_formats_pick_best_per_format(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes, make_epub):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(
        SPEC_MD.replace('["pdf"]', '["pdf", "epub"]'), encoding="utf-8"
    )
    epub = make_epub()

    def respond(url, kwargs):
        if url.endswith(".pdf"):
            return FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})
        return FakeResponse(content=Path(epub).read_bytes(), headers={"content-type": "application/epub+zip"})

    client = fake_client({"example.org/book.pdf": respond, "example.org/book.epub": respond})
    cands = [
        Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=60),
        Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=95),  # better pdf
        Candidate(source="mock", url="https://example.org/book.epub", fmt="epub", score=80),
    ]
    wire_cli(monkeypatch, client, [mock_adapter(cands)])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)

    names = sorted(p.suffix for p in resolutions[0].saved)
    assert names == [".epub", ".pdf"]
    assert len(list(cfg.out_dir.glob("*.pdf"))) == 1          # best-per-format only
    assert len(list(cfg.out_dir.glob("*.epub"))) == 1


def test_download_failure_falls_back_to_next_candidate(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes):
    """Scoring picks the highest score, but a failing download must not sink the spec."""
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")

    def respond(url, kwargs):
        if "openlibrary.org" in url:
            return FakeResponse(json_data={"docs": []})
        if url.endswith(".pdf"):
            if "bad" in url:
                return FakeResponse(content=b"<html>proxy error</html>", headers={"content-type": "text/html"})
            return FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})
        return FakeResponse(404)

    client = fake_client({"example.org": respond})
    cands = [
        Candidate(source="mock", url="https://example.org/bad.pdf", fmt="pdf", score=90),   # wins scoring
        Candidate(source="mock", url="https://example.org/good.pdf", fmt="pdf", score=70),  # fallback
    ]

    class FallbackAdapter(mock_adapter):
        def __init__(self):
            super().__init__(cands)

    wire_cli(monkeypatch, client, [FallbackAdapter()])

    resolutions = cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)

    assert resolutions[0].status == "ok"
    saved = list(cfg.out_dir.glob("*.pdf"))
    assert len(saved) == 1 and saved[0].read_bytes() == pdf_bytes
    assert (cfg.out_dir / "manifest.jsonl").read_text(encoding="utf-8").strip().count("\n") == 0


def test_only_filter(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes):
    cfg = make_config()
    for key in ("one", "two"):
        (cfg.specs_dir / f"{key}.md").write_text(
            f'---\ntitle: "{key.title()}"\nformats: ["pdf"]\n---\n', encoding="utf-8"
        )
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    resolutions = cli.run(cfg, [cfg.specs_dir], only={"two"}, dry_run=False)

    assert [r.spec.key for r in resolutions] == ["two"]


def test_rerun_is_idempotent(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes):
    cfg = make_config()
    (cfg.specs_dir / "demo.md").write_text(SPEC_MD, encoding="utf-8")
    client = fake_client(
        {
            # enrichment hits openlibrary every run; downloads are cached on disk
            "openlibrary.org": FakeResponse(json_data={"docs": []}),
            "example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"}),
        }
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)
    downloads_after_first = sum(1 for url, _ in client.calls if "example.org" in url)
    cli.run(cfg, [cfg.specs_dir], only=None, dry_run=False)
    downloads_after_second = sum(1 for url, _ in client.calls if "example.org" in url)

    assert downloads_after_second == downloads_after_first == 1  # second run skipped download
    assert len(list(cfg.out_dir.glob("*.pdf"))) == 1


def test_single_spec_file_as_source(monkeypatch, make_config, fake_client, mock_adapter, pdf_bytes):
    """--specs accepts a single .md file as well as a directory."""
    cfg = make_config()
    spec_file = cfg.specs_dir / "demo.md"
    spec_file.write_text(SPEC_MD, encoding="utf-8")
    client = fake_client(
        {"example.org/book.pdf": FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})}
    )
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    resolutions = cli.run(cfg, [spec_file], only=None, dry_run=False)

    assert [r.spec.key for r in resolutions] == ["demo"]
    assert resolutions[0].status == "ok"