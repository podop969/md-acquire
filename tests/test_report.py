# Offline tests for report.md + wanted.md rendering.
# wanted.md in this repo also carries manual search links (handoff.py) and
# borrow hints; those are covered by test_pipeline.py, here we pin the core
# resolved/unresolved contract from the integration guide.
from __future__ import annotations

from pipeline.models import Resolution
from pipeline.report import write


def test_report_and_wanted_reflect_resolutions(tmp_path, make_spec):
    ok = Resolution(
        spec=make_spec(key="resolved", title="Resolved Book"),
        status="ok",
        saved=[tmp_path / "Resolved.pdf"],
        detail="arxiv",
    )
    missing = Resolution(
        spec=make_spec(key="missing", title="Missing Book", isbn13="9780374533557", doi="10.1/x"),
        status="not_found",
        detail="no adapter produced a match",
        hints=["isbn13 <- 9780374533557"],
    )

    report, wanted = write([ok, missing], tmp_path)

    rtext = report.read_text(encoding="utf-8")
    assert "resolved: 1" in rtext
    assert "unresolved: 1" in rtext
    assert "Resolved.pdf" in rtext

    wtext = wanted.read_text(encoding="utf-8")
    assert "## Missing Book" in wtext
    assert "9780374533557" in wtext
    assert "10.1/x" in wtext
    assert "no adapter produced a match" in wtext    # detail
    assert "isbn13 <- 9780374533557" in wtext        # hints


def test_all_resolved_yields_empty_wanted(tmp_path, make_spec):
    ok = Resolution(spec=make_spec(), status="ok", saved=[tmp_path / "x.pdf"], detail="mock")

    report, wanted = write([ok], tmp_path)

    assert "resolved: 1" in report.read_text(encoding="utf-8")
    assert "unresolved: 0" in report.read_text(encoding="utf-8")
    assert "## " not in wanted.read_text(encoding="utf-8")


def test_empty_input_still_writes_both_files(tmp_path):
    report, wanted = write([], tmp_path)

    assert report.exists() and wanted.exists()
    assert "resolved: 0" in report.read_text(encoding="utf-8")


def test_failed_spec_lands_in_wanted_with_manual_links(tmp_path, make_spec):
    from pipeline.handoff import manual_links

    res = Resolution(spec=make_spec(), status="failed", detail="both formats failed",
                     manual=manual_links(make_spec()))

    _, wanted = write([res], tmp_path)

    text = wanted.read_text(encoding="utf-8")
    assert "search manually" in text
    assert "annas-archive" in text