"""
Retry search for keywords that returned 0 results (browser state degraded).

Usage:
    python scripts/search-rerun.py
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import RERUN_KEYWORDS, CDP_PORT
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome, terminate_chrome
from lib.downloader_lib import (
    get_sidebar_options, load_seen_ids, merge_tasks, load_task_list,
    save_task_list, SearchRunner, TASK_FILE,
)


def main():
    if not RERUN_KEYWORDS:
        print("No RERUN_KEYWORDS configured in config.py."); sys.exit(1)

    print("=" * 60)
    print(f"NSFC Rerun Search ({len(RERUN_KEYWORDS)})")
    print("=" * 60)

    print("\nRestarting Chrome...")
    terminate_chrome()
    time.sleep(3)
    launch_chrome()
    if not wait_for_cdp(timeout=30):
        print("Chrome failed to start!"); sys.exit(1)

    client = CDPClient(CDP_PORT)
    client.connect()

    sidebar = get_sidebar_options(client)
    year_opts = sidebar.get("0", {}).get("options", [])
    category_opts = sidebar.get("1", {}).get("options", [])

    seen_ids = load_seen_ids(TASK_FILE)
    runner = SearchRunner(client, seen_ids)
    all_new = []
    for kw in RERUN_KEYWORDS:
        print(f"\n{'='*50}")
        print(f"Sub-keyword: {kw}")
        all_new.extend(runner.run(kw, [year_opts, category_opts]))

    print(f"\n{'='*60}")
    print(f"Rerun found {len(all_new)} new projects")
    tasks = load_task_list(TASK_FILE)
    tasks, new_count = merge_tasks(tasks, all_new)
    save_task_list(tasks, TASK_FILE)
    print(f"task_list.csv: {len(tasks)} projects ({new_count} new)")
    client.close()


if __name__ == "__main__":
    main()
