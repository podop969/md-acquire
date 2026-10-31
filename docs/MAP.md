# md-acquire — documentation map

Root: **`C:\Users\ajibo\md-acquire\`**

One paragraph of orientation: this is a local acquisition pipeline for books and
papers. You write a Markdown spec per work you want (YAML frontmatter: title,
authors, ISBN/DOI, wanted formats). Four open-access sources are queried
(arXiv, Open Library public scans, Project Gutenberg, Unpaywall). Matching
files are downloaded, byte-validated as real PDF/EPUB, logged in a provenance
manifest with sha256, and reported. Works that are not openly available are
never auto-fetched — they land in `wanted.md`/`wanted.html` as handoff pages.
The whole thing is triggered from a local web UI (or a CLI).

---

## 1. Start it (the UI you asked for)

```
.\scripts\ui.ps1                    -> http://127.0.0.1:8619  (browser opens)
.\scripts\ui.ps1 -Port 9000         -> different port
.\scripts\ui.ps1 -NoBrowser         -> don't auto-open
```
Direct equivalent: `python -m pipeline.webui` (use
`.venv\Scripts\python.exe -m pipeline.webui`).

The page has:
| Control | What it does |
|---|---|
| **Dry run all** | shows what *would* be fetched, network-free for downloads |
| **Run all (resume)** | fetches every incomplete spec; skips complete ones |
| **Force re-fetch all** | re-runs every spec regardless of manifest state |
| **Run test suite** | runs the offline pytest suite (108 tests, ~1s) in-process |
| **Fetch / re-fetch** (row button) | one spec only (`re-fetch` forces when complete) |
| output links | opens `report.md` / `wanted.md` / `wanted.html` / `manifest.jsonl` |

While a job runs, a live log tail streams the run's own console output; buttons
disable until it finishes; the banner shows the last exit code. One job at a
time; the server binds only to 127.0.0.1 so nothing outside this machine can
reach it; no scheduler, no daemon, no background task exists.

Safety in the file server: only `report.md`, `wanted.md`, `wanted.html`,
`manifest.jsonl` are served; everything else → 404.

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

## 3. Full tree (absolute paths)

```
C:\Users\ajibo\md-acquire\
├─ config.yaml                     # adapters, out dir, throttle, contact_email
├─ requirements.txt                # requests, PyYAML
├─ pyproject.toml                  # pytest config (testpaths, pythonpath)
├─ .gitignore
├─ README.md                       # project overview + spec format
├─ docs\
│  └─ MAP.md                       # ← this file
├─ pipeline\                       # the library
│  ├─ models.py                    # WorkSpec, Candidate, Resolution (dataclasses)
│  ├─ config.py                    # Config.load (YAML + ACQUIRE_EMAIL env override)
│  ├─ http.py                      # Client: throttled, retrying, UA-tagged
│  ├─ spec.py                      # parse_file / load_from (MD frontmatter → WorkSpec)
│  ├─ metadata.py                  # enrich(): fills missing ISBN via Open Library
│  ├─ adapters\
│  │  ├─ base.py                   # Adapter ABC (lookup(client, spec) → [Candidate])
│  │  ├─ arxiv.py                  # arXiv Atom API → pdf candidates (score 85/55)
│  │  ├─ openlibrary.py            # OL public scans → pdf (88/80 +5 year); borrowable → hints
│  │  ├─ gutenberg.py              # Gutendex (fallback gutenberg.org) → epub/pdf (90/55)
│  │  ├─ unpaywall.py              # OA copies for DOIs → pdf (70/60/50); needs contact_email
│  │  └─ __init__.py               # CLASSES whitelist + build(names, cfg)
│  ├─ download.py                  # safe_name, filename_for, validate, download
│  ├─ manifest.py                  # Manifest.record → jsonl (ts, sha256, license, url…)
│  ├─ report.py                    # report.md + wanted.md (+ auto wanted.html)
│  ├─ handoff.py                   # manual_links(): search-page links, never fetched
│  ├─ htmlwanted.py                # wanted.md → wanted.html renderer
│  ├─ citations.py                 # citation lines → spec files (CLI: -m pipeline.citations)
│  ├─ bulk.py                      # resume-safe runner over specs\ (used by UI + run.ps1)
│  ├─ webui.py                     # the local trigger UI (loopback http server)
│  └─ cli.py                       # orchestration: enrich → adapters → rank → fallback → save
├─ scripts\
│  ├─ setup.ps1  dev.ps1  run.ps1  ui.ps1   # workflow (schedule/unschedule optional)
├─ tests\                          # 108 offline tests, zero network
│  ├─ conftest.py                  # FakeClient/FakeResponse seam, make_spec/make_config,
│  │                               #   MockAdapter, wire_cli(), pdf/epub payloads
│  ├─ test_bulk.py  test_cli.py  test_spec.py  test_metadata.py  test_adapters.py
│  ├─ test_download.py  test_manifest.py  test_report.py
│  └─ test_pipeline.py  test_citations.py  test_htmlwanted.py   # pre-existing
├─ .github\workflows\windows.yml   # CI: pytest 3.10/3.11/3.12 matrix + CLI smoke
├─ specs\                          # your wants (one .md per work)
│  ├─ attention-is-all-you-need.md
│  ├─ pride-and-prejudice.md
│  └─ thinking-fast-and-slow.md
└─ library\                        # outputs (gitignored)
   ├─ Attention Is All You Need - Vaswani.pdf
   ├─ Pride and Prejudice - Jane Austen.epub / .pdf
   ├─ manifest.jsonl               # provenance: ts, key, source, url, sha256…
   ├─ report.md                    # resolved: N / unresolved: N + table
   ├─ wanted.md                    # unresolved works + search links
   └─ wanted.html                  # same, clickable buttons
```

## 4. How a run flows

```
UI button /run?mode=…        .\scripts\run.ps1
      │                            │
      ▼                            ▼
pipeline.webui.Job  ──────▶ pipeline.bulk.run(cfg, force, dry_run, only)
                                  │  1. parse specs\*.md (bad files skipped, reported)
                                  │  2. read manifest.jsonl + check files on disk
                                  │  3. pending = spec wants format F, F not done-on-disk
                                  ▼
                             pipeline.cli.run(cfg, [spec files], only, dry_run)
                                  │  per spec: enrich (OL ISBN) → adapters.lookup
                                  │  → rank (-score, format order) → group by fmt
                                  │  → per format: try ranked candidates IN ORDER
                                  │    until one downloads AND validates
                                  ▼
                             download.py: cache hit? → sha256; else stream → .part
                             → HTML-sniff → validate (%PDF- / epub mimetype+zip)
                             → atomically rename
                                  ▼
                             manifest.record → report.write (+wanted.html)
```

Exit semantics: UI badges `last …: exit 0/1/2`; dry-run is always 0 (the plan
is the product); real runs are 0 only when nothing is left unresolved.

## 5. Contracts worth remembering

- **Spec** (`specs\<slug>.md`): `---\ntitle: "…"\nauthors: […]\nisbn13: "…"\ndoi: "…"\nyear_min: N\nformats: ["epub","pdf"]\n---` + free notes. ISBN hyphens stripped, DOI prefixes normalized on parse.
- **Resume rule**: a spec is complete only when *every* wanted format has a manifest entry whose file still exists. Delete a file → next run re-fetches it.
- **Fallback rule**: per format, candidates are tried in ranked order until one downloads and validates (one dead mirror can't sink a spec) — pinned by `test_download_failure_falls_back_to_next_candidate`.
- **Borrowable ≠ fetchable**: Open Library `borrowable`/`printdisabled` copies become wanted.md hints, never candidates.
- **Non-open works**: handoff links only (openlibrary-search, WorldCat, Google Books/Scholar, DOI landing) — the pipeline never fetches those hosts; `adapters/__init__.py CLASSES` is the fetch whitelist.
- **Enrichment** fills a missing ISBN only (Open Library; crossref deliberately not used — unreachable from some networks); enrichment failure never fails a run; dry-run still enriches.

## 6. Test suite (what guards what)

| File | Guards |
|---|---|
| `test_spec.py` | frontmatter parsing, defaults, DOI/ISBN normalization, ordering |
| `test_metadata.py` | OL ISBN fill / skip-when-present / failures swallowed |
| `test_adapters.py` | all 4 adapters: URL building, scoring, dedupe, error→[] |
| `test_download.py` | naming (incl. Windows reserved), validation, cache-skip, .part cleanup, HTML rejection |
| `test_manifest.py` | jsonl append, field completeness, parent-dir creation |
| `test_report.py` | resolved/unresolved counts, wanted content, empty-run files |
| `test_cli.py` | orchestration: dry-run never touches candidate URLs, per-format fallback, only-filter, idempotent re-run, single-spec input |
| `test_bulk.py` | manifest tolerance, disk-existence resume cycle, unknown `only`, unparsable-spec survival |
| `test_pipeline.py` / `test_citations.py` / `test_htmlwanted.py` | original 17: adapters, handoff links, citations parser, wanted.html renderer |

Run them: `.\scripts\ui.ps1 → Run test suite` button, or
`.venv\Scripts\python.exe -m pytest`.

## 7. Verified state (as of 2026-10-18)

- 108/108 tests green (~1s, fully offline).
- Every UI route exercised live: dashboard 200, `/status` states, dry-run
  (exit 0), run all (exit 1 with 1 spec genuinely unresolved), per-spec fetch,
  unknown spec key → clean "nothing matches" message, `/test` (exit 0,
  108 passed), file whitelist (404 outside it), wanted.html served.
- `setup.ps1` / `dev.ps1` / `run.ps1` executed for real; adapters answered live
  (arXiv, Gutendex, Open Library, gutenberg.org fallback path included).
- Three real downloads from earlier runs sit in `library\` with manifest
  sha256 entries (arXiv PDF, Gutenberg EPUB, IA scan PDF) — resume treats them
  as complete.
- Known non-result, by design: `thinking-fast-and-slow` stays unresolved —
  Kahneman's book is not openly licensed anywhere the pipeline may fetch; it
  produces wanted.html handoff links instead.

## 8. Boundaries (unchanged and deliberate)

Automated downloading is whitelisted to the four open-access sources above.
Sites that host non-open works are surfaced as **search-page links for you to
click**, never as fetch targets — that line lives in `pipeline/handoff.py`
(links only, never downloaded) and `pipeline/adapters/__init__.py` (the fetch
whitelist). No login, paywall, or scrape-against-terms anywhere in the code.