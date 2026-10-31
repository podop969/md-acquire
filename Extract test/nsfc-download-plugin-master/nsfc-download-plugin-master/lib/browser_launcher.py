"""
Launch Chrome with remote debugging port enabled.
"""
import subprocess
import os
import tempfile
import time
import requests

from .config_loader import CHROME_PATH, CDP_PORT, NSFC_HOST

_chrome_process = None


def launch_chrome():
    global _chrome_process
    user_data_dir = os.path.join(tempfile.gettempdir(), "nsfc_chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        f"{NSFC_HOST}/login",
    ]

    print(f"Starting Chrome (CDP port: {CDP_PORT})...")
    _chrome_process = subprocess.Popen(args)
    return user_data_dir


def terminate_chrome():
    """Gracefully terminate the Chrome process we launched."""
    global _chrome_process
    if _chrome_process is not None:
        try:
            _chrome_process.terminate()
            _chrome_process.wait(timeout=5)
        except Exception:
            try:
                _chrome_process.kill()
            except Exception:
                pass
        _chrome_process = None
        print("Chrome terminated.")


def wait_for_cdp(timeout=60):
    print("Waiting for CDP...", end="")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            if resp.status_code == 200:
                print(" OK")
                return resp.json()
        except requests.ConnectionError:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print("\nTimeout: Chrome failed to start.")
    return None


def login_prompt():
    print("\n" + "=" * 60)
    print("Please log in to NSFC in the opened browser window:")
    print("  URL: https://kd.nsfc.cn/")
    print("  (Use your own NSFC account)")
    print("")
    print("Note:")
    print("  1. After login, the page will redirect to the site home")
    print("  2. Make sure you can see the search page before continuing")
    print("=" * 60)
    input("\nPress Enter after logging in...")
