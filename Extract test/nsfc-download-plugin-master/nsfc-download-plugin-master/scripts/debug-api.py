"""
Diagnostic script: print raw API response for a project to verify field names.

Usage:
    python scripts/debug-api.py <project_id>

Example:
    python scripts/debug-api.py d2ba133ee2e6748c133d86bf52b1dd80
"""
import json
import sys
import os
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import NSFC_HOST, CDP_PORT
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome


def extract_token(client):
    result = client.evaluate_js("localStorage.getItem('access')")
    return result.get("result", {}).get("value", "")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug-api.py <project_id>")
        print("Example: python scripts/debug-api.py d2ba133ee2e6748c133d86bf52b1dd80")
        sys.exit(1)

    project_id = sys.argv[1]

    # Connect Chrome
    print("Connecting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed!"); sys.exit(1)
    else:
        print("  Chrome running")

    client = CDPClient(CDP_PORT)
    client.connect()
    token = extract_token(client)
    if not token:
        print("Login timeout"); sys.exit(1)
    client.close()

    # Call API
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Authorization": f"Bearer {token}",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded",
        "origin": NSFC_HOST,
    })

    url = f"{NSFC_HOST}/api/baseQuery/conclusionProjectInfo/{project_id}"
    print(f"\nAPI: {url}")
    resp = session.post(url, timeout=15)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"\nFull response:\n{json.dumps(data, ensure_ascii=False, indent=2)}")

    inner = data.get("data", {})
    if inner:
        print(f"\n--- data keys ({len(inner)} fields) ---")
        for k, v in inner.items():
            val_str = str(v)[:120]
            print(f"  {k:30s} = {val_str}")

        # Check against our field mappings
        print(f"\n--- field mapping check ---")
        from lib.downloader_lib import _FIELD_MAP, _extract_year
        for target, candidates in _FIELD_MAP.items():
            found = [c for c in candidates if c in inner]
            if found:
                print(f"  {target}: OK -> {found[0]} = {inner[found[0]]}")
            else:
                similar = [k for k in inner if any(c.lower() in k.lower() for c in candidates)]
                print(f"  {target}: MISSING (tried: {candidates})")
                if similar:
                    print(f"           similar keys: {similar}")

        # Check year extraction
        scope = inner.get("researchTimeScope", "")
        if scope:
            print(f"\n--- year extraction from researchTimeScope ---")
            print(f"  scope string: {scope}")
            print(f"  approvalYear  = {_extract_year(scope, 0)}")
            print(f"  conclusionYear = {_extract_year(scope, -1)}")


if __name__ == "__main__":
    main()
