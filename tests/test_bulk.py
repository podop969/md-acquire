# Offline tests for the resume-safe bulk runner.
from __future__ import annotations

import json
from pathlib import Path

from pipeline.bulk import (
    _read_manifest,
    completed_formats,
    pending_specs,
    run,
)
from pipeline.models import Candidate, WorkSpec
from tests.conftest import FakeResponse, wire_cli


def test_read_manifest_tolerates_bad_lines(tmp_path: Path):
    p = tmp_path / "manifest.jsonl"
    p.write_text(
        json.dumps({"key": "a", "format": "pdf", "saved_as": "a.pdf"}) + "\n"
        + "{ broken json\n"
        + "\n"
        + json.dumps({"key": "b", "format": "epub", "saved_as": "b.epub"}) + "\n",
        encoding="utf-8",
    )
    recs = _read_manifest(p)
    assert [r["key"] for r in recs] == ["a", "b"]
    assert _read_manifest(tmp_path / "missing.jsonl") == []


def test_completed_formats_requires_existing_files(tmp_path: Path):
    mf = tmp_path / "manifest.jsonl"
    mf.write_text(
        json.dumps({"key": "a", "format": "pdf", "saved_as": "a.pdf"}) + "\n"
        + json.dumps({"key": "b", "format": "pdf", "saved_as": "gone.pdf"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "a.pdf").write_bytes(b"%PDF- x")
    # b.pdf missing -> not done
    done = completed_formats(mf, tmp_path)
    assert done == {"a": {"pdf"}}


def test_pending_specs_logic():
    s1 = WorkSpec(key="a", title="A", formats=["pdf", "epub"])
    s2 = WorkSpec(key="b", title="B", formats=["pdf"])
    done = {"a": {"pdf"}, "b": {"pdf"}}

    assert pending_specs([s1, s2], done) == [s1]       # a missing epub
    assert pending_specs([s1, s2], {}) == [s1, s2]
    assert pending_specs([s1], done, force=True) == [s1]  # force re-fetches all
    assert pending_specs([s1], {"a": {"pdf", "epub"}}) == []  # complete


def test_run_returns_empty_when_no_specs(tmp_path: Path):
    from pipeline.config import Config

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    cfg = Config(specs_dir, tmp_path / "lib", "", 0.0, 5, 1, ["arxiv"])

    assert run(cfg) == []                                    # no specs, no crash


def test_bulk_end_to_end_resume(tmp_path: Path, monkeypatch, mock_adapter, pdf_bytes):
    """First pass fetches; re-run does nothing; --force re-runs the spec."""
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "demo.md").write_text(
        '---\ntitle: "Demo Book"\nformats: ["pdf"]\n---\n', encoding="utf-8"
    )
    lib = tmp_path / "library"

    from pipeline.config import Config

    cfg = Config(specs_dir, lib, "", 0.0, 5, 1, ["arxiv"])

    calls: list[tuple] = []

    class FakeBulkClient:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})

    client = FakeBulkClient()
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    adapters = [mock_adapter([cand])]

    import pipeline.cli as cli_mod
    monkeypatch.setattr(cli_mod, "Client", lambda *a, **k: client)
    monkeypatch.setattr(cli_mod, "build_adapters", lambda names, cfg: adapters)

    # 1st pass: downloads
    res = run(cfg)
    assert [r.status for r in res] == ["ok"]
    assert (lib / "Demo Book.pdf").exists()
    assert (lib / "manifest.jsonl").exists()
    assert calls, "expected a real network call through cli.run"

    # 2nd pass: everything complete -> no new calls
    calls.clear()
    assert run(cfg) == []
    assert calls == []

    # --force: re-fetch (file exists so download() skips network; manifest grows)
    res = run(cfg, force=True)
    assert [r.status for r in res] == ["ok"]
    assert len(list(lib.glob("*.pdf"))) == 1

    # a manifest entry whose file vanished -> pending again
    (lib / "Demo Book.pdf").unlink()
    calls.clear()
    res = run(cfg)
    assert [r.status for r in res] == ["ok"]
    assert calls, "deleted file must be re-fetched"


def test_bulk_skips_unparsable_specs(tmp_path: Path, monkeypatch, mock_adapter, pdf_bytes, capsys):
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "good.md").write_text('---\ntitle: "Good"\nformats: ["pdf"]\n---\n', encoding="utf-8")
    (specs_dir / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")

    from pipeline.config import Config

    cfg = Config(specs_dir, tmp_path / "lib", "", 0.0, 5, 1, ["arxiv"])

    client = type("C", (), {
        "get": staticmethod(lambda url, **k: FakeResponse(content=pdf_bytes,
                                                          headers={"content-type": "application/pdf"})),
    })()
    cand = Candidate(source="mock", url="https://example.org/book.pdf", fmt="pdf", score=90)
    wire_cli(monkeypatch, client, [mock_adapter([cand])])

    res = run(cfg)
    assert [r.spec.key for r in res] == ["good"]
    out = capsys.readouterr().out
    assert "bad.md" in out                            # skipped file reported, run survived