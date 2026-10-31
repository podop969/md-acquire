# Offline tests for the Manifest provenance log.
from __future__ import annotations

import json

from pipeline.manifest import Manifest
from pipeline.models import Candidate


def test_appends_one_valid_jsonl_line(tmp_path, make_spec):
    path = tmp_path / "manifest.jsonl"
    m = Manifest(path)
    spec = make_spec(doi="10.1/x")
    cand = Candidate(
        source="mock",
        url="https://example.org/a.pdf",
        fmt="pdf",
        license="cc-by",
        extra={"k": "v"},
    )

    m.record(spec, cand, tmp_path / "a.pdf", "deadbeef")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["key"] == "demo"
    assert entry["title"] == "Thinking, Fast and Slow"
    assert entry["authors"] == ["Daniel Kahneman"]
    assert entry["source"] == "mock"
    assert entry["url"] == "https://example.org/a.pdf"
    assert entry["format"] == "pdf"
    assert entry["license"] == "cc-by"
    assert entry["saved_as"] == "a.pdf"
    assert entry["sha256"] == "deadbeef"
    assert entry["extra"] == {"k": "v"}
    assert "ts" in entry


def test_two_records_append(tmp_path, make_spec):
    path = tmp_path / "manifest.jsonl"
    m = Manifest(path)
    cand = Candidate(source="mock", url="http://x", fmt="pdf")

    m.record(make_spec(), cand, tmp_path / "1.pdf", "a")
    m.record(make_spec(), cand, tmp_path / "2.pdf", "b")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["saved_as"] == "2.pdf"


def test_creates_parent_dirs(tmp_path):
    m = Manifest(tmp_path / "deep" / "sub" / "manifest.jsonl")

    m.record(
        __import__("pipeline.models", fromlist=["WorkSpec"]).WorkSpec(key="k", title="T"),
        Candidate(source="s", url="u", fmt="pdf"),
        tmp_path / "f.pdf",
        "sha",
    )

    m.path.exists()