"""
Search NSFC projects by institution dimension (institution → year → sub-keyword).

Usage:
    python scripts/search-institution.py [keyword]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import KEYWORDS, CDP_PORT
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome
from lib.downloader_lib import (
    get_sidebar_options, load_seen_ids, merge_tasks, load_task_list,
    save_task_list, SearchRunner, TASK_FILE,
)


def main():
    parser = argparse.ArgumentParser(description="NSFC search by institution dimension")
    parser.add_argument("keyword", nargs="?", default=None,
                       help="Keyword (default: first KEYWORDS entry)")
    args = parser.parse_args()

    keyword = args.keyword or (KEYWORDS[0] if KEYWORDS else None)
    if not keyword:
        print("No keyword specified."); sys.exit(1)

    print("=" * 60)
    print(f"NSFC Search — Institution Dimension: {keyword}")
    print("=" * 60)

    print("\n[1/3] Starting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed to start!"); sys.exit(1)
    else:
        print("  Chrome already running")

    print("\n[2/3] Connecting CDP...")
    client = CDPClient(CDP_PORT)
    client.connect()

    print(f"\n[3/3] Searching (institution → year → sub-keyword)...")
    sidebar = get_sidebar_options(client)
    inst_opts = sidebar.get("4", {}).get("options", [])
    year_opts = sidebar.get("0", {}).get("options", [])
    kw_opts = sidebar.get("2", {}).get("options", [])

    seen_ids = load_seen_ids(TASK_FILE)
    runner = SearchRunner(client, seen_ids)
    projects = runner.run(keyword, [inst_opts, year_opts, kw_opts])

    print(f"\n  Found {len(projects)} new projects")
    tasks = load_task_list(TASK_FILE)
    tasks, new_count = merge_tasks(tasks, projects)
    save_task_list(tasks, TASK_FILE)
    print(f"task_list.csv: {len(tasks)} projects ({new_count} new)")
    client.close()


if __name__ == "__main__":
    main()
