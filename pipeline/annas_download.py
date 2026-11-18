"""Download an explicitly selected Anna record through a visible browser."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .annas_archive import record_md5, validate_base_url
from .annas_browser import _BROWSER_LOCK
from .download import filename_for, validate
from .progress import emit


class MirrorDownloadError(RuntimeError):
    """Safe diagnostic without exposing a signed download URL."""


def ready_download_urls(html: str, page_url: str) -> list[str]:
    """Read provided Download/copy controls, without executing their JavaScript."""
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    for a in soup.select('a[href]'):
        if re.search(r'download (now|with short filename)', a.get_text(' ', strip=True), re.I):
            candidates.append(urljoin(page_url, a['href']))
    for node in soup.select('button, [data-clipboard-text], input[readonly], textarea[readonly]'):
        if node.has_attr('data-clipboard-text'):
            candidates.append(node['data-clipboard-text'])
        if node.name in ('input', 'textarea'):
            candidates.append(node.get('value', node.get_text()).strip())
        # The site uses a JSON string literal inside clipboard.writeText(...).
        match = re.search(r'clipboard\.writeText\(\s*("(?:[^"\\]|\\.)*")\s*\)', node.get('onclick', ''))
        if match:
            with suppress(ValueError):
                candidates.append(json.loads(match.group(1)))
    found = []
    for url in candidates:
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if (parts.scheme in ('http', 'https') and parts.hostname and not parts.username
                and not parts.password and url not in found):
            found.append(url)
    return found


async def transfer_ready_url(context, page, url: str, referer: str, tmp: Path, cand) -> dict | None:
    """Use the verified context's cookie jar; HTML/challenges need browser navigation."""
    response = None
    emit('downloading', 'Transferring the selected file. Transfer size is not available yet.')
    try:
        headers = {'Referer': referer, 'User-Agent': await page.evaluate('navigator.userAgent')}
        try:
            response = await context.request.get(url, headers=headers, timeout=30000,
                                                 ignore_https_errors=False, max_retries=0)
        except Exception as exc:
            detail = str(exc).lower()
            reason = ('TLS certificate validation failed' if 'cert' in detail or 'ssl' in detail
                      else 'file request timed out' if 'timeout' in detail or 'timed out' in detail
                      else 'file server connection failed')
            raise MirrorDownloadError(reason) from exc
        if response.status in (401, 403, 429):
            return None  # The mirror may require its own interactive verification.
        if not response.ok:
            raise MirrorDownloadError(f'file server returned HTTP {response.status}')
        content_type = response.headers.get('content-type', '').lower()
        if 'html' in content_type:
            return None
        body = await response.body()
        if body.lstrip().startswith(b'<'):
            return None
        tmp.write_bytes(body)
        try:
            verify_selected_file(tmp, cand.fmt, cand.extra['md5'])
        except ValueError as exc:
            tmp.unlink(missing_ok=True)
            raise MirrorDownloadError('file failed format or selected-record checksum validation') from exc
        return {'download_host': urlsplit(response.url).hostname, 'partner_page': referer,
                'transport': 'verified-session-request'}
    finally:
        if response is not None:
            await response.dispose()


def slow_download_links(html: str, base_url: str, md5: str) -> list[str]:
    """Only follow free partner links for this record on the configured site."""
    origin = urlsplit(base_url)
    found = []
    for a in BeautifulSoup(html, 'html.parser').select('a[href]'):
        url = urljoin(base_url, a['href'])
        parts = urlsplit(url)
        if ((parts.scheme, parts.netloc) == (origin.scheme, origin.netloc)
                and re.fullmatch(r'/slow_download/' + re.escape(md5) + r'/\d+/\d+', parts.path)
                and not parts.query and not parts.fragment and url not in found):
            found.append(url)
    return found


def verify_selected_file(path: Path, fmt: str, expected_md5: str) -> str:
    emit('validating', 'Checking file format and selected-record checksum.')
    validate(path, fmt)
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b''):
            md5.update(chunk)
            sha.update(chunk)
    if md5.hexdigest() != expected_md5:
        raise ValueError("Downloaded file does not match the selected Anna's Archive record (MD5 mismatch).")
    return sha.hexdigest()


async def _capture_download(cand, tmp: Path, cfg) -> dict:
    try:
        from playwright.async_api import async_playwright, Error, TimeoutError as BrowserTimeout
    except ImportError as exc:
        raise RuntimeError('Install requirements.txt using the Python that runs the dashboard.') from exc

    async with async_playwright() as pw:
        emit('connecting', 'Opening the download browser.')
        channel = cfg.annas_archive_browser_channel
        profile = cfg.annas_archive_profile_dir.resolve()
        profile.mkdir(parents=True, exist_ok=True)
        try:
            context = await pw.chromium.launch_persistent_context(
                str(profile), channel=None if channel == 'chromium' else channel,
                headless=False, accept_downloads=True, timeout=30000,
            )
        except Error as exc:
            raise RuntimeError('Could not open the Anna download browser. Check the browser installation and close other windows using its profile.') from exc
        try:
            downloads = asyncio.Queue()
            navigation_errors = []
            def attach(page):
                page.on('download', lambda item: downloads.put_nowait(item))
                def failed(request):
                    failure = request.failure or ''
                    # ERR_ABORTED is normal when navigation turns into a download.
                    if request.is_navigation_request() and failure != 'net::ERR_ABORTED':
                        navigation_errors.append((page, failure))
                page.on('requestfailed', failed)
            context.on('page', attach)
            for existing in context.pages:
                attach(existing)
            page = context.pages[0] if context.pages else await context.new_page()
            print("  -> Anna's Archive: complete any browser verification in the window that opens.", flush=True)
            emit('waiting', 'Loading the source page. Complete browser verification if prompted.')
            try:
                await page.goto(cand.url, wait_until='domcontentloaded', timeout=30000)
            except BrowserTimeout:
                pass
            slow_url = None
            mirrors = []
            clicked = False
            switch_mirror = False
            last_state = None
            transfer_started = None
            last_failure = ''
            while True:
                if not downloads.empty():
                    item = downloads.get_nowait()
                    print('  -> receiving selected file; validating after transfer...', flush=True)
                    try:
                        emit('downloading', 'Receiving the selected file through the browser.')
                        await item.save_as(str(tmp))
                        return {'download_host': urlsplit(item.url).hostname,
                                'partner_page': slow_url or '', 'transport': 'browser'}
                    except Error:
                        print('  -> partner transfer failed; trying the next listed free mirror.', flush=True)
                        tmp.unlink(missing_ok=True)
                        switch_mirror = True
                if not context.pages:
                    raise RuntimeError('Download browser was closed before a file arrived.')
                if page.is_closed():
                    page = context.pages[0]
                # A popup's initial request can fail before Playwright emits its
                # page event. Detect Chrome's error page as well as requestfailed.
                for tab in list(context.pages):
                    try:
                        code = tab.locator('#error-code')
                        if await code.count():
                            reason = (await code.inner_text(timeout=1000)).strip()
                            if reason.upper().startswith('NET::ERR_') and not any(p == tab for p, _ in navigation_errors):
                                navigation_errors.append((tab, reason))
                    except Error:
                        pass
                if navigation_errors and slow_url:
                    for failed_page, reason in navigation_errors:
                        last_failure = reason
                        print(f'  -> partner connection failed ({reason}); trying the next free mirror.', flush=True)
                        if failed_page != page:
                            with suppress(Error):
                                await failed_page.close()
                    navigation_errors.clear()
                    switch_mirror = True
                if transfer_started is not None and time.monotonic() - transfer_started > 60:
                    last_failure = 'no file arrived from this mirror within 60 seconds'
                    print('  -> no file arrived; trying the next listed free mirror.', flush=True)
                    switch_mirror = True
                if switch_mirror:
                    emit('retrying', 'The mirror failed. Trying another listed free mirror.')
                    if not mirrors:
                        raise RuntimeError('The listed free download mirrors failed. Last failure: ' + last_failure)
                    slow_url = mirrors.pop(0)
                    clicked = False
                    switch_mirror = False
                    transfer_started = None
                    try:
                        await page.goto(slow_url, wait_until='domcontentloaded', timeout=30000)
                    except Error:
                        switch_mirror = True
                    continue
                try:
                    state = (urlsplit(page.url).hostname, await page.title())
                    if state != last_state:
                        print(f'  -> browser: {state[1]} ({state[0]})', flush=True)
                        last_state = state
                    if slow_url is None and urlsplit(page.url).path == urlsplit(cand.url).path:
                        links = slow_download_links(await page.content(), cfg.annas_archive_url, cand.extra['md5'])
                        if links:
                            slow_url, mirrors = links[0], links[1:]
                            print('  -> opening free partner download page; complete any verification or wait shown there.', flush=True)
                            emit('waiting', 'Waiting for the partner download link. Complete verification in the browser if prompted.')
                            await page.goto(slow_url, wait_until='domcontentloaded', timeout=30000)
                    current = urlsplit(page.url)
                    expected = urlsplit(slow_url or '')
                    if (slow_url and not clicked
                            and (current.netloc, current.path) == (expected.netloc, expected.path)):
                        button = page.get_by_role('link', name=re.compile(r'Download now', re.I)).first
                        copy = page.locator('button[onclick*="clipboard.writeText"], [data-clipboard-text], input[readonly], textarea[readonly]')
                        ready = await button.is_visible()
                        if not ready and await copy.count():
                            ready = await copy.first.is_visible()
                        if ready:
                            clicked = True
                            urls = ready_download_urls(await page.content(), page.url)
                            if urls:
                                print('  -> file link is ready; transferring it directly to the app...', flush=True)
                                try:
                                    result = await transfer_ready_url(context, page, urls[0], slow_url, tmp, cand)
                                    if result:
                                        return result
                                except MirrorDownloadError as exc:
                                    last_failure = str(exc)
                                    print(f'  -> {last_failure}; trying the next free mirror.', flush=True)
                                    switch_mirror = True
                                    continue
                                print('  -> mirror needs a browser step; complete any verification shown.', flush=True)
                                emit('waiting', 'The file server needs a browser step. Complete any verification shown; the app will continue automatically.')
                                transfer_started = time.monotonic()
                                # Use the same tab so failures cannot be lost in a popup.
                                await page.goto(urls[0], wait_until='domcontentloaded', timeout=30000)
                            else:
                                print('  -> starting browser download...', flush=True)
                                transfer_started = time.monotonic()
                                await button.click(timeout=5000)
                except Error:
                    # Verification redirects replace the document. Let the normal browser
                    # flow continue; the user can also choose another mirror in this window.
                    if not context.pages:
                        raise RuntimeError('Download browser was closed before a file arrived.')
                await asyncio.sleep(0.5)
        finally:
            with suppress(Exception):
                await context.close()


def download_selected(cand, spec, dest: Path, cfg) -> tuple[Path, str]:
    validate_base_url(cfg.annas_archive_url)
    md5 = record_md5(cand.url)
    if cand.extra.get('md5') != md5 or cand.fmt not in ('pdf', 'epub'):
        raise ValueError('Invalid selected Anna file.')
    if cfg.annas_archive_browser_channel not in ('chrome', 'chromium', 'msedge'):
        raise ValueError('Set annas_archive_browser_channel to chrome, chromium, or msedge.')
    if not 30 <= cfg.annas_archive_download_timeout <= 1800:
        raise ValueError('Set annas_archive_download_timeout between 30 and 1800 seconds.')
    dest.mkdir(parents=True, exist_ok=True)
    name = Path(filename_for(spec, cand))
    # Keep distinct selected editions separate from existing title-only downloads.
    final = dest / f'{name.stem} [aa-{md5}]{name.suffix}'
    if final.exists():
        return final, verify_selected_file(final, cand.fmt, md5)
    if not _BROWSER_LOCK.acquire(blocking=False):
        raise RuntimeError('An Anna browser operation is already running. Finish or close it, then retry Fetch.')
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest, prefix='.anna-', suffix='.part', delete=False) as fh:
            tmp = Path(fh.name)
        async def bounded():
            return await asyncio.wait_for(_capture_download(cand, tmp, cfg), cfg.annas_archive_download_timeout)
        try:
            provenance = asyncio.run(bounded())
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f'Anna download timed out after {cfg.annas_archive_download_timeout:g} seconds. '
                'Retry and complete the browser steps, or increase annas_archive_download_timeout for a longer wait.'
            ) from exc
        sha = verify_selected_file(tmp, cand.fmt, md5)
        tmp.replace(final)
        cand.extra.update(provenance)
        return final, sha
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        _BROWSER_LOCK.release()
