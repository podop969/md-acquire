# md-acquire — MD-spec → open-access download pipeline

Give it folders of Markdown specs for books/papers. It finds open, legal copies
(arXiv, Project Gutenberg, Open Library public scans, Unpaywall OA copies for
DOIs), downloads PDF/EPUB, verifies the file really is that format, records a
provenance manifest, and writes a report.

For works that are NOT openly licensed, it does not download anything. The
wanted list gets one-click search links (Anna's Archive, Open Library,
WorldCat, Google Books/Scholar) so you decide and click through with your own
browser, on a source and per-title basis you judge for yourself.

## Layout

    md-acquire/
    ├─ config.yaml            # adapters, output dir, throttle, email (Unpaywall)
    ├─ requirements.txt
    ├─ specs/                 # your MD specs (YAML frontmatter per file)
    │  ├─ attention-is-all-you-need.md
    │  ├─ pride-and-prejudice.md
    │  └─ thinking-fast-and-slow.md
    ├─ pipeline/…             # models, config, http, spec, metadata, handoff,
    │  …                      # download, manifest, report, cli, bulk, adapters/
    ├─ scripts/               # setup.ps1 / dev.ps1 / run.ps1 / schedule.ps1
    ├─ .github/workflows/     # windows CI (pytest matrix + CLI smoke)
    └─ tests/                 # offline suite (FakeClient seam, no network)

## Spec format

```markdown
---
title: "Thinking, Fast and Slow"
authors: ["Daniel Kahneman"]
isbn13: "9780374533557"          # optional
doi: "10.1000/xyz"               # optional
year_min: 2011                   # optional
edition_pref: "latest"           # optional: latest (default) | any
formats: ["epub", "pdf"]         # wanted formats, in preference order
priority: "open_access"          # informational
---
Free-text notes.
```

`--specs` accepts a single MD file or a folder (default `specs/`).

## Run

    .\scripts\ui.ps1             # the trigger UI -> http://127.0.0.1:8619 (opens browser)

CLI equivalents (what the UI buttons call):

    python -m pipeline.bulk --dry-run                # what would be fetched
    python -m pipeline.bulk                          # resume-safe bulk pass
    python -m pipeline.bulk --force                  # re-fetch everything
    python -m pipeline.bulk --only pride-and-prejudice
    python -m pipeline.cli --specs specs\more\       # point at other MD files

Docs: `docs\MAP.md` — full map of the tree, flow, contracts, test coverage.

Outputs in `library/`:
- the files themselves, named `Title - Author.epub/.pdf`
- `manifest.jsonl` — one provenance line per saved file (source, URL, license, sha256, year)
- `report.md` — what resolved, per source/format/year/license
- `wanted.md` — unresolved specs with pre-built search links for manual fetching
  (and Open Library borrow hints when a copy is borrowable but not public)

## Scoring / edition choice

Exact normalized title match beats fuzzy. Year bonus: +8 when edition_pref is
"latest" and a year is known, +5 when the candidate year satisfies year_min.
Format preference follows the spec's `formats` order. Per format the ranked
candidates are tried in order until one downloads and validates, so one flaky
mirror can't sink a spec.

## Legal scope (deliberate)

Automated downloading only from open-access/public-domain sources: arXiv,
Project Gutenberg (+Gutendex), Open Library public scans (archive.org),
Unpaywall-reported OA copies. No site is scraped in a way that ignores its
terms; no paywall or login is bypassed. Non-open works are handed to wanted.md
for manual decision. That split is the point of this tool.

## Licence

md-acquire's own code is MIT-licensed (see `LICENSE`). The repositories under
`Extract test/` are third-party code and keep their own licences (or lack of one);
the MIT licence does not apply to them.
