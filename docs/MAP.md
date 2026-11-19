# md-acquire — documentation map

Paths are relative to the repository root.

A local pipeline for acquiring books and papers. You write one Markdown spec per
work (YAML frontmatter: title, authors, ISBN/DOI, wanted formats). Four
open-access sources are searched (arXiv, Open Library public scans, Project
Gutenberg, Unpaywall). Anna's Archive is a fifth adapter: it downloads only a
record you explicitly selected in the UI (see README § Anna's Archive). Matching
files are downloaded, byte-validated as real PDF/EPUB, logged in a provenance
manifest with sha256, and reported. Works with no candidate land in
`wanted.md`/`wanted.html` as handoff pages. Everything is triggered from a
local web UI (or the CLI), which also hosts a library and a reader.

---

## 1. Start it

```
.\scripts\ui.ps1                    -> http://127.0.0.1:8619  (browser opens)
.\scripts\ui.ps1 -Port 9000         -> different port
.\scripts\ui.ps1 -NoBrowser         -> don't auto-open
```
Direct equivalent: `python -m pipeline.webui` (use
`.venv\Scripts\python.exe -m pipeline.webui`).

The dashboard has:
| Control | What it does |
|---|---|
| **Search** box | queries the catalogues (`GET /search`); Anna's Archive answers in a separate request (`POST /search/annas`) when its adapter is enabled; **Add to specs** saves a result as a spec (`POST /specs`) |
| **Dry run all** | shows what *would* be fetched; downloads nothing |
| **Run all (resume)** | fetches every incomplete spec; skips complete ones |
| **Force re-fetch all** | re-runs every spec regardless of manifest state |
| **Run test suite** | runs `pytest -q` in-process (pyproject testpaths: the whole `tests/` suite) |
| **Fetch / re-fetch** (row button) | one spec only (`re-fetch` forces when complete) |
| **My library** | `/library`: downloaded books; **Read** opens `/reader` |
| output links | `report.md` / `wanted.md` / `wanted.html` / `manifest.jsonl` via `/file` |
| download status card | current book, source, stage, bytes and progress where the size is known |

While a job runs, a live log tail streams the run's console output; buttons
disable until it finishes; the banner shows the last exit code. One job at a
time. No scheduler, no daemon, no background task exists.

### Security of the local UI

The server binds to 127.0.0.1 only. A loopback bind does not stop a web page in
your own browser from sending requests to it (cross-site requests, DNS
rebinding), so:

- every request must carry a `Host` of `127.0.0.1:<port>` or `localhost:<port>`;
  anything else gets 403;
- state-changing routes are POST only (`GET /run` and `GET /test` get 405);
- every POST must send the per-process token in an `X-UI-Token` header. The
  token is random on each start and embedded as `<meta name="ui-token">` in the
  dashboard, library and reader pages. The check runs before routing, so an
  unknown POST route also gets 403;
- the four JSON routes additionally require `Content-Type: application/json`
  (else 415), an `Origin` that matches the `Host` when one is sent (else 403),
  and a body of 1 to 65,536 bytes (else 400);
- `/file` serves only `report.md`, `wanted.md`, `wanted.html`,
  `manifest.jsonl`; the library serves only PDF/EPUB files directly inside the
  download folder, never symlinks.

Pinned by `tests/test_webui_csrf.py` and `tests/test_webui_post_guard.py`.
`pipeline/webui.py` must keep exactly ONE `do_POST`: Python silently keeps the
last of two same-named methods, which is how a merge once dropped this guard.
`test_handler_defines_do_post_once` fails on a second one.

### Routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | dashboard |
| GET | `/status` | job state and log (polled by the page) |
| GET | `/search?q=` | catalogue search (not Anna's Archive) |
| GET | `/file?name=` | the four whitelisted output files |
| GET | `/library`, `/reader` | library and reader pages |
| GET | `/library/books`, `/library/book`, `/library/content` | book list, one book, its file |
| GET | `/library/cover`, `/library/image`, `/library/chapter` | EPUB cover, images, sanitised chapters |
| GET | `/assets/...` | bundled CSS/JS and PDF.js |
| POST | `/run?mode=dry\|run\|force` | start a bulk run (all specs, or one from a row button) |
| POST | `/test` | start the test suite |
| POST | `/specs` | add a search result as a spec |
| POST | `/search/annas` | Anna's Archive search (separate, may open a browser) |
| POST | `/library/position` | save a reading position |
| POST | `/library/reveal` | show a book in its folder |

## 2. First-time setup (all idempotent)

```
.\scripts\setup.ps1        # venv + deps (uv-aware) + config.yaml + specs\ skeleton
.\scripts\dev.ps1          # pytest + bulk --dry-run (the daily loop)
.\scripts\run.ps1          # bulk pass, resume-safe, exit 1 when anything unresolved
.\scripts\run.ps1 -Force   # re-acquire everything
.\scripts\run.ps1 -DryRun  # plan only, no downloads
```
Scheduler scripts still exist if you ever change your mind (nothing is
registered): `scripts\schedule.ps1 -WhatIf` / `scripts\unschedule.ps1`.

## 3. Tree

```
md-acquire/
├─ config.yaml                     # adapters, out dir, throttle, contact_email, annas_archive_* settings
├─ requirements.txt                # requests, PyYAML, beautifulsoup4, playwright
├─ pyproject.toml  uv.lock         # pytest config (testpaths, pythonpath); locked deps
├─ LICENSE                         # MIT (md-acquire's own code)
├─ README.md                       # overview, spec format, library/reader, Anna's Archive
├─ docs/
│  └─ MAP.md                       # ← this file
├─ pipeline/
│  ├─ models.py                    # WorkSpec, Candidate, Resolution (dataclasses)
│  ├─ config.py                    # Config.load (YAML + ACQUIRE_EMAIL env override)
│  ├─ http.py                      # Client: throttled, retrying, UA-tagged
│  ├─ spec.py                      # parse_file / load_from (MD frontmatter → WorkSpec)
│  ├─ metadata.py                  # enrich(): fills missing ISBN via Open Library
│  ├─ adapters/
│  │  ├─ base.py                   # Adapter ABC (lookup(client, spec) → [Candidate])
│  │  ├─ arxiv.py                  # arXiv Atom API → pdf candidates
│  │  ├─ openlibrary.py            # OL public scans → pdf; borrowable → hints
│  │  ├─ gutenberg.py              # Gutendex (fallback gutenberg.org) → epub/pdf
│  │  ├─ unpaywall.py              # OA copies for DOIs → pdf; needs contact_email
│  │  ├─ annas_archive.py          # the exact record selected in an Anna's search result
│  │  └─ __init__.py               # CLASSES: the fetch whitelist + build(names, cfg)
│  ├─ annas_archive.py             # Anna's Archive metadata search (public HTML pages)
│  ├─ annas_browser.py             # visible, user-assisted browser search
│  ├─ annas_download.py            # download of a selected record through a visible browser
│  ├─ download.py                  # safe_name, filename_for, validate, download
│  ├─ manifest.py                  # Manifest.record → jsonl (ts, sha256, license, url…)
│  ├─ report.py                    # report.md + wanted.md (+ auto wanted.html)
│  ├─ handoff.py                   # manual_links(): search-page links, never fetched
│  ├─ htmlwanted.py                # wanted.md → wanted.html renderer
│  ├─ citations.py                 # citation lines → spec files (CLI: -m pipeline.citations)
│  ├─ search.py                    # catalogue search; duplicate-aware spec creation
│  ├─ progress.py                  # job-local progress events for the status card
│  ├─ library.py                   # library listing, bounded EPUB parsing, reading positions
│  ├─ static/                      # library.css, library.js, reader.js, pdfjs/ (bundled PDF.js)
│  ├─ bulk.py                      # resume-safe runner over specs/ (used by UI + run.ps1)
│  ├─ webui.py                     # the local UI (loopback http server, guarded POSTs)
│  └─ cli.py                       # orchestration: enrich → adapters → rank → fallback → save
├─ scripts/                        # setup.ps1 dev.ps1 run.ps1 ui.ps1 (+ schedule/unschedule)
├─ tests/                          # pytest suite, offline (FakeClient seam, mocked browser)
│  ├─ conftest.py                  # FakeClient/FakeResponse, make_spec/make_config, MockAdapter, payloads
│  ├─ fixtures/                    # saved Anna's Archive search pages
│  └─ browser_library_smoke.py     # optional, not collected: real Chrome + temp books
├─ .github/workflows/windows.yml   # CI: pytest on 3.10/3.11/3.12 + CLI smoke
├─ Extract test/                   # third-party material, own licences (see README § Licence)
├─ specs/                          # your wants (one .md per work)
└─ library/                        # outputs (gitignored): books, manifest.jsonl, report.md,
                                   #   wanted.md, wanted.html, .reading-positions.json
```

## 4. How a run flows

```
UI button: POST /run?mode=…     .\scripts\run.ps1
      │                            │
      ▼                            ▼
pipeline.webui.Job  ──────▶ pipeline.bulk.run(cfg, force, dry_run, only)
                                  │  1. parse specs/*.md (bad files skipped, reported)
                                  │  2. read manifest.jsonl + check files on disk
                                  │  3. pending = spec wants format F, F not done-on-disk
                                  ▼
                             pipeline.cli.run(cfg, [spec files], only, dry_run)
                                  │  per spec: enrich (OL ISBN) → adapters.lookup
                                  │  → rank (-score, format order) → group by fmt
                                  │  → per format: try ranked candidates IN ORDER
                                  │    until one downloads AND validates
                                  ▼
          annas_archive candidate → annas_download.download_selected (visible browser)
          any other candidate     → download.py:
              existing file valid?   → reuse it (sha256)
              existing file invalid? → move it to <name>.invalid, then fetch
              else stream → .part → HTML-sniff → validate (%PDF- / epub mimetype+zip)
              → atomic rename
                                  ▼
                             manifest.record → report.write (+wanted.html)
```

Exit semantics: `bulk` exits 0 only when every spec ends `ok` or `partial`,
and 1 when any spec stays pending. **Dry runs included**: a dry run counts a
spec as resolved when a candidate exists, so an in-copyright book with no
candidate makes it exit 1. That is why CI's CLI smoke accepts exit 1 only when
the `bulk done.` summary line was printed; a crash also exits 1 but never
prints it.

## 5. Contracts worth remembering

- **Spec** (`specs/<slug>.md`): `---\ntitle: "…"\nauthors: […]\nisbn13: "…"\ndoi: "…"\nyear_min: N\nformats: ["epub","pdf"]\n---` + free notes. ISBN hyphens stripped, DOI prefixes normalized on parse. A spec added from an Anna's result also carries `source`, `source_url` and `source_format`.
- **Resume rule**: a spec is complete only when *every* wanted format has a manifest entry whose file still exists. Delete a file → next run re-fetches it.
- **Fallback rule**: per format, candidates are tried in ranked order until one downloads and validates (one dead mirror can't sink a spec) — pinned by `test_download_failure_falls_back_to_next_candidate`.
- **Invalid existing file**: every candidate for a spec targets the same filename, so an invalid file already there is moved to `<name>.invalid` (kept, never deleted) and a fresh copy is fetched — pinned by `test_download_replaces_invalid_existing_file`.
- **Borrowable ≠ fetchable**: Open Library `borrowable`/`printdisabled` copies become wanted.md hints, never candidates.
- **Fetch whitelist**: `CLASSES` in `pipeline/adapters/__init__.py` (five adapters); `config.yaml` `adapters` chooses which run. Everything else is a handoff link from `pipeline/handoff.py`, never downloaded.
- **Enrichment** fills a missing ISBN only (Open Library; crossref deliberately not used — unreachable from some networks); enrichment failure never fails a run; dry-run still enriches.
- **One guarded `do_POST`** in `pipeline/webui.py` (see § 1, Security).

## 6. Test suite (what guards what)

| File | Guards |
|---|---|
| `test_spec.py` | frontmatter parsing, defaults, DOI/ISBN normalization, ordering |
| `test_metadata.py` | OL ISBN fill / skip-when-present / failures swallowed |
| `test_adapters.py` | the open-access adapters: URL building, scoring, dedupe, error→[] |
| `test_download.py` | naming (incl. Windows reserved), validation, cache-skip, invalid-existing-file replacement, .part cleanup, HTML rejection |
| `test_manifest.py` | jsonl append, field completeness, parent-dir creation |
| `test_report.py` | resolved/unresolved counts, wanted content, empty-run files |
| `test_cli.py` | orchestration: dry-run never touches candidate URLs, per-format fallback, only-filter, idempotent re-run, single-spec input |
| `test_bulk.py` | manifest tolerance, disk-existence resume cycle, unknown `only`, unparsable-spec survival |
| `test_search.py` | catalogue search, spec creation (duplicates, filename safety), search endpoints |
| `test_library.py` | library listing, symlink exclusion, reading positions, EPUB parsing and covers |
| `test_progress.py` | progress events, live job status, readable HTTP failures without signed URLs |
| `test_webui.py` | finished job log kept and escaped on the dashboard |
| `test_webui_csrf.py` | GET cannot start a job; missing/wrong token and rebinding Host refused; page token works |
| `test_webui_post_guard.py` | every POST route (and an unknown one) guarded; one `do_POST`; library/reader carry the token |
| `test_annas_archive.py` / `test_annas_browser.py` / `test_annas_download.py` | Anna's Archive search parsing, browser search lifecycle, selected-record download (mocked) |
| `test_pipeline.py` / `test_citations.py` / `test_htmlwanted.py` | adapters, handoff links, citations parser, wanted.html renderer |

Run them: `.\scripts\ui.ps1 → Run test suite`, or `.venv\Scripts\python.exe -m pytest`.

## 7. Verified state (as of 2026-11-19)

- CI on `main` at `9422e1b` (PR #1 merged): green on Python 3.10, 3.11 and
  3.12, both the test step (212 passed) and the CLI smoke. This is the first
  green `main` since 31 Oct, when the CLI smoke began failing on the pending
  in-copyright spec.
- Local, 19 Nov: the suite minus the Anna's Archive tests, 166 passed on 3.12
  and 3.10; `tests/browser_library_smoke.py` passed in headless Chrome; on the
  dashboard, **Dry run all** clicked in headless Chrome sent `POST /run` (200) and the job
  ran; a live server refused a rebinding `Host` and a missing token and
  accepted the page token.
- Not re-verified here: live Anna's Archive search or download (the tests mock
  them; README records the last live check by its author).
- Known non-result, by design: `thinking-fast-and-slow` stays unresolved — no
  source the pipeline may fetch has an open copy; it gets wanted.html handoff
  links instead.

## 8. Boundaries

Automated downloading is limited to the adapters in `CLASSES`: the four
open-access sources, plus Anna's Archive for records you explicitly select,
which this repository's `config.yaml` enables (README § Anna's Archive and
§ Source behavior describe its behaviour and limits). Sites outside the
whitelist are surfaced as **search-page links for you to click**, never as
fetch targets — that line lives in `pipeline/handoff.py` (links only, never
downloaded) and `pipeline/adapters/__init__.py` (the whitelist).
