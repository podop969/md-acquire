---
name: nsfc-download
description: >
  Download NSFC (国家自然科学基金) final research reports as PDFs through Chrome
  browser automation. Users MUST have specific domain keywords (e.g. 电池, 电解质,
  电极材料, 钙钛矿) before using this tool — it does NOT support random browsing
  or keyword-free downloads. Use when the user wants to batch-download 国自然
  结题报告 for their research field, configure search keywords, set up automated
  report downloading, or troubleshoot download issues.
---

# NSFC Final Research Report Downloader

Automated downloading of NSFC (国家自然科学基金) final research reports (结题报告)
as PDFs. Uses Chrome DevTools Protocol (CDP) for browser interaction,
multi-dimensional search filtering, and image-to-PDF assembly.

**Prerequisite**: Users MUST have domain-specific research keywords before using
this tool. The NSFC site requires keyword-based search — there is no keyword-free
browsing or "download all" capability. If the user does not yet have keywords,
help them define their research scope first (e.g., 电池, 电解质, 钙钛矿,
太阳能电池 for battery research).

## Quick Start for New Users

Guide new users through these steps in order:

1. Install dependencies: `pip install -r requirements.txt`
2. Copy the config template: copy `templates/config-example.py` to the project root as `config.py`
3. Edit `config.py`: set `KEYWORDS`, `CHROME_PATH`, `DOWNLOAD_DIR`
4. Start Chrome with CDP: `python scripts/start-chrome.py`
5. User must manually log into NSFC in the opened browser (captcha/biometric required)
6. Search for projects: `python scripts/search-keyword.py`
7. Enrich metadata: `python scripts/enrich-tasks.py`
8. Download reports: `python scripts/download.py`

**Important**: Each user needs their own NSFC account. Passwords and accounts are never
hardcoded. The tool requires manual browser login — this cannot be automated.

## Configuration

Users edit `config.py` (copied from `templates/config-example.py`):

| Setting | Required | Description |
|---------|----------|-------------|
| `KEYWORDS` | Yes | Main search terms, e.g. `["battery", "electrolyte"]` |
| `CHROME_PATH` | Yes | Path to Chrome executable |
| `DOWNLOAD_DIR` | Yes | Where PDFs are saved |
| `CDP_PORT` | No | Chrome debugging port (default 9222) |
| `REQUEST_DELAY` | No | Seconds between API calls (default 3.0) |

All settings support environment variable override with `NSFC_` prefix
(e.g. `NSFC_CHROME_PATH`, `NSFC_KEYWORDS`).

For advanced search coverage, configure optional keyword lists:
`SUB_KEYWORDS`, `MATERIAL_KEYWORDS`, `COLD_KEYWORDS`, `RERUN_KEYWORDS`.

## Workflow Phases

### Phase 1: Launch Browser & Login
```
python scripts/start-chrome.py
```
Chrome opens with remote debugging on CDP port. User logs into `https://kd.nsfc.cn/`
manually (captcha/biometric required). Keep this Chrome instance running.

### Phase 2: Search & Discovery
Run any combination of search scripts to build task lists:

| Script | Purpose | Uses Config Key |
|--------|---------|-----------------|
| `search-keyword.py` | Main keyword search (year→category→discipline split) | `KEYWORDS[0]` or CLI arg |
| `search-sub-keywords.py` | Fine-grained sub-keywords (year→category split) | `SUB_KEYWORDS` |
| `search-material.py` | Material/component keywords | `MATERIAL_KEYWORDS` |
| `search-institution.py` | Institution dimension (inst→year→keyword split) | `KEYWORDS[0]` |
| `search-cold.py` | Cold/long-tail supplemental keywords | `COLD_KEYWORDS` |
| `search-rerun.py` | Retry after Chrome restart (for degraded state) | `RERUN_KEYWORDS` |

All results merge into `task_list.csv`, with automatic deduplication.

### Phase 3: Enrich Task Metadata
```
python scripts/enrich-tasks.py
```
Fetches project details from NSFC API to fill in missing fields:
申请代码, 项目负责人, 资助经费, 批准年度, 结题年度.
This step is also automatically performed before download.

### Phase 4: Download Reports
```
python scripts/download.py
```
- Extracts auth token from browser localStorage via CDP
- Creates authenticated HTTP session
- Downloads report pages as images, assembles into PDFs in `DOWNLOAD_DIR`
- Updates task status in real time (success/failed/no_report)
- Refreshes auth token every 50 downloads

## Search Strategy (Why Multi-Dimensional Splitting)

NSFC caps search results at 100 per query (10 pages × 10 items). For keywords
with many results, the tool splits by sidebar filters:

1. Search keyword alone — get total count
2. If > 90 results → split by **year** (年度)
3. If still > 90 → split by **funding category** (资助类别)
4. If still > 90 → split by **discipline** (学科) or **institution** (依托单位)

Each combination stays under 100, enabling complete pagination coverage.

## Troubleshooting

Guide users through these common issues:

| Symptom | Cause | Solution |
|---------|-------|----------|
| Chrome fails to start | Wrong `CHROME_PATH` | Check path in config.py; run `chrome.exe` manually to verify |
| "Login timeout" | User didn't complete login | Re-run download.py, ensure logged in at kd.nsfc.cn |
| "No images retrieved" | Token expired or no report | Re-login in browser, re-run download.py |
| Search returns 0 | Browser state degraded | Restart Chrome, use `search-rerun.py` |
| 503 errors during download | NSFC rate limiting | Already handled with retries; reduce REQUEST_DELAY further |

## File Reference

| Path | Purpose |
|------|---------|
| `lib/cdp_client.py` | Chrome DevTools Protocol WebSocket client |
| `lib/browser_launcher.py` | Chrome launcher with remote debugging |
| `lib/config_loader.py` | Config loading with env var override |
| `lib/downloader_lib.py` | Shared Vue state extraction, task management |
| `scripts/download.py` | Main download orchestrator |
| `scripts/enrich-tasks.py` | Fetch project metadata from API |
| `scripts/start-chrome.py` | Launch Chrome for CDP |
| `scripts/search-*.py` | Search scripts (various dimensions) |
| `templates/config-example.py` | Configuration template |
| `task_list.csv` | Task tracking (auto-generated) |

## Important Constraints

- **Never** hardcode credentials or account numbers — each user provides their own
- NSFC login requires manual browser interaction (captcha/biometric)
- The site uses Vue.js; CDP accesses component state (`finalSearchList`)
- Keep `REQUEST_DELAY` at 3+ seconds to avoid rate limiting
- Auth tokens expire; download script auto-refreshes every 50 downloads
- Report images are downloaded one page at a time via API, then assembled server-side
- The tool only works with Chrome (Chromium may also work but is untested)
