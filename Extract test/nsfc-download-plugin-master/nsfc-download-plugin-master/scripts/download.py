"""
NSFC Final Research Report Downloader.

Downloads report images from NSFC project detail pages and assembles them into
PDF files. Requires Chrome with CDP for auth token extraction.

Usage:
    python scripts/download.py [--task-list TASK_FILE]
"""
import os
import sys
import time
import uuid
import shutil
import tempfile
import argparse
from datetime import datetime

import requests
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config_loader import (
    NSFC_HOST, DOWNLOAD_DIR, CDP_PORT, REQUEST_DELAY,
)
from lib.cdp_client import CDPClient
from lib.browser_launcher import wait_for_cdp, launch_chrome, terminate_chrome
from lib.downloader_lib import (
    load_task_list, save_task_list, enrich_task, TASK_FILE,
)
from lib.notify import push

# ── Auth ──────────────────────────────────────────────────────────────────────

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


# ── Download ──────────────────────────────────────────────────────────────────

_MAX_NAME_LEN = 200


def _safe_filename(name, download_dir):
    """Build a safe PDF path: sanitize, truncate, resolve conflicts."""
    safe = "".join(c for c in name if c not in r'\/:*?"<>|')
    safe = safe.strip(". ") or "report"
    if len(safe) > _MAX_NAME_LEN:
        safe = safe[:_MAX_NAME_LEN]

    path = os.path.join(download_dir, f"{safe}.pdf")
    if os.path.exists(path):
        tag = str(uuid.uuid4())[:8]
        path = os.path.join(download_dir, f"{safe}_{tag}.pdf")
    return path


def download_project(session, project_id, project_name):
    """Download report images and pack into PDF using streaming assembly.

    Writes each page image to a temp file instead of holding all in memory.
    Returns (status, error).
    """
    info = None
    for attempt in range(3):
        try:
            resp = session.post(
                f"{NSFC_HOST}/api/baseQuery/conclusionProjectInfo/{project_id}",
                timeout=15)
            if resp.status_code == 503:
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code != 200 or not resp.text.strip():
                return "no_report", f"API status {resp.status_code}"
            info = resp.json().get("data", {})
            break
        except Exception:
            time.sleep(3)

    if not info or not isinstance(info, dict) or not info:
        return "no_report", "No project data"
    if not info.get("hasReport"):
        return "no_report", "No final report uploaded"

    name = info.get("projectName", project_name)
    pdf_path = _safe_filename(name, DOWNLOAD_DIR)

    if os.path.exists(pdf_path):
        return "success", ""

    # Stream pages to temp files
    tmp_dir = tempfile.mkdtemp(prefix="nsfc_")
    page_files = []
    try:
        for pi in range(1, 200):
            url = None
            for retry in range(3):
                try:
                    resp = session.post(
                        f"{NSFC_HOST}/api/baseQuery/completeProjectReport",
                        data={"id": project_id, "index": str(pi)}, timeout=15)
                    if resp.status_code == 503:
                        time.sleep(5 * (retry + 1))
                        continue
                    if resp.status_code != 200 or not resp.text.strip():
                        break
                    url = resp.json().get("data", {}).get("url", "")
                    break
                except Exception:
                    time.sleep(2)
            if not url:
                break

            for retry2 in range(3):
                try:
                    img_resp = session.get(NSFC_HOST + url, timeout=30)
                    if img_resp.status_code == 503:
                        time.sleep(5 * (retry2 + 1))
                        continue
                    break
                except Exception:
                    time.sleep(2)
            if img_resp.status_code == 200 and len(img_resp.content) > 1024:
                tmp_path = os.path.join(tmp_dir, f"{pi:04d}.img")
                with open(tmp_path, "wb") as f:
                    f.write(img_resp.content)
                page_files.append((tmp_path, pi))
                if pi % 10 == 1 or pi <= 3:
                    print(f"    Page {pi} OK ({len(img_resp.content)} bytes)")
            else:
                break
            time.sleep(REQUEST_DELAY)

        if not page_files:
            return "failed", "No images retrieved"

        # Assemble PDF from temp files
        page_files.sort(key=lambda x: x[1])
        pil_images = []
        for tmp_path, _ in page_files:
            try:
                pil_images.append(Image.open(tmp_path))
            except Exception:
                pass
        if not pil_images:
            return "failed", "PDF generation failed"

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        pil_images[0].save(pdf_path, "PDF", resolution=100.0,
                           save_all=True, append_images=pil_images[1:])
        return "success", ""

    finally:
        for tmp_path, _ in page_files:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSFC Final Report Downloader")
    parser.add_argument("--task-list", default=None,
                       help="Task list CSV path (default: task_list.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("NSFC Final Report Downloader")
    print("=" * 60)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Determine task list file
    task_file = args.task_list or TASK_FILE

    tasks = load_task_list(task_file)
    pending = [t for t in tasks if t["status"] == "pending"]
    print(f"Tasks: {len(tasks)} total, {len(pending)} pending")

    # Launch Chrome (needed for auth token)
    print("\n[1/5] Starting Chrome...")
    if not wait_for_cdp(timeout=2):
        launch_chrome()
        if not wait_for_cdp():
            print("Chrome failed to start!")
            sys.exit(1)
    else:
        print("  Chrome already running")

    # Connect & auth
    print("\n[2/5] Getting auth token...")
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
    print("  CDP closed")

    # Verify API
    print("  Testing API...", end="")
    resp = session.post(
        f"{NSFC_HOST}/api/baseQuery/conclusionProjectInfo/d2ba133ee2e6748c133d86bf52b1dd80",
        timeout=15)
    if resp.status_code != 200 or not resp.json().get("data"):
        print(" failed")
        sys.exit(1)
    print(" OK")

    # Enrich task metadata before downloading
    print(f"\n[3/5] Enriching task metadata...")
    pending = [t for t in tasks if t["status"] == "pending"]
    need_enrich = [t for t in pending if not t.get("projectAdmin") and not t.get("personInCharge")]
    if need_enrich:
        print(f"  {len(need_enrich)} tasks need enrichment, fetching from API...")
        for i, task in enumerate(need_enrich):
            enrich_task(session, task)
            if (i + 1) % max(1, len(need_enrich) // 10) == 0:
                print(f"  [{i+1}/{len(need_enrich)}] enriched")
            time.sleep(REQUEST_DELAY)
        save_task_list(tasks, task_file)
        print(f"  Enrichment complete")
    else:
        print(f"  All {len(pending)} tasks already enriched")

    # Task list summary
    print(f"\n[4/5] Downloading reports...")
    print(f"\n{'─'*60}")
    print(f"Download directory: {DOWNLOAD_DIR}")
    print(f"{'─'*60}")

    success_count = sum(1 for t in tasks if t["status"] == "success")
    failed_count = sum(1 for t in tasks if t["status"] == "failed")
    no_report_count = sum(1 for t in tasks if t["status"] == "no_report")
    pending = [t for t in tasks if t["status"] == "pending"]

    print(f"Total: {len(tasks)} | Pending: {len(pending)} | Done: {success_count} | No-report: {no_report_count} | Failed: {failed_count}")
    print(f"{'─'*60}")

    if not pending:
        print("No pending tasks. All done!")
        sys.exit(0)

    # Disk space check (warn if < 500MB)
    usage = shutil.disk_usage(DOWNLOAD_DIR)
    free_mb = usage.free // (1024 * 1024)
    if free_mb < 100:
        print(f"ERROR: Only {free_mb}MB free on disk. Need at least 100MB.")
        sys.exit(1)
    if free_mb < 500:
        print(f"WARNING: Only {free_mb}MB free on disk. Downloads may fail.")
        push("磁盘空间不足", f"仅剩 {free_mb}MB，下载可能失败")
    print(f"Disk free: {free_mb}MB")

    # Print pending task list (first 20)
    show_n = min(len(pending), 20)
    print(f"\nPending tasks ({show_n}/{len(pending)} shown):")
    for i, t in enumerate(pending[:show_n]):
        pid = t.get("id", "")[:12]
        name = (t.get("name") or "")[:50]
        kw = t.get("keyword", "")[:12]
        pi = t.get("personInCharge", "")[:8]
        unit = t.get("unit", "")[:15]
        print(f"  {i+1:3d}. [{pid}] {name}")
        print(f"       keyword={kw}  PI={pi}  unit={unit}")

    if len(pending) > show_n:
        print(f"  ... and {len(pending) - show_n} more")

    print(f"\n{'─'*60}")
    print(f"Starting download of {len(pending)} reports to:")
    print(f"  {DOWNLOAD_DIR}")
    print(f"{'─'*60}")

    for i, task in enumerate(pending):
        try:
            print(f"\n[{i+1}/{len(pending)}] {task['name'][:40]}")
        except UnicodeEncodeError:
            print(f"\n[{i+1}/{len(pending)}] <unicode name>")

        try:
            # Refresh token periodically
            if i > 0 and i % 50 == 0:
                print("  Refreshing token...")
                try:
                    client = CDPClient(CDP_PORT)
                    client.connect()
                    new_token = extract_token(client)
                    if new_token:
                        session = create_session(new_token)
                    client.close()
                except Exception:
                    print("  CDP connection lost — Chrome may have crashed.")
                    for t in pending[i:]:
                        t["status"] = "connection_lost"
                        t["error"] = "Chrome CDP unreachable during token refresh"
                        t["updated_at"] = datetime.now().isoformat()
                    save_task_list(tasks, task_file)
                    terminate_chrome()
                    push("Token 刷新失败", f"Chrome CDP 不可达，{len(pending) - i} 个任务已标记为 connection_lost")
                    sys.exit(1)
            status, error = download_project(session, task["id"], task["name"])
            task["status"] = status
            task["error"] = error
        except Exception as e:
            task["status"] = "failed"
            task["error"] = str(e)
        task["updated_at"] = datetime.now().isoformat()
        save_task_list(tasks, task_file)
        if task["status"] in ("failed", "no_report"):
            print(f"  [{task['status']}] {task['error']}")
        time.sleep(REQUEST_DELAY)

    success = sum(1 for t in tasks if t["status"] == "success")
    failed = sum(1 for t in tasks if t["status"] == "failed")
    no_report = sum(1 for t in tasks if t["status"] == "no_report")
    print(f"\n{'='*60}")
    print(f"Complete! Success: {success}  Failed: {failed}  No-report: {no_report}  Total: {len(tasks)}")
    print(f"Directory: {DOWNLOAD_DIR}")
    push("下载完成", f"成功 {success} / 失败 {failed} / 无报告 {no_report}，共 {len(tasks)} 条")


if __name__ == "__main__":
    main()
