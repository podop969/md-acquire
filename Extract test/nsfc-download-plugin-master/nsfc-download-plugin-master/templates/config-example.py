"""
NSFC Final Research Report Downloader - Configuration Template
Copy this file to config.py and fill in your values.

Usage:
  1. cp templates/config-example.py config.py
  2. Edit config.py with your own settings
  3. (Optional) Override with environment variables: NSFC_KEYWORDS, NSFC_CHROME_PATH, etc.
"""
import os

# ── REQUIRED ──────────────────────────────────────────────────────────────────

# Your NSFC search keywords (comma-separated list)
KEYWORDS = ["YOUR_KEYWORD_1", "YOUR_KEYWORD_2"]

# Download directory for PDF reports
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "nsfc-reports")

# Chrome executable path
#   Windows:  r"C:\Program Files\Google\Chrome\Application\chrome.exe"
#   macOS:    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
#   Linux:    "/usr/bin/google-chrome"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ── OPTIONAL: Search sub-keyword lists ────────────────────────────────────────
# Leave empty if you only want the main keyword search.

# Sub-keywords for fine-grained search (search-sub-keywords.py)
SUB_KEYWORDS = [
    # "sub_keyword_1",
    # "sub_keyword_2",
]

# Material/component keywords (search-material.py)
MATERIAL_KEYWORDS = [
    # "material_1",
]

# Cold/long-tail supplemental keywords (search-cold.py)
COLD_KEYWORDS = [
    # "cold_keyword_1",
]

# Keywords to retry after Chrome restart (search-rerun.py)
RERUN_KEYWORDS = [
    # "rerun_keyword_1",
]

# ── OPTIONAL: Advanced settings ───────────────────────────────────────────────

# NSFC website
NSFC_HOST = "https://kd.nsfc.cn"

# Chrome DevTools Protocol port
CDP_PORT = 9222

# Rate limiting (seconds between requests)
REQUEST_DELAY = 3.0

# Timeout settings (seconds)
IMAGE_TIMEOUT = 30
PAGE_TIMEOUT = 60

# Search limits (NSFC caps at 100 results per query)
RESULTS_PER_PAGE = 10
MAX_PAGES_PER_SEARCH = 10
MAX_RESULTS_THRESHOLD = 90
