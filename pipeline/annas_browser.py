"""Visible, user-assisted browser search, isolated from the other catalogues."""
from __future__ import annotations

from contextlib import suppress
import threading
import time
from urllib.parse import urlencode

from .annas_archive import AnnaSearchError, parse_results, validate_base_url
from .config import Config

_BROWSER_LOCK = threading.Lock()


def _playwright():
    # Keep all other sources usable if the optional browser installation is missing.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AnnaSearchError(
            "Anna's Archive needs Playwright. Install requirements.txt using the Python that runs the dashboard."
        ) from exc
    return sync_playwright()


def lookup(query: str, cfg: Config) -> list[dict]:
    validate_base_url(cfg.annas_archive_url)
    if cfg.annas_archive_browser_channel not in ('chrome', 'chromium', 'msedge'):
        raise AnnaSearchError('Set annas_archive_browser_channel to chrome, chromium, or msedge.')
    if not 10 <= cfg.annas_archive_browser_timeout <= 300:
        raise AnnaSearchError('Set annas_archive_browser_timeout between 10 and 300 seconds.')
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise AnnaSearchError("An Anna's Archive browser operation is already running. Wait for it or close its window, then retry.")
    context = None
    try:
        with _playwright() as pw:
            try:
                deadline = time.monotonic() + cfg.annas_archive_browser_timeout
                profile = cfg.annas_archive_profile_dir.resolve()
                profile.mkdir(parents=True, exist_ok=True)
                channel = cfg.annas_archive_browser_channel
                try:
                    context = pw.chromium.launch_persistent_context(
                        str(profile), channel=None if channel == 'chromium' else channel,
                        headless=False, timeout=30000,
                    )
                except Exception as exc:
                    raise AnnaSearchError(
                        "Anna's Archive could not open its browser. Install Chrome, or install Playwright Chromium "
                        "with 'python -m playwright install chromium' and set annas_archive_browser_channel: chromium. "
                        "Close any other window using the app's browser profile before retrying."
                    ) from exc
                page = context.pages[0] if context.pages else context.new_page()
                url = cfg.annas_archive_url.rstrip('/') + '/search?' + urlencode({'q': query, 'check': '1'})
                from playwright.sync_api import TimeoutError as BrowserTimeout
                try:
                    page.goto(url, wait_until='domcontentloaded',
                              timeout=max(1, min(30000, int((deadline - time.monotonic()) * 1000))))
                except BrowserTimeout:
                    pass  # Verification can still finish after the initial navigation timeout.
                last_error = None
                while time.monotonic() < deadline:
                    if page.is_closed():
                        raise AnnaSearchError("Anna's Archive browser window was closed before results loaded. Search again to retry.")
                    try:
                        return parse_results(page.content(), cfg.annas_archive_url)
                    except AnnaSearchError as exc:
                        last_error = exc
                    except Exception:
                        # A challenge redirect can briefly replace the page during content().
                        pass
                    page.wait_for_timeout(min(500, max(1, int((deadline - time.monotonic()) * 1000))))
                detail = f' {last_error}' if last_error else ''
                raise AnnaSearchError(
                    f"Anna's Archive search timed out after {cfg.annas_archive_browser_timeout:g} seconds. "
                    'Complete verification in the browser window when you retry.' + detail
                )
            finally:
                if context is not None:
                    with suppress(Exception):
                        context.close()
    except AnnaSearchError:
        raise
    except Exception as exc:
        raise AnnaSearchError(
            "Anna's Archive browser could not load the search page or was closed. Check the connection and retry."
        ) from exc
    finally:
        _BROWSER_LOCK.release()
