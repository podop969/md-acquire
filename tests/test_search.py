from pathlib import Path
from types import SimpleNamespace
import io
import json

import pytest

from pipeline import search
from pipeline.config import Config
from pipeline.spec import parse_file
from pipeline.webui import dashboard_html, make_handler


def test_add_roundtrip_duplicate_and_filename_safety(tmp_path):
    book = {'title': '../../A Book: A Story', 'authors': ['An Author'],
            'formats': ['pdf'], 'doi': '10.1234/example'}
    key, created = search.add_spec(book, tmp_path)
    assert created
    spec = parse_file(tmp_path / f'{key}.md')
    assert spec.title == book['title']
    assert spec.doi == book['doi']
    assert spec.formats == ['pdf']
    assert search.add_spec(book, tmp_path) == (key, False)
    assert len(list(tmp_path.glob('*.md'))) == 1


def test_add_preserves_existing_file_and_handles_slug_collision(tmp_path):
    (tmp_path / 'a-book.md').write_text('User notes, not a valid spec')
    key, created = search.add_spec({'title': 'A book', 'authors': []}, tmp_path)
    assert created and key == 'a-book-2'
    assert (tmp_path / 'a-book.md').read_text() == 'User notes, not a valid spec'


@pytest.mark.parametrize('book', [None, {}, {'title': '../'},
    {'title': 'Test', 'authors': 'invalid'}, {'title': 'Test', 'formats': ['exe']}])
def test_invalid_input(tmp_path, book):
    if book == {'title': '../'}:
        key, _ = search.add_spec(book, tmp_path)
        assert key == 'work'
    else:
        with pytest.raises(ValueError):
            search.add_spec(book, tmp_path)


def test_search_keeps_results_when_one_source_fails(monkeypatch):
    def lookup(source, query, cfg):
        if source == 'arxiv':
            raise TimeoutError()
        return [{'title': query, 'authors': [], 'formats': ['epub']}]
    monkeypatch.setattr(search, '_lookup', lookup)
    cfg = Config.load('/nonexistent-config')
    result = search.search('A book', cfg)
    assert [b['source'] for b in result['results']] == ['openlibrary', 'gutenberg']
    assert 'arxiv' in result['warnings'][0]
    cfg.adapters = ['unpaywall']
    assert search.search('A book', cfg)['results'] == []
    with pytest.raises(ValueError):
        search.search(' ', cfg)


def test_search_parses_each_catalogue(monkeypatch):
    responses = {
        'openlibrary': {'docs': [{'title': 'Book', 'author_name': ['Author'], 'isbn': ['9781234567890']}]},
        'gutendex': {'results': [{'title': 'Book', 'authors': [{'name': 'Author'}],
                                 'formats': {'application/epub+zip': 'https://example.test/book.epub'}}]},
    }
    class Client:
        def __init__(self, *args):
            self.session = SimpleNamespace(close=lambda: None)
        def get(self, url, **kwargs):
            data = next((v for k, v in responses.items() if k in url), {})
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data,
                text='<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom">'
                     '<entry><id>https://arxiv.org/abs/123</id><title>A paper</title>'
                     '<author><name>Author</name></author><x:doi>10.1234/test</x:doi></entry></feed>')
    monkeypatch.setattr(search, 'Client', Client)
    cfg = Config.load('/nonexistent-config')
    assert search._lookup('openlibrary', 'book', cfg)[0]['isbn13'] == '9781234567890'
    assert search._lookup('gutenberg', 'book', cfg)[0]['formats'] == ['epub']
    assert search._lookup('arxiv', 'paper', cfg)[0]['doi'] == '10.1234/test'


def test_add_endpoint_creates_spec_and_rejects_foreign_origin(tmp_path):
    config = tmp_path / 'config.yaml'
    config.write_text(f'specs_dir: {tmp_path / "specs"}\n')
    handler_type = make_handler(str(config))
    handler = object.__new__(handler_type)
    handler.path = '/specs'
    payload = json.dumps({'title': 'New book', 'authors': ['Author']}).encode()
    handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload)),
                       'Host': '127.0.0.1:8619', 'Origin': 'http://127.0.0.1:8619'}
    handler.rfile = io.BytesIO(payload)
    sent = []
    handler._json = lambda data, code=200: sent.append((data, code))
    handler.do_POST()
    assert sent[-1][1] == 201
    assert parse_file(tmp_path / 'specs/new-book.md').title == 'New book'
    handler.headers['Origin'] = 'https://foreign.example'
    handler.do_POST()
    assert sent[-1][1] == 403


def test_search_appears_between_title_and_run_buttons():
    page = dashboard_html([], [], {})
    assert page.index('</h1>') < page.index("id='search-form'") < page.index("class='bar'")


def test_catalogue_endpoint_excludes_browser_and_browser_endpoint_is_separate(tmp_path, monkeypatch):
    import pipeline.webui as webui
    config = tmp_path / 'config.yaml'
    config.write_text('adapters: [openlibrary, gutenberg, arxiv, annas_archive]\nannas_archive_mode: browser\n')
    seen = []
    monkeypatch.setattr(search, '_lookup', lambda source, query, cfg:
                        seen.append(source) or [{'title': query, 'authors': [], 'formats': ['epub']}])
    handler = object.__new__(webui.make_handler(str(config)))
    sent = []
    handler._json = lambda data, code=200: sent.append((data, code))
    handler.path = '/search?q=book'
    handler.do_GET()
    assert set(seen) == {'openlibrary', 'gutenberg', 'arxiv'}
    assert len(sent[-1][0]['results']) == 3

    seen.clear()
    payload = json.dumps({'q': 'book'}).encode()
    handler.path = '/search/annas'
    handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload)),
                       'Host': '127.0.0.1:8619', 'Origin': 'http://127.0.0.1:8619'}
    handler.rfile = io.BytesIO(payload)
    handler.do_POST()
    assert seen == ['annas_archive']
    assert sent[-1][0]['results'][0]['source'] == 'annas_archive'
    seen.clear()
    handler.headers['Origin'] = 'https://foreign.example'
    handler.do_POST()
    assert sent[-1][1] == 403
    assert seen == []


def test_disabled_anna_does_not_launch_and_relative_profile_uses_config_folder(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text('adapters: [openlibrary]\nannas_archive_profile_dir: .browser/anna\n')
    cfg = Config.load(str(config))
    monkeypatch.setattr(search, '_lookup', lambda *args: pytest.fail('Disabled source was called'))
    assert search.search('book', cfg, sources=('annas_archive',)) == {'results': [], 'warnings': []}
    assert cfg.annas_archive_profile_dir == tmp_path / '.browser/anna'
    assert "data-annas-enabled='false'" in dashboard_html([], [], {})
    assert "data-annas-enabled='true'" in dashboard_html([], [], {}, anna_enabled=True)
