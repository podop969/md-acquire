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
import hmac
import html
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .bulk import completed_formats
from .config import Config
from .spec import parse_file
from .search import search, add_spec, CATALOGUE_SOURCES
from .progress import listen, failure_reason
from . import library
import mimetypes
import zipfile
import xml.etree.ElementTree as ET

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
        self.progress: dict = {}
        self.results: dict = {}
        self.started_at = 0.0
        self.finished_at = None

    def update_progress(self, event):
        with self.lock:
            self.progress.update(event)
            if event.get('result'):
                self.results[self.progress.get('key', '')] = dict(self.progress)

    def start(self, kind: str, work: Callable[[], int]) -> bool:
        with self.lock:
            if self.running:
                return False
            echo = sys.stdout
            self.lines, self.exit_code, self.kind = [], None, kind
            self.running = True
            self.started_at = time.monotonic()
            self.finished_at = None
            self.progress = {'stage': 'starting', 'message': 'Starting ' + kind + '…'}
            self.results = {}

        def runner() -> None:
            try:
                with listen(self.update_progress), contextlib.redirect_stdout(_Tee(self.lines, echo)):
                    self.exit_code = int(work())
            except Exception as exc:
                self.lines.append(f"\n!! crashed: {exc!r}\n")
                self.exit_code = 2
                self.update_progress({'stage': 'failed', 'message': failure_reason(exc)})
            with self.lock:
                if self.exit_code and self.progress.get('stage') not in ('failed', 'partial'):
                    self.progress.update(stage='failed', message='Run finished with failures. See results and log below.')
                elif not self.exit_code and self.progress.get('stage') not in ('saved', 'partial', 'failed'):
                    self.progress.update(stage='complete', message='Run complete. See the log for details.')
                self.finished_at = time.monotonic()
                self.running = False

        threading.Thread(target=runner, daemon=True).start()
        return True

    def status(self) -> dict:
        with self.lock:
            return {
            "running": self.running,
            "kind": self.kind,
            "exit_code": self.exit_code,
            "log": "".join(self.lines[-160:]),
            "progress": dict(self.progress),
            "results": [dict(r) for r in self.results.values()],
            "elapsed": round((self.finished_at or time.monotonic()) - self.started_at, 1) if self.started_at else 0,
        }


_SHARED_JOB = Job()


def _bulk_work(cfg: Config, *, force: bool = False, dry_run: bool = False,
               only: set[str] | None = None) -> Callable[[], int]:
    def work() -> int:
        from . import bulk                    # attribute lookup stays patchable in tests
        resolutions = bulk.run(cfg, force=force, dry_run=dry_run, only=only)
        if dry_run:
            return 0                # informational: the printed plan is the product
        failed = sum(1 for r in resolutions if r.status != "ok")
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
                "selected_source": (f"Anna’s Archive · selected {spec.source_format.upper()} file"
                                    if spec.source == 'annas_archive' else ''),
                "formats": [{"fmt": f, "ok": f in got} for f in spec.formats],
                "all_done": all(f in got for f in spec.formats),
            })
    return rows, problems


_CSS = """\
.search-panel { margin-bottom: 1.5rem; }
.search-form { display: flex; gap: .5rem; margin-top: .5rem; }
.search-form input { min-width: 0; flex: 1; padding: .7rem; border: 1px solid #505164;
  border-radius: 8px; background: #1d1e26; color: #e7e7ee; font: inherit; }
#search-results { display: grid; gap: .5rem; max-height: 24rem; overflow: auto; }
.search-result { display: flex; align-items: center; justify-content: space-between;
  gap: 1rem; padding: .8rem; background: #1d1e26; border-radius: 8px; }
.search-result button { flex-shrink: 0; }
#search-message { color: #a9a9c0; }
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
.download-status { border: 1px solid #666680; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.download-status[data-stage='failed'], .download-status[data-stage='partial'] { border-color: #d99672; }
.download-status progress { width: 100%; }
footer { color: #70708a; font-size: .82rem; margin-top: 2rem; }
"""

_JS = """\
const logEl = document.getElementById('log');
const buttons = [...document.querySelectorAll('[data-run]')];
let polling = false;
function setBusy(b) { buttons.forEach(x => x.disabled = b); }
function renderProgress(job) {
  const p = job.progress || {};
  const card = document.getElementById('download-status');
  card.hidden = !p.stage; card.dataset.stage = p.stage || '';
  const labels = {starting: 'Starting', finding: 'Finding files', connecting: 'Connecting',
    waiting: 'Waiting for browser or verification', downloading: 'Downloading',
    validating: 'Checking file', retrying: 'Trying another source', saved: 'Saved',
    failed: 'Failed', partial: 'Some formats missing', complete: 'Complete'};
  document.getElementById('download-stage').textContent = labels[p.stage] || '';
  document.getElementById('download-detail').textContent = p.message || '';
  document.getElementById('download-context').textContent =
    [p.title, p.source, (p.fmt || '').toUpperCase(), Math.floor(job.elapsed || 0) + 's elapsed'].filter(Boolean).join(' · ');
  const meter = document.getElementById('download-meter');
  meter.hidden = p.stage !== 'downloading';
  if (p.total > 0 && p.received != null) { meter.max = p.total; meter.value = p.received; }
  else { meter.removeAttribute('value'); }
  document.getElementById('download-bytes').textContent = p.received == null ? '' :
    (p.received / 1048576).toFixed(2) + ' MB received' +
    (p.total ? ' of ' + (p.total / 1048576).toFixed(2) + ' MB' : '');
  const results = document.getElementById('download-results'); results.replaceChildren();
  for (const r of job.results || []) {
    const item = document.createElement('li');
    item.textContent = r.title + ': ' + r.message; results.append(item);
  }
}
const TOKEN = document.querySelector('meta[name="ui-token"]').content;
async function run(url) {
  await fetch(url, { method: 'POST', headers: { 'X-UI-Token': TOKEN } });
  poll();
}
async function poll() {
  if (polling) return;
  polling = true; setBusy(true);
  try { while (true) {
    const j = await (await fetch('/status')).json();
    renderProgress(j);
    logEl.textContent = j.log || (j.running ? 'working...' : '');
    logEl.scrollTop = logEl.scrollHeight;
    if (!j.running) break;
    await new Promise(r => setTimeout(r, 700));
  }
  setTimeout(() => location.reload(), 800);
  } catch (error) {
    logEl.textContent += '\\nLost connection to the dashboard. Reload to reconnect.';
  } finally { polling = false; setBusy(false); }
}
async function refreshSpecs() {
  const response = await fetch('/');
  if (!response.ok) throw new Error('Could not refresh the table. Reload this page.');
  const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
  document.querySelector('table').replaceWith(doc.querySelector('table'));
  document.querySelector('.count').replaceWith(doc.querySelector('.count'));
  document.querySelectorAll('table [data-run]').forEach(b => {
    buttons.push(b);
    b.addEventListener('click', () => run(b.dataset.run));
  });
}
function appendSearchResults(books, results, message) {
    for (const book of books) {
      const row = document.createElement('div'); row.className = 'search-result';
      const info = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = book.title;
      const detail = document.createElement('div'); detail.className = 'auth';
      detail.textContent = [book.authors.join(', '), book.year,
        book.source === 'annas_archive' ? "Anna's Archive" : book.source,
        book.listed_format ? 'Listed format: ' + book.listed_format.toUpperCase() : '',
        book.availability].filter(Boolean).join(' · ');
      info.append(title, detail);
      if (book.source_url) {
        const url = new URL(book.source_url, window.location.origin);
        if (url.protocol === 'https:' || url.protocol === 'http:') {
          const link = document.createElement('a'); link.href = url.href;
          link.textContent = 'View source page'; link.target = '_blank'; link.rel = 'noopener noreferrer';
          info.append(link);
        }
      }
      const add = document.createElement('button'); add.textContent = 'Add to specs';
      if (book.source === 'annas_archive' && !['pdf', 'epub'].includes(book.listed_format)) {
        add.disabled = true; add.textContent = 'PDF/EPUB only';
        add.title = 'Choose a PDF or EPUB record to download through this app.';
      }
      add.setAttribute('aria-label', 'Add ' + book.title + ' to specs');
      add.addEventListener('click', async () => {
        add.disabled = true; add.textContent = 'Adding…';
        try {
          const response = await fetch('/specs', {method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-UI-Token': TOKEN}, body: JSON.stringify(book)});
          const saved = await response.json();
          if (!response.ok) throw new Error(saved.error || 'Could not add this title.');
          await refreshSpecs();
          add.textContent = saved.created ? 'Added ✓' : 'Already added';
          message.textContent = book.title + (book.source === 'annas_archive'
            ? ' is in your specs table. Click Fetch to download this selected copy through the browser.'
            : ' is in your specs table. Click Fetch to look for an open-access copy.');
        } catch (error) {
          message.textContent = error.message; add.disabled = false; add.textContent = 'Retry adding';
        }
      });
      row.append(info, add); results.append(row);
    }
}
async function searchBooks(event) {
  event.preventDefault();
  const message = document.getElementById('search-message');
  const annaMessage = document.getElementById('annas-search-message');
  const results = document.getElementById('search-results');
  const submit = document.getElementById('search-submit');
  if (submit.disabled) return;
  const query = document.getElementById('search-query').value;
  const useAnna = document.getElementById('search-form').dataset.annasEnabled === 'true';
  submit.disabled = true; results.replaceChildren();
  annaMessage.textContent = useAnna ? 'Searching Anna’s Archive… Complete verification if a browser window opens. You can use other results while it loads.' : '';
  let count = 0;
  let pending = useAnna ? 2 : 1;
  const warnings = [];
  const updateSummary = () => {
    message.textContent = (count ? count + ' results. Add a title to your specs below.' :
      pending ? 'Searching catalogues…' : 'No matches found. Try another title or author.') + ' ' + warnings.join(' ');
  };
  updateSummary();
  async function loadSource(url, options, isAnna) {
    try {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Search failed. Please try again.');
      appendSearchResults(data.results, results, message);
      count += data.results.length;
      if (isAnna) {
        annaMessage.textContent = data.warnings.length ? data.warnings.join(' ') :
          'Anna’s Archive: ' + data.results.length + ' results.';
      } else {
        warnings.push(...data.warnings);
      }
    } catch (error) {
      if (isAnna) annaMessage.textContent = 'Anna’s Archive: ' + error.message;
      else warnings.push(error.message);
    } finally {
      pending -= 1; updateSummary();
    }
  }
  const tasks = [loadSource('/search?q=' + encodeURIComponent(query), undefined, false)];
  if (useAnna) tasks.push(loadSource('/search/annas', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-UI-Token': TOKEN}, body: JSON.stringify({q: query})
  }, true));
  try { await Promise.all(tasks); }
  finally { submit.disabled = false; }
}
window.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('search-form').addEventListener('submit', searchBooks);
  document.querySelectorAll('[data-run]').forEach(b =>
    b.addEventListener('click', () => run(b.dataset.run)));
  const j = await (await fetch('/status')).json();
  if (j.log) logEl.textContent = j.log;
  renderProgress(j);
  if (j.running) poll();
});
"""


def dashboard_html(rows: list[dict], problems: list[dict], status: dict,
                   token: str = "", *, anna_enabled: bool = False) -> str:
    out = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           f"<meta name='ui-token' content='{html.escape(token, quote=True)}'>",
           "<title>md-acquire — trigger UI</title>",
           "<style>", _CSS, "</style></head><body><main>",
           "<h1>md-acquire <span>— trigger UI</span></h1>",
           "<p><a href='/library'>My library — read downloaded books</a></p>",
           "<section class='search-panel' aria-label='Catalogue search'>",
           f"<form id='search-form' data-annas-enabled='{str(anna_enabled).lower()}'><label for='search-query'>Find books and papers</label>",
           "<div class='search-form'><input id='search-query' type='search' required minlength='2' maxlength='300' "
           "placeholder='Search by title, author, or ISBN'><button id='search-submit' type='submit'>Search</button></div></form>",
           "<p class='auth'>Searches enabled Open Library, Gutenberg, arXiv, and Anna’s Archive sources. "
           "Anna’s Archive PDF/EPUB selections keep their exact file link for browser downloads. "
           "Unpaywall checks DOI-based open copies when you fetch. Adding a title does not download it.</p>",
           "<p id='search-message' role='status' aria-live='polite'></p>",
           "<p id='annas-search-message' class='auth' role='status' aria-live='polite'></p><div id='search-results'></div></section>",
           "<div class='bar'>",
           "<button data-run=\"/run?mode=dry\">Dry run all</button>",
           "<button class='go' data-run=\"/run?mode=run\">Run all (resume)</button>",
           "<button class='warn' data-run=\"/run?mode=force\">Force re-fetch all</button>",
           "<button data-run=\"/test\">Run test suite</button>",
           "</div>",
           "<section id='download-status' class='download-status' hidden role='status' aria-live='polite'>"
           "<strong id='download-stage'></strong><p id='download-context' class='auth'></p>"
           "<p id='download-detail'></p><progress id='download-meter' aria-label='Download progress' hidden></progress>"
           "<p id='download-bytes'></p><ul id='download-results'></ul></section>",
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
        if r.get('selected_source'):
            auth_html += f"<div class='auth'>{html.escape(r['selected_source'])}</div>"
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
    out.append("<footer>Fetch checks the configured open-access sources and any explicitly selected "
               "Anna’s Archive file. Anna downloads may need browser interaction. "
               "Unresolved titles get manual links in wanted.html.</footer>")
    out.append("<script>" + _JS + "</script>")
    out.append("</main></body></html>")
    return "".join(out)


def make_handler(config_path: str, job: Job | None = None, *,
                 port: int = 8619, token: str | None = None):
    """Build the request handler.

    CSRF / DNS-rebinding guard: every request must carry a loopback Host header,
    and every state-changing route is POST-only and needs the per-process token
    (embedded in the dashboard, library and reader pages) in an X-UI-Token header.
    A cross-site page can neither read that token nor set a custom header.
    The guard runs in do_POST before any routing, so a POST route added later
    is covered without further changes; never add a second do_POST.
    """
    _job = job or _SHARED_JOB
    _token = token or secrets.token_urlsafe(32)
    _allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    _json_routes = ('/specs', '/search/annas', '/library/position', '/library/reveal')

    class Handler(BaseHTTPRequestHandler):
        server_version = "md-acquire-ui/0.1"

        def log_message(self, fmt, *args) -> None:   # keep the console clean
            pass

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") in _allowed_hosts:
                return True
            self._json({"ok": False, "error": "bad host"}, 403)
            return False

        def do_POST(self) -> None:
            if not self._host_ok():
                return
            sent = self.headers.get("X-UI-Token", "")
            if not hmac.compare_digest(sent.encode(), _token.encode()):
                self._json({"ok": False, "error": "bad or missing token"}, 403)
                return
            if urlparse(self.path).path in ("/run", "/test"):
                self._post_job()
            elif self.path in _json_routes:
                self._post_json()
            else:
                self._json({"ok": False, "error": "unknown route"}, 404)

        def _post_job(self) -> None:
            u = urlparse(self.path)
            try:
                if u.path == "/run":
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
                else:
                    started = _job.start("test suite", _pytest_work())
                    self._json({"ok": True, "started": started, "busy": not started})
            except BrokenPipeError:
                pass
            except Exception as exc:
                try:
                    self._json({"ok": False, "error": repr(exc)}, 500)
                except Exception:
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

        def _local_file(self, path: Path, ctype: str) -> None:
            with path.open('rb') as stream:
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(path.stat().st_size))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                while chunk := stream.read(64 * 1024):
                    self.wfile.write(chunk)

        def _post_json(self) -> None:
            # Second layer behind the token: JSON-only and same-origin requests.
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self._json({'error': 'Expected JSON'}, 415)
                return
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                self._json({'error': 'Cross-origin request rejected'}, 403)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    raise ValueError('Invalid request size.')
                payload = json.loads(self.rfile.read(size))
                cfg = Config.load(config_path)
                if self.path in ('/library/position', '/library/reveal'):
                    if not isinstance(payload, dict) or not isinstance(payload.get('id'), str):
                        raise ValueError('Invalid library request.')
                    if self.path == '/library/position':
                        library.save_position(cfg.out_dir, payload['id'], payload.get('position'))
                    else:
                        library.reveal(cfg.out_dir, payload['id'])
                    self._json({'ok': True})
                    return
                if self.path == '/search/annas':
                    query = payload.get('q') if isinstance(payload, dict) else None
                    if not isinstance(query, str):
                        raise ValueError('Enter a search query.')
                    self._json(search(query, cfg, sources=('annas_archive',)))
                    return
                key, created = add_spec(payload, cfg.specs_dir)
                self._json({'key': key, 'created': created}, 201 if created else 200)
            except (ValueError, UnicodeDecodeError) as exc:
                self._json({'error': str(exc)}, 400)
            except BrokenPipeError:
                pass
            except FileNotFoundError as exc:
                self._json({'error': str(exc)}, 404)
            except OSError:
                self._json({'error': 'Could not save the spec. Check folder permissions.'}, 500)

        def do_GET(self) -> None:
            if not self._host_ok():
                return
            u = urlparse(self.path)
            try:
                if u.path.startswith('/assets/'):
                    path = (library.STATIC / u.path.removeprefix('/assets/')).resolve()
                    if not path.is_relative_to(library.STATIC.resolve()) or not path.is_file():
                        raise FileNotFoundError('Asset not found.')
                    self._local_file(path, mimetypes.guess_type(path)[0] or 'application/octet-stream')
                elif u.path in ('/library', '/reader'):
                    page = (library.library_page(_token) if u.path == '/library'
                            else library.reader_page(_token))
                    self._send(200, page.encode(), 'text/html; charset=utf-8')
                elif u.path.startswith('/library/'):
                    root = Config.load(config_path).out_dir
                    q = parse_qs(u.query)
                    if u.path == '/library/books':
                        self._json({'books': library.books(root), 'positions': library.positions(root)})
                        return
                    identifier = (q.get('id') or [''])[0]
                    row, path = library.book(root, identifier)
                    if u.path == '/library/book':
                        row['position'] = library.positions(root).get(identifier)
                        if row['format'] == 'epub':
                            row['chapters'] = len(library.Epub(path).chapters)
                        self._json(row)
                    elif u.path == '/library/content':
                        self._local_file(path, 'application/pdf' if row['format'] == 'pdf' else 'application/epub+zip')
                    elif u.path in ('/library/cover', '/library/image', '/library/chapter') and row['format'] == 'epub':
                        epub = library.Epub(path)
                        if u.path == '/library/chapter':
                            body = epub.chapter(int((q.get('index') or ['0'])[0]), identifier).encode()
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/html; charset=utf-8')
                            self.send_header('Content-Length', str(len(body)))
                            self.send_header('Content-Security-Policy', "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; sandbox allow-same-origin")
                            self.end_headers()
                            self.wfile.write(body)
                        else:
                            name = epub.cover if u.path == '/library/cover' else (q.get('name') or [''])[0]
                            if not name:
                                raise FileNotFoundError('No embedded cover.')
                            data, ctype = epub.image(name)
                            self._send(200, data, ctype)
                    else:
                        raise FileNotFoundError('Library route not found.')
                elif u.path == "/":
                    cfg = Config.load(config_path)
                    rows, problems = spec_rows(cfg)
                    page = dashboard_html(rows, problems, _job.status(), _token,
                                          anna_enabled='annas_archive' in cfg.adapters)
                    self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                elif u.path == '/search':
                    query = (parse_qs(u.query).get('q') or [''])[0]
                    try:
                        self._json(search(query, Config.load(config_path), sources=CATALOGUE_SOURCES))
                    except ValueError as exc:
                        self._json({'error': str(exc)}, 400)
                elif u.path == "/status":
                    self._json(_job.status())
                elif u.path in ("/run", "/test"):
                    self._json({"ok": False, "error": "POST only"}, 405)
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
            except FileNotFoundError as exc:
                self._json({'error': str(exc)}, 404)
            except (ValueError, KeyError) as exc:
                self._json({'error': str(exc)}, 400)
            except (zipfile.BadZipFile, ET.ParseError):
                self._json({'error': 'This EPUB is damaged or has an unsupported package structure. Try the original file in another reader.'}, 400)
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
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.config, job, port=a.port))
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
