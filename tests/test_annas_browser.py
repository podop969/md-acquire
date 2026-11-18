from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import annas_browser, search
from pipeline.annas_archive import AnnaSearchError

HTML = (Path(__file__).parent / 'fixtures/annas_search_current.html').read_text('utf-8')


@pytest.fixture
def browser(monkeypatch, make_config, tmp_path):
    state = SimpleNamespace(clock=0.0, closed=False, launched=[], urls=[], waits=0,
                            html=['<title>DDoS-Guard</title>', HTML], window_closed=False)

    class Page:
        def goto(self, url, **kwargs):
            state.urls.append(url)

        def content(self):
            return state.html.pop(0) if len(state.html) > 1 else state.html[0]

        def is_closed(self):
            return state.window_closed

        def wait_for_timeout(self, ms):
            state.waits += 1
            state.clock += ms / 1000

    class Context:
        pages = [Page()]

        def close(self):
            state.closed = True

    class Playwright:
        def __enter__(self):
            return SimpleNamespace(chromium=self)

        def __exit__(self, *args):
            pass

        def launch_persistent_context(self, profile, **kwargs):
            state.launched.append((profile, kwargs))
            return Context()

    monkeypatch.setattr(annas_browser, '_playwright', Playwright)
    monkeypatch.setattr(annas_browser.time, 'monotonic', lambda: state.clock)
    cfg = make_config(annas_archive_mode='browser', annas_archive_profile_dir=tmp_path / 'profile',
                      annas_archive_browser_timeout=10)
    return state, cfg


def test_waits_for_verification_then_parses_and_closes(browser):
    state, cfg = browser
    result = annas_browser.lookup('Frankenstein & Mary', cfg)
    assert len(result) == 3
    assert result[0]['authors'] == ['Mary Shelley']
    assert state.urls == ['https://annas-archive.gl/search?q=Frankenstein+%26+Mary&check=1']
    assert state.launched[0][0] == str(cfg.annas_archive_profile_dir)
    assert state.launched[0][1]['headless'] is False
    assert state.waits == 1
    assert state.closed
    assert not annas_browser._BROWSER_LOCK.locked()


def test_verification_timeout_is_bounded_and_closes_browser(browser):
    state, cfg = browser
    state.html = ['<title>DDoS-Guard</title>']
    with pytest.raises(AnnaSearchError, match='timed out after 10 seconds'):
        annas_browser.lookup('book', cfg)
    assert state.clock == 10
    assert state.closed
    assert not annas_browser._BROWSER_LOCK.locked()


def test_user_closes_browser(browser):
    state, cfg = browser
    state.window_closed = True
    with pytest.raises(AnnaSearchError, match='window was closed'):
        annas_browser.lookup('book', cfg)
    assert state.closed


def test_parallel_search_does_not_open_same_profile_twice(browser):
    state, cfg = browser
    annas_browser._BROWSER_LOCK.acquire()
    try:
        with pytest.raises(AnnaSearchError, match='already running'):
            annas_browser.lookup('book', cfg)
        assert state.launched == []
    finally:
        annas_browser._BROWSER_LOCK.release()


def test_missing_browser_dependency_releases_lock(browser, monkeypatch):
    _, cfg = browser
    def missing():
        raise AnnaSearchError('Install requirements.txt')
    monkeypatch.setattr(annas_browser, '_playwright', missing)
    with pytest.raises(AnnaSearchError, match='Install requirements'):
        annas_browser.lookup('book', cfg)
    assert not annas_browser._BROWSER_LOCK.locked()


def test_browser_dispatch_never_uses_http_client(browser, monkeypatch):
    _, cfg = browser
    def no_http(*args):
        raise AssertionError('Anna browser mode must not use the HTTP client')
    monkeypatch.setattr(search, 'Client', no_http)
    assert len(search._lookup('annas_archive', 'book', cfg)) == 3
