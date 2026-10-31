"""
Search NSFC projects by main keyword with year/category/discipline splitting.

Usage:
    python scripts/search-keyword.py [keyword]
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
    parser = argparse.ArgumentParser(description="NSFC search by main keyword")
    parser.add_argument("keyword", nargs="?", default=None,
                       help="Keyword (default: first KEYWORDS entry)")
    args = parser.parse_args()

    keyword = args.keyword or (KEYWORDS[0] if KEYWORDS else None)
    if not keyword:
        print("No keyword specified. Set KEYWORDS in config.py or pass as argument.")
        sys.exit(1)

    print("=" * 60)
    print(f"NSFC Search — Main Keyword: {keyword}")
    print("=" * 60)

    print("\n[1/2] Connecting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed to start!"); sys.exit(1)
    else:
        print("  Chrome already running")

    client = CDPClient(CDP_PORT)
    client.connect()

    print("\n[2/2] Searching (keyword → year → category → discipline)...")
    sidebar = get_sidebar_options(client)
    year_opts = sidebar.get("0", {}).get("options", [])
    category_opts = sidebar.get("1", {}).get("options", [])
    discipline_opts = sidebar.get("3", {}).get("options", [])

    seen_ids = load_seen_ids(TASK_FILE)
    runner = SearchRunner(client, seen_ids)
    projects = runner.run(keyword, [year_opts, category_opts, discipline_opts])

    print(f"\n  Found {len(projects)} new projects")
    tasks = load_task_list(TASK_FILE)
    tasks, new_count = merge_tasks(tasks, projects)
    save_task_list(tasks, TASK_FILE)
    print(f"task_list.csv: {len(tasks)} projects ({new_count} new)")
    client.close()


if __name__ == "__main__":
    main()
