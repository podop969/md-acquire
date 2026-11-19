import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import annas_download, cli, search
from pipeline.adapters.annas_archive import AnnasArchiveAdapter
from pipeline.annas_archive import record_md5
from pipeline.annas_browser import _BROWSER_LOCK
from pipeline.models import Candidate, WorkSpec
from pipeline.spec import parse_file
from tests.conftest import wire_cli

BASE = 'https://annas-archive.gl'


@pytest.fixture
def selected(make_config, pdf_bytes):
    cfg = make_config(adapters=['annas_archive'])
    md5 = hashlib.md5(pdf_bytes).hexdigest()
    book = dict(title='Selected book', authors=['Writer'], formats=['pdf'], source='annas_archive',
                source_url=BASE + '/md5/' + md5, listed_format='pdf')
    key, _ = search.add_spec(book, cfg.specs_dir)
    spec = parse_file(cfg.specs_dir / (key + '.md'))
    cand = AnnasArchiveAdapter(cfg).lookup(None, spec)[0]
    return cfg, spec, cand, book


def test_selection_roundtrip_and_distinct_editions(selected):
    cfg, spec, cand, book = selected
    assert spec.source == 'annas_archive'
    assert spec.source_url == book['source_url']
    assert spec.source_format == 'pdf'
    assert cand.url == book['source_url']
    assert cand.extra['md5'] == record_md5(book['source_url'])
    assert search.add_spec(book, cfg.specs_dir) == (spec.key, False)
    different = dict(book, source_url=BASE + '/md5/' + 'b' * 32)
    key2, created = search.add_spec(different, cfg.specs_dir)
    assert created and key2 != spec.key
    legacy = dict(title=book['title'], authors=book['authors'], formats=['pdf'])
    key3, created = search.add_spec(legacy, cfg.specs_dir)
    assert created and key3 not in (spec.key, key2)
    assert search.add_spec(book, cfg.specs_dir) == (spec.key, False)


def test_legacy_spec_does_not_swallow_new_selection(selected):
    cfg, spec, _, book = selected
    path = spec.source_path
    path.write_text('---\ntitle: Selected book\nauthors: [Writer]\nformats: [pdf]\n---\nPersonal notes\n')
    before = path.read_bytes()
    key, created = search.add_spec(book, cfg.specs_dir)
    assert created and key != spec.key
    assert path.read_bytes() == before


@pytest.mark.parametrize('url', ['file:///tmp/book', 'javascript:alert(1)', BASE + '/search?q=x',
                              BASE + '/md5/not-a-hash', BASE + '/md5/' + 'a' * 32 + '?token=x'])
def test_rejects_invalid_record_urls(url):
    with pytest.raises(ValueError):
        record_md5(url)


def test_requires_supported_format_and_resolves_current_site(selected):
    cfg, spec, _, book = selected
    with pytest.raises(ValueError, match='PDF or EPUB'):
        search.add_spec(dict(book, listed_format='mobi'), cfg.specs_dir)
    cfg.annas_archive_url = 'https://new-site.example'
    cand = AnnasArchiveAdapter(cfg).lookup(None, spec)[0]
    assert cand.url.startswith(cfg.annas_archive_url + '/md5/')
    assert cand.extra['selected_source_url'] == book['source_url']
    assert AnnasArchiveAdapter(cfg).lookup(None, WorkSpec('plain', 'Book')) == []


def test_mirror_parser_only_accepts_this_file_and_site():
    md5 = 'a' * 32
    url = f'/slow_download/{md5}/0/0'
    html = f'''<a href="{url}">Slow Partner Server #1</a>
        <a href="{url}">Duplicate</a><a href="https://evil.example{url}">Other</a>
        <a href="/fast_download/{md5}/0/0">Fast</a>
        <a href="/slow_download/{'b' * 32}/0/0">Wrong file</a>'''
    assert annas_download.slow_download_links(html, BASE, md5) == [BASE + url]


def test_save_validate_cache_and_do_not_reuse_other_edition(selected, monkeypatch, pdf_bytes):
    cfg, spec, cand, _ = selected
    cfg.out_dir.mkdir(parents=True)
    cfg.out_dir.joinpath('Selected book - Writer.pdf').write_bytes(b'other edition')
    calls = []
    async def capture(c, tmp, config):
        calls.append(c.url)
        tmp.write_bytes(pdf_bytes)
        return {'download_host': 'mirror.example'}
    monkeypatch.setattr(annas_download, '_capture_download', capture)
    saved, sha = annas_download.download_selected(cand, spec, cfg.out_dir, cfg)
    assert saved.read_bytes() == pdf_bytes
    assert cand.extra['md5'] in saved.name
    assert sha == hashlib.sha256(pdf_bytes).hexdigest()
    assert cand.extra['download_host'] == 'mirror.example'
    assert annas_download.download_selected(cand, spec, cfg.out_dir, cfg) == (saved, sha)
    assert len(calls) == 1
    assert not list(cfg.out_dir.glob('*.part'))


@pytest.mark.parametrize('body,reason', [(b'<html>blocked</html>', 'not a PDF'),
                                       (b'%PDF-1.4 different edition', 'MD5 mismatch')])
def test_invalid_download_is_not_kept(selected, monkeypatch, body, reason):
    cfg, spec, cand, _ = selected
    async def capture(c, tmp, config):
        tmp.write_bytes(body)
        return {}
    monkeypatch.setattr(annas_download, '_capture_download', capture)
    with pytest.raises(ValueError, match=reason):
        annas_download.download_selected(cand, spec, cfg.out_dir, cfg)
    assert list(cfg.out_dir.iterdir()) == []
    assert not _BROWSER_LOCK.locked()


def test_timeout_cancels_transfer_and_removes_partial(selected, monkeypatch):
    cfg, spec, cand, _ = selected
    cancelled = []
    async def capture(c, tmp, config):
        tmp.write_bytes(b'partial')
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    original = asyncio.wait_for
    async def short_wait(coro, timeout):
        return await original(coro, 0.01)
    monkeypatch.setattr(annas_download, '_capture_download', capture)
    monkeypatch.setattr(annas_download.asyncio, 'wait_for', short_wait)
    with pytest.raises(RuntimeError, match='timed out'):
        annas_download.download_selected(cand, spec, cfg.out_dir, cfg)
    assert cancelled == [True]
    assert list(cfg.out_dir.iterdir()) == []
    assert not _BROWSER_LOCK.locked()


def test_browser_lock_is_shared_with_search(selected):
    cfg, spec, cand, _ = selected
    _BROWSER_LOCK.acquire()
    try:
        with pytest.raises(RuntimeError, match='already running'):
            annas_download.download_selected(cand, spec, cfg.out_dir, cfg)
    finally:
        _BROWSER_LOCK.release()


def test_fetch_prefers_selected_copy_and_records_provenance(selected, monkeypatch, fake_client, mock_adapter, pdf_bytes):
    cfg, spec, cand, _ = selected
    fallback = Candidate(source='mock', url='https://example.test/book.pdf', fmt='pdf', score=90)
    unrequested = Candidate(source='mock', url='https://example.test/book.epub', fmt='epub', score=90)
    client = fake_client({})
    wire_cli(monkeypatch, client, [mock_adapter([fallback, unrequested]), AnnasArchiveAdapter(cfg)])
    async def capture(c, tmp, config):
        tmp.write_bytes(pdf_bytes)
        return {'download_host': 'mirror.example'}
    monkeypatch.setattr(annas_download, '_capture_download', capture)
    results = cli.run(cfg, [spec.source_path])
    assert results[0].status == 'ok'
    assert len(results[0].saved) == 1
    record = json.loads((cfg.out_dir / 'manifest.jsonl').read_text())
    assert record['source'] == 'annas_archive'
    assert record['url'] == cand.url
    assert record['extra']['md5'] == cand.extra['md5']
    assert record['extra']['download_host'] == 'mirror.example'
    assert not any('example.test' in url for url, _ in client.calls)


def test_dry_run_never_opens_download_browser(selected, monkeypatch, fake_client):
    cfg, spec, _, _ = selected
    wire_cli(monkeypatch, fake_client({}), [AnnasArchiveAdapter(cfg)])
    monkeypatch.setattr(annas_download, 'download_selected', lambda *a: pytest.fail('Dry run downloaded'))
    assert cli.run(cfg, [spec.source_path], dry_run=True)[0].detail == 'dry-run'
    assert not list(cfg.out_dir.glob('*.pdf'))


def test_extracts_direct_and_copy_only_links_without_running_javascript():
    url = 'https://mirror.example/book.epub?token=a&x=1'
    literal = json.dumps(url).replace('"', '&quot;')
    html = f'''<button onclick="navigator.clipboard.writeText({literal})">copy</button>
        <input readonly value="{url.replace('&', '&amp;')}">
        <a href="javascript:alert(1)">Download now</a>
        <a href="https://unrelated.example">Other link</a>'''
    assert annas_download.ready_download_urls(html, BASE) == [url]
    assert annas_download.ready_download_urls(
        '<a href="/file.epub" target="_blank">📚 Download now</a>', BASE) == [BASE + '/file.epub']
    assert annas_download.ready_download_urls('<button onclick="evil()">copy</button>', BASE) == []


@pytest.mark.parametrize('kind', ['file', 'html', 'unauthorized', 'server_error', 'wrong_file', 'certificate'])
def test_verified_context_transfer_checks_response_and_preserves_security(selected, pdf_bytes, kind):
    cfg, spec, cand, _ = selected
    cfg.out_dir.mkdir(parents=True)
    tmp = cfg.out_dir / 'file.part'
    calls, disposed = [], []
    class Response:
        status = {'unauthorized': 403, 'server_error': 503}.get(kind, 200)
        ok = status == 200
        headers = {'content-type': 'text/html' if kind == 'html' else 'application/pdf'}
        url = 'https://mirror.example/file.pdf?secret=signed'
        async def body(self):
            return b'%PDF-wrong file' if kind == 'wrong_file' else pdf_bytes
        async def dispose(self):
            disposed.append(True)
    class Request:
        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            if kind == 'certificate':
                raise RuntimeError('CERT_AUTHORITY_INVALID signedurl-secret')
            return Response()
    class Page:
        async def evaluate(self, expr):
            assert expr == 'navigator.userAgent'
            return 'verified-browser-UA'
    async def run():
        return await annas_download.transfer_ready_url(
            SimpleNamespace(request=Request()), Page(), Response.url, BASE + '/slow_download/test', tmp, cand)
    if kind in ('server_error', 'wrong_file', 'certificate'):
        with pytest.raises(annas_download.MirrorDownloadError) as exc:
            asyncio.run(run())
        assert 'signedurl-secret' not in str(exc.value)
        assert not tmp.exists()
    else:
        result = asyncio.run(run())
        if kind == 'file':
            assert result['download_host'] == 'mirror.example'
            assert result['transport'] == 'verified-session-request'
            assert 'secret' not in json.dumps(result)
            assert tmp.read_bytes() == pdf_bytes
        else:
            assert result is None
            assert not tmp.exists()
    assert calls[0][1]['ignore_https_errors'] is False
    assert calls[0][1]['headers']['User-Agent'] == 'verified-browser-UA'
    assert disposed == ([] if kind == 'certificate' else [True])


@pytest.mark.parametrize('failure_delivery', ['request', 'popup'])
def test_browser_tries_next_mirror_on_certificate_error(selected, monkeypatch, pdf_bytes, failure_delivery):
    import playwright.async_api as api
    cfg, spec, cand, _ = selected
    md5 = cand.extra['md5']
    first = BASE + f'/slow_download/{md5}/0/0'
    second = BASE + f'/slow_download/{md5}/0/1'
    visited = []
    closed = []
    options = []

    class Download:
        url = 'https://working-mirror.example/book.pdf?private_token=secret'

        async def save_as(self, path):
            Path(path).write_bytes(pdf_bytes)

    class Page:
        url = ''
        events = {}

        def on(self, event, callback):
            self.events[event] = callback

        def is_closed(self):
            return False

        def locator(self, selector):
            return self

        async def count(self):
            return 0

        async def goto(self, url, **kwargs):
            self.url = url
            visited.append(url)
            if url == first:
                if failure_delivery == 'request':
                    self.events['requestfailed'](SimpleNamespace(
                        is_navigation_request=lambda: True, failure='net::ERR_CERT_AUTHORITY_INVALID'))
                else:
                    Context.pages.append(ErrorPage())

        async def title(self):
            return 'Download page'

        async def content(self):
            return f'<a href="{first}">Slow 1</a><a href="{second}">Slow 2</a>'

        def get_by_role(self, *args, **kwargs):
            return SimpleNamespace(first=self)

        async def is_visible(self):
            return self.url == second

        async def click(self, **kwargs):
            self.events['download'](Download())

    class ErrorPage(Page):
        async def count(self):
            return 1

        async def inner_text(self, **kwargs):
            return 'NET::ERR_CERT_AUTHORITY_INVALID'

        async def close(self):
            Context.pages.remove(self)

    class Context:
        pages = [Page()]

        def on(self, *args):
            pass

        async def close(self):
            closed.append(True)

    class Playwright:
        async def __aenter__(self):
            return SimpleNamespace(chromium=self)

        async def __aexit__(self, *args):
            pass

        async def launch_persistent_context(self, *args, **kwargs):
            options.append(kwargs)
            return Context()

    async def no_sleep(seconds):
        pass
    monkeypatch.setattr(api, 'async_playwright', Playwright)
    monkeypatch.setattr(annas_download.asyncio, 'sleep', no_sleep)
    saved, _ = annas_download.download_selected(cand, spec, cfg.out_dir, cfg)
    assert visited == [cand.url, first, second]
    assert saved.read_bytes() == pdf_bytes
    assert options[0]['headless'] is False
    assert 'ignore_https_errors' not in options[0]
    assert closed == [True]
    assert cand.extra['download_host'] == 'working-mirror.example'
    assert 'private_token' not in json.dumps(cand.extra)
