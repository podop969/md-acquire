"""
Supplemental cold/long-tail keyword search (year split only).

Usage:
    python scripts/search-cold.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import COLD_KEYWORDS, CDP_PORT
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome
from lib.downloader_lib import (
    get_sidebar_options, load_seen_ids, merge_tasks, load_task_list,
    save_task_list, SearchRunner, TASK_FILE,
)


def main():
    if not COLD_KEYWORDS:
        print("No COLD_KEYWORDS configured in config.py."); sys.exit(1)

    print("=" * 60)
    print(f"NSFC Search — Cold Keywords ({len(COLD_KEYWORDS)})")
    print("=" * 60)

    print("\nConnecting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed to start!"); sys.exit(1)
    else:
        print("  Chrome already running")

    client = CDPClient(CDP_PORT)
    client.connect()

    sidebar = get_sidebar_options(client)
    year_opts = sidebar.get("0", {}).get("options", [])

    seen_ids = load_seen_ids(TASK_FILE)
    runner = SearchRunner(client, seen_ids)
    all_new = []
    for kw in COLD_KEYWORDS:
        print(f"\n{'='*50}")
        print(f"Keyword: {kw}")
        all_new.extend(runner.run(kw, [year_opts]))

    print(f"\n{'='*60}")
    print(f"Found {len(all_new)} new projects")
    tasks = load_task_list(TASK_FILE)
    tasks, new_count = merge_tasks(tasks, all_new)
    save_task_list(tasks, TASK_FILE)
    print(f"task_list.csv: {len(tasks)} projects ({new_count} new)")
    client.close()


if __name__ == "__main__":
    main()
