"""Local trigger UI for md-acquire (replaces the nightly-task workflow).

    python -m pipeline.webui          ->  http://127.0.0.1:8619
    scripts\\ui.ps1                    ->  same, plus opens the browser

One page: every spec with its per-format manifest status (complete / pending /
unparsable), top buttons — Dry run all, Run all (resume), Force re-fetch all —
a per-spec Fetch, a live log tail while a run is in flight, and links to
report.md / wanted.md / wanted.html / manifest.jsonl.

Loopback-only bind (nothing leaves the machine), one run at a time, no daemon
and no scheduler: the button is the trigger.
"""
from __future__ import annotations

import argparse
import contextlib
import html
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .bulk import completed_formats
from .config import Config
from .spec import parse_file

_FILE_WHITELIST = ("report.md", "wanted.md", "wanted.html", "manifest.jsonl")


class _Tee:
    """Send run output to the shared log buffer AND the real console.

    The echo target is captured before redirect_stdout, else the echo would
    recurse into itself (redirect_stdout swaps sys.stdout for this object).
    """

    def __init__(self, sink: list[str], echo) -> None:
        self.sink = sink
        self.echo = echo

    def write(self, s: str) -> int:
        self.sink.append(s)
        try:
            self.echo.write(s)
        except Exception:
            pass
        return len(s)

    def flush(self) -> None:
        pass

    # pytest's terminal writer probes the stream (isatty et al); without these
    # it raises INTERNALERROR when it finds our redirected buffer in its way.
    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def writelines(self, seq) -> None:
        for s in seq:
            self.write(s)


class Job:
    """One job at a time (bulk run or pytest), with a capturable log."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.running = False
        self.kind = ""
        self.exit_code: int | None = None

    def start(self, kind: str, work: Callable[[], int]) -> bool:
        with self.lock:
            if self.running:
                return False
            echo = sys.stdout
            self.lines, self.exit_code, self.kind = [], None, kind
            self.running = True

        def runner() -> None:
            try:
                with contextlib.redirect_stdout(_Tee(self.lines, echo)):
                    self.exit_code = int(work())
            except Exception as exc:
                self.lines.append(f"\n!! crashed: {exc!r}\n")
                self.exit_code = 2
            self.running = False

        threading.Thread(target=runner, daemon=True).start()
        return True

    def status(self) -> dict:
        return {
            "running": self.running,
            "kind": self.kind,
            "exit_code": self.exit_code,
            "log": "".join(self.lines[-160:]),
        }


_SHARED_JOB = Job()


def _bulk_work(cfg: Config, *, force: bool = False, dry_run: bool = False,
               only: set[str] | None = None) -> Callable[[], int]:
    def work() -> int:
        from . import bulk                    # attribute lookup stays patchable in tests
        resolutions = bulk.run(cfg, force=force, dry_run=dry_run, only=only)
        if dry_run:
            return 0                # informational: the printed plan is the product
        failed = sum(1 for r in resolutions if r.status not in ("ok", "partial"))
        return 0 if failed == 0 else 1

    return work


def _pytest_work() -> Callable[[], int]:
    def work() -> int:
        print("==> pytest (offline suite)")
        import pytest
        return int(pytest.main(["-q"]))       # no args -> pyproject testpaths apply

    return work


def spec_rows(cfg: Config) -> tuple[list[dict], list[dict]]:
    """(ready rows, unparsable problems) for the dashboard table."""
    done = completed_formats(cfg.out_dir / "manifest.jsonl", cfg.out_dir)
    rows: list[dict] = []
    problems: list[dict] = []
    if cfg.specs_dir.is_dir():
        for p in sorted(cfg.specs_dir.glob("*.md")):
            try:
                spec = parse_file(p)
            except Exception as exc:
                problems.append({"name": p.name, "error": str(exc)})
                continue
            got = done.get(spec.key, set())
            rows.append({
                "key": spec.key,
                "title": spec.title,
                "authors": ", ".join(spec.authors),
                "formats": [{"fmt": f, "ok": f in got} for f in spec.formats],
                "all_done": all(f in got for f in spec.formats),
            })
    return rows, problems


_CSS = """\
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem 4rem; background: #14151a; color: #e7e7ee;
       font: 16px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width: 56rem; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 1.2rem; }
h1 span { color: #9a9ab0; font-size: 1rem; font-weight: 400; }
.bar { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0 0 1rem; }
button { padding: .5rem .85rem; border-radius: 8px; font-size: .9rem; color: #dcdcea;
         background: #2a2b36; border: 1px solid #3a3b48; cursor: pointer; }
button:hover { background: #34354a; border-color: #5a5b78; }
button.go { background: #2b3a2e; border-color: #3f5a44; }
button.warn { background: #3a2b2b; border-color: #5a3f3f; }
button:disabled { opacity: .45; cursor: default; }
pre { background: #1d1e26; border: 1px solid #2c2d38; border-radius: 10px;
      padding: .8rem 1rem; min-height: 3.2rem; max-height: 16rem; overflow: auto;
      white-space: pre-wrap; font-size: .82rem; color: #c7c7d9; margin: 0 0 1.5rem; }
table { width: 100%; border-collapse: collapse; background: #1d1e26;
        border: 1px solid #2c2d38; border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: .55rem .8rem; border-bottom: 1px solid #26272f;
         font-size: .9rem; vertical-align: top; }
th { color: #9a9ab0; font-weight: 600; background: #20212b; }
tr:last-child td { border-bottom: 0; }
td form { margin: 0; }
.ok { color: #7fd19c; }
.pend { color: #d1a97f; }
.auth { color: #a9a9c0; font-size: .8rem; }
.problems { color: #e08585; font-size: .85rem; margin: .6rem 0 1rem; }
.count { color: #9a9ab0; font-size: .85rem; margin: 1.4rem 0 .5rem; }
.note { color: #d1a97f; font-size: .85rem; margin: .6rem 0 1rem; }
.files a { display: inline-block; margin: 0 .7rem .4rem 0; color: #9db4e8;
           font-size: .9rem; text-decoration: none; }
.files a:hover { text-decoration: underline; }
footer { color: #70708a; font-size: .82rem; margin-top: 2rem; }
"""

_JS = """\
const logEl = document.getElementById('log');
const buttons = [...document.querySelectorAll('button')];
let polling = false;
function setBusy(b) { buttons.forEach(x => x.disabled = b); }
async function run(url) { await fetch(url); poll(); }
async function poll() {
  if (polling) return;
  polling = true; setBusy(true);
  while (true) {
    const j = await (await fetch('/status')).json();
    logEl.textContent = j.log || (j.running ? 'working...' : '');
    logEl.scrollTop = logEl.scrollHeight;
    if (!j.running) break;
    await new Promise(r => setTimeout(r, 700));
  }
  polling = false; setBusy(false);
  setTimeout(() => location.reload(), 800);
}
window.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('[data-run]').forEach(b =>
    b.addEventListener('click', () => run(b.dataset.run)));
  const j = await (await fetch('/status')).json();
  if (j.log) logEl.textContent = j.log;
  if (j.running) poll();
});
"""


def dashboard_html(rows: list[dict], problems: list[dict], status: dict) -> str:
    out = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           "<title>md-acquire — trigger UI</title>",
           "<style>", _CSS, "</style></head><body><main>",
           "<h1>md-acquire <span>— trigger UI</span></h1>",
           "<div class='bar'>",
           "<button data-run=\"/run?mode=dry\">Dry run all</button>",
           "<button class='go' data-run=\"/run?mode=run\">Run all (resume)</button>",
           "<button class='warn' data-run=\"/run?mode=force\">Force re-fetch all</button>",
           "<button data-run=\"/test\">Run test suite</button>",
           "</div>",
           f"<pre id='log'>{html.escape(status.get('log') or '')}</pre>"]
    if status.get("running"):
        out.append(f"<div class='note'>a {html.escape(status.get('kind') or 'job')} is in "
                   "flight — buttons re-enable when it finishes</div>")
    elif status.get("exit_code") is not None:
        cls = "ok" if status["exit_code"] == 0 else "problems"
        kind = html.escape(status.get("kind") or "job")
        out.append(f"<div class='{cls}'>last {kind}: exit {status['exit_code']}</div>")
    out.append(f"<div class='count'>{len(rows)} spec(s) &middot; "
               f"{sum(1 for r in rows if r['all_done'])} fully complete</div>")
    out.append("<table><tr><th>title</th><th>formats</th><th></th></tr>")
    for r in rows:
        auth_html = f"<div class='auth'>{html.escape(r['authors'])}</div>" if r["authors"] else ""
        fmt_html = " &middot; ".join(
            f"<span class='{'ok' if f['ok'] else 'pend'}'>"
            f"{'&#10003; ' if f['ok'] else '&#10007; '}{html.escape(f['fmt'])}"
            "</span>" for f in r["formats"])
        btn = (f"<button data-run=\"/run?mode={'force' if r['all_done'] else 'run'}"
               f"&amp;spec={html.escape(r['key'], quote=True)}\">"
               f"{'re-fetch' if r['all_done'] else 'Fetch'}</button>")
        out.append(f"<tr><td>{html.escape(r['title'])}{auth_html}</td>"
                   f"<td>{fmt_html}</td><td>{btn}</td></tr>")
    out.append("</table>")
    if problems:
        out.append("<div class='problems'>unparsable spec files (skipped by runs):")
        for pr in problems:
            out.append(f"<div>&mdash; {html.escape(pr['name'])}: {html.escape(pr['error'])}</div>")
        out.append("</div>")
    out.append("<div class='files'>outputs: "
               "<a href='/file?name=report.md' target='_blank'>report.md</a>"
               "<a href='/file?name=wanted.md' target='_blank'>wanted.md</a>"
               "<a href='/file?name=wanted.html' target='_blank'>wanted.html (clickable)</a>"
               "<a href='/file?name=manifest.jsonl' target='_blank'>manifest.jsonl</a>"
               "</div>")
    out.append("<footer>Open-access sources only (arXiv, Open Library public scans, "
               "Project Gutenberg, Unpaywall). Non-open titles are never auto-fetched: "
               "wanted.html hands you search links to click yourself.</footer>")
    out.append("<script>" + _JS + "</script>")
    out.append("</main></body></html>")
    return "".join(out)


def make_handler(config_path: str, job: Job | None = None):
    _job = job or _SHARED_JOB

    class Handler(BaseHTTPRequestHandler):
        server_version = "md-acquire-ui/0.1"

        def log_message(self, fmt, *args) -> None:   # keep the console clean
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict, code: int = 200) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self) -> None:
            u = urlparse(self.path)
            try:
                if u.path == "/":
                    cfg = Config.load(config_path)
                    rows, problems = spec_rows(cfg)
                    self._send(200, dashboard_html(rows, problems, _job.status()).encode("utf-8"),
                               "text/html; charset=utf-8")
                elif u.path == "/status":
                    self._json(_job.status())
                elif u.path == "/run":
                    cfg = Config.load(config_path)
                    q = parse_qs(u.query)
                    mode = (q.get("mode") or ["run"])[0]
                    key = (q.get("spec") or [None])[0]
                    started = _job.start(
                        "bulk run",
                        _bulk_work(cfg, force=mode == "force", dry_run=mode == "dry",
                                   only={key} if key else None),
                    )
                    self._json({"ok": True, "started": started, "busy": not started})
                elif u.path == "/test":
                    started = _job.start("test suite", _pytest_work())
                    self._json({"ok": True, "started": started, "busy": not started})
                elif u.path == "/file":
                    name = (parse_qs(u.query).get("name") or [""])[0]
                    if name not in _FILE_WHITELIST:
                        self._json({"ok": False, "error": "not in whitelist"}, 404)
                        return
                    p = Path(Config.load(config_path).out_dir) / name
                    if not p.exists():
                        self._json({"ok": False, "error": f"{name} not written yet"}, 404)
                        return
                    ctype = ("text/html; charset=utf-8" if name.endswith(".html")
                             else "text/plain; charset=utf-8")
                    self._send(200, p.read_bytes(), ctype)
                else:
                    self._json({"ok": False, "error": "unknown route"}, 404)
            except BrokenPipeError:
                pass
            except Exception as exc:
                try:
                    self._json({"ok": False, "error": repr(exc)}, 500)
                except Exception:
                    pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        "md-acquire ui", description="Local trigger UI (http://127.0.0.1:<port>)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8619)
    ap.add_argument("--open", action="store_true", help="open the browser on start")
    a = ap.parse_args(argv)

    job = Job()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.config, job))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"md-acquire UI on {url}   (Ctrl+C stops)")
    if a.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())