# NSFC Report Downloader - Workflow Guide

## Overview

The NSFC downloader has three phases: browser setup, project discovery, and report downloading.

## Phase 1: Browser Setup

1. Run `python scripts/start-chrome.py`
2. Chrome opens with remote debugging on the configured CDP port
3. Navigate to `https://kd.nsfc.cn/login` and log in with your NSFC account
4. The browser must remain open for the entire download session

## Phase 2: Project Discovery

### Primary Search
Run `python scripts/search-keyword.py` with your main keyword. This script:
- Searches with the keyword alone (to get total count)
- Splits by year, then by funding category, then by discipline
- Each split ensures results stay under 100 (the site limit)
- Deduplicates against existing task lists

### Supplemental Searches
Run additional scripts with specialized keyword lists:

- `search-sub-keywords.py` - Specific sub-keywords for fine-grained coverage
- `search-material.py` - Material and component keywords
- `search-institution.py` - Search by institution dimension
- `search-cold.py` - Cold or long-tail keywords that may have been missed

### Task Lists
- Results are stored in and deduplicated against `task_list.csv`
- Task status: `pending`, `success`, `failed`, `no_report`

## Phase 3: Download

Run `python scripts/download.py`:
1. Connects to Chrome via CDP to extract auth token
2. Verifies API connectivity
3. Downloads each pending task's report pages as images
4. Assembles images into PDFs in `DOWNLOAD_DIR`
5. Updates task status in real time

### Resume Support
If the download is interrupted, re-run `download.py` — it skips already-completed tasks
(those with status `success` and existing PDF files).
