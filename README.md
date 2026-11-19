# md-acquire — MD-spec → open-access download pipeline

Give it folders of Markdown specs for books/papers. It finds open, legal copies
(arXiv, Project Gutenberg, Open Library public scans, Unpaywall OA copies for
DOIs), downloads PDF/EPUB, verifies the file really is that format, records a
provenance manifest, and writes a report.

It can also download a specific PDF/EPUB explicitly selected from Anna's Archive
through a visible browser. Verification and waiting steps may require your
interaction. Unresolved specs get manual search links in the wanted list.

## Library and reader

Open **My library** from the dashboard (or `/library`) to browse PDF and EPUB files in the configured download folder. Titles and authors come from the download manifest; files added directly to that folder also appear, using their filenames. Filter the library by title or author, choose **Read / Continue reading**, or use **Show in folder** to reveal the file on the computer running the app.

EPUB cards display embedded JPEG/PNG/GIF/WebP covers when available. PDF cards display the first page. A title card remains when a preview is unavailable. Files outside the download folder and symlinks are excluded.

The reader provides previous/next navigation and a page/chapter number field. PDFs also have zoom controls. Page/chapter and scroll positions save to `.reading-positions.json` in the download folder, surviving browser and server restarts. **Open original file** is available for use with another reader. Positions are shared locally, rather than separated into user accounts.

PDF rendering uses locally bundled [Mozilla PDF.js](https://mozilla.github.io/pdf.js/) 6.5.438 (license and version in `pipeline/static/pdfjs`). Reading does not need an external CDN. EPUBs use a simplified text-and-image layout in spine order; scripts, external resources, original styling, and navigation links are stripped. This first reader does not support DRM-protected books, annotations, or PDF text selection/search.

The optional browser integration check is `python tests/browser_library_smoke.py`; it uses temporary sample books and installed Chrome to check rendering, PDF thumbnails, and saved reading positions without accessing your library.

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

## Anna's Archive search and selected-file downloads

The UI can include Anna's Archive metadata alongside the other search sources.
Install `requirements.txt`, add `annas_archive` to `adapters` in `config.yaml`,
and set `annas_archive_url` to the site's base address (default:
`https://annas-archive.gl`). This repository's config enables it.
Restart the UI after updating dependencies and code. The repository's config
sets `annas_archive_mode: browser`: only Anna's Archive opens a visible browser.
Open Library, Gutenberg, and arXiv keep their HTTP/API search paths; Unpaywall
still checks DOIs during fetching.

Search requests use `/search?q=<encoded query>&check=1`. BeautifulSoup extracts
up to eight records, including titles, authors, listed formats, and source-page
links. **Add to specs** saves the exact Anna record for PDF/EPUB results:
`source: annas_archive`, `source_url: https://…/md5/<hash>`, and
`source_format: epub` (or `pdf`). Other file types cannot be added for downloading.
Listed formats describe the record, not verified download availability.

**Fetch** prioritizes this selected file. It opens the book page, extracts its
free partner-server links, and follows the first one. Once a visible download
or copy-link control is ready, the app reads the supplied file URL and transfers
it using the verified browser context's cookie jar. You do not need to copy or
paste the link. If the mirror needs another browser step, the app opens it in
the same verification tab and captures the resulting download. Complete any
verification or waiting steps shown there. Connection and certificate errors cause another listed free
mirror to be tried; certificate verification is never disabled. This is not a
guarantee that every mirror works. Fast member links are not selected automatically.
A live Van Helsing EPUB transfer was verified on 2026-11-01: the first mirror
failed certificate validation, the second delivered the file, and its format
and selected-record MD5 checks passed.

The entire browser download is bounded by `annas_archive_download_timeout`
(default 300 seconds, configurable from 30 to 1800). The saved PDF/EPUB must
pass format validation and match the selected record's MD5. Failed and partial
files are removed. Successful files include `[aa-<hash>]` in their names to
keep editions separate; the manifest records the book page, hash, download
host, and SHA256 without storing signed download URLs or session cookies.
If this candidate fails, existing sources may still supply a fallback for the
requested format; the log and manifest identify which source actually succeeded.

Older specs created before this feature have no record link. Re-add the desired
Anna result to create a new linked spec; the old spec and any notes are preserved.
Different Anna file IDs remain separate even if titles match. Dry runs do not
open a download browser. Downloads always use the browser, even if search mode
is `http`.

Anna's Archive runs in a separate dashboard request, so other results appear
while browser verification is pending. Complete any verification yourself in
the browser window. It closes after results are read or after
`annas_archive_browser_timeout` seconds (default 120, allowed 10–300). Closing
the window early cancels that source. One Anna browser operation (search or
download) runs at a time; other-source searches and downloads are independent.
If an Anna search is still open, finish it before fetching an Anna file.

Install the dependencies using the Python that runs the UI. With the default
`annas_archive_browser_channel: chrome`, Google Chrome must be installed.
Alternatively run `python -m playwright install chromium` and set the channel
to `chromium`. The dedicated profile at `annas_archive_profile_dir` saves browser
state separately from your normal browser and is ignored by Git under `.browser/`.
Relative profile paths are resolved against the config file's folder. If you
customize this path, keep the profile out of version control as it can contain
cookies. The site may require verification again on later searches.

Set `annas_archive_mode: http` for ordinary requests without a browser (these
may be blocked by DDoS-Guard). Configurations that omit the mode retain HTTP
behavior. The parser supports both an older saved layout and the current layout
captured during a successful visible-browser test on 2026-10-31. Challenges,
timeouts, and layout changes produce warnings without discarding other results.

## Scoring / edition choice

Exact normalized title match beats fuzzy. Year bonus: +8 when edition_pref is
"latest" and a year is known, +5 when the candidate year satisfies year_min.
Format preference follows the spec's `formats` order. Per format the ranked
candidates are tried in order until one downloads and validates, so one flaky
mirror can't sink a spec.

## Source behavior

Title-based lookup uses arXiv, Project Gutenberg (+Gutendex), Open Library
public scans, and Unpaywall-reported OA copies. Anna's Archive downloads are
attempted only for specs retaining a user-selected record link; its license is
recorded as unverified. Login, browser verification, and access restrictions
are not bypassed. Unresolved specs receive manual links in the wanted list.

## Download status

The dashboard displays the current book, source, elapsed time, and download stage above the log. It shows received bytes for streamed downloads and a progress bar when the server supplies a usable file size. Browser transfers show their stage without an estimated percentage.

For Anna’s Archive, the status card indicates when you may need to complete browser verification. Transfers continue automatically when a supported download link becomes available. Files are checked before being reported as saved. Missing requested formats are reported as partial downloads; authorization, connection, and certificate failures have readable explanations. Completed results remain visible across page reloads until another job starts or the server restarts.

## Licence

md-acquire's own code is MIT-licensed (see `LICENSE`). The repositories under
`Extract test/` are third-party code and keep their own licences (or lack of one);
the MIT licence does not apply to them.
