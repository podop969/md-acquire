"""Dashboard rendering: a finished job's log survives the end-of-run reload."""
from __future__ import annotations

from pipeline.webui import dashboard_html


def test_dashboard_keeps_finished_log_and_escapes_it():
    page = dashboard_html([], [], {
        "running": False,
        "kind": "bulk run",
        "exit_code": 0,
        "log": "1 / 3 specs pending\n<script>alert(1)</script>",
    })
    pre = page.split("<pre id='log'>", 1)[1].split("</pre>", 1)[0]
    assert "1 / 3 specs pending" in pre
    assert "<script>" not in pre
    assert "&lt;script&gt;" in pre
    assert "if (j.log) logEl.textContent = j.log;" in page
