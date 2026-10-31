"""
Start Chrome with remote debugging for NSFC report downloader.

Usage:
    python scripts/start-chrome.py
    # Chrome opens. Log in to https://kd.nsfc.cn/ manually.
    # Then run: python scripts/download.py (or any search script)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.browser_launcher import launch_chrome, wait_for_cdp
from lib.config_loader import NSFC_HOST, CDP_PORT

print("Starting Chrome...")
launch_chrome()
browser_info = wait_for_cdp()
if not browser_info:
    print("Chrome failed to start!")
    sys.exit(1)

print(f"\nChrome is running (CDP port: {CDP_PORT})")
print(f"Open {NSFC_HOST}/login and log in with your NSFC account.")
print(f"After login, run your search or download scripts.")
print(f"\nPress Ctrl+C to exit...")

try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting")
