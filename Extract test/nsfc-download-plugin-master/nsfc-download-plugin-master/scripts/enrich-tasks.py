"""
Enrich NSFC task list with project metadata from API.

Fetches missing fields (application code, PI, funding, approval/conclusion year)
for each pending task before downloading reports.

Usage:
    python scripts/enrich-tasks.py [--task-list TASK_LIST_FILE]
"""
import os
import sys
import time
import argparse

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import NSFC_HOST, CDP_PORT, REQUEST_DELAY
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome
from lib.downloader_lib import (
    load_task_list, save_task_list, enrich_tasks, TASK_FILE,
)


def extract_token(client):
    result = client.evaluate_js("localStorage.getItem('access')")
    return result.get("result", {}).get("value", "")


def create_session(token):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Authorization": f"Bearer {token}",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded",
        "origin": NSFC_HOST,
    })
    return s


def main():
    parser = argparse.ArgumentParser(description="Enrich NSFC task list with API metadata")
    parser.add_argument("--task-list", default=None,
                       help="Task list CSV path (default: task_list.csv)")
    parser.add_argument("--force", action="store_true",
                       help="Re-enrich even already-filled tasks")
    args = parser.parse_args()

    task_file = args.task_list or TASK_FILE

    if not os.path.exists(task_file):
        print(f"Task list not found: {task_file}")
        print("Run a search script first.")
        sys.exit(1)

    tasks = load_task_list(task_file)
    print(f"Loaded {len(tasks)} tasks from {os.path.basename(task_file)}")

    # Connect to Chrome for auth token
    print("\n[1/3] Connecting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed to start!")
            sys.exit(1)
    else:
        print("  Chrome already running")

    print("\n[2/3] Getting auth token...")
    client = CDPClient(CDP_PORT)
    client.connect()
    token = extract_token(client)
    if not token:
        print("\nPlease log in to your NSFC account in the browser...")
        print("Waiting for login...", end="", flush=True)
        for _ in range(120):
            time.sleep(2)
            token = extract_token(client)
            if token:
                break
            print(".", end="", flush=True)
        if not token:
            print("\nLogin timeout. Exiting.")
            sys.exit(1)
        print(" OK")
    print(f"Token: {token[:30]}...")
    session = create_session(token)
    client.close()

    # Enrich
    print(f"\n[3/3] Enriching tasks...")
    target = tasks if args.force else [t for t in tasks if not t.get("personInCharge") and not t.get("projectAdmin")]
    print(f"  Targets: {len(target)} tasks need enrichment")
    enrich_tasks(session, target, delay=REQUEST_DELAY)
    save_task_list(tasks, task_file)
    print(f"Saved to {task_file}")


if __name__ == "__main__":
    main()
