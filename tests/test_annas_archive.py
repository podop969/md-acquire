from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from pipeline import search
from pipeline.adapters import build
from pipeline.annas_archive import AnnaSearchError, lookup, parse_results
from pipeline.config import Config
from pipeline.spec import parse_file
from tests.conftest import FakeResponse

BASE = 'https://annas-archive.gl'
HTML = (Path(__file__).parent / 'fixtures/annas_search.html').read_text('utf-8')
CURRENT_HTML = (Path(__file__).parent / 'fixtures/annas_search_current.html').read_text('utf-8')


def test_current_live_page_layout(tmp_path):
    books = parse_results(CURRENT_HTML, BASE)
    assert len(books) == 3
    assert books[0]['title'] == 'Frankenstein: Or the Modern Prometheus - the 1818 Text'
    assert books[0]['authors'] == ['Mary Shelley']
    assert books[0]['year'] == 2012
    assert [book['listed_format'] for book in books] == ['fb2', 'azw3', 'epub']
    assert books[2]['authors'] == ['Mary Shelley [Shelley, Mary]']
    assert books[2]['formats'] == ['epub']
    key, created = search.add_spec(books[2], tmp_path)
    assert created
    assert parse_file(tmp_path / (key + '.md')).formats == ['epub']


def test_saved_page_metadata_and_add_to_specs(tmp_path):
    books = parse_results(HTML, BASE)
    assert len(books) == 4
    assert books[0]['authors'] == ['Edwards S. Herman & Noam Chomsky']
    book = books[1]
    assert book['title'] == 'Manufacturing Consent : The Political Economy of the Mass Media'
    assert book['authors'] == ['Edward S. Herman', 'Noam Chomsky']
    assert book['year'] == 2011
    assert book['formats'] == ['epub']
    assert book['listed_format'] == 'epub'
    assert book['source_url'] == BASE + '/md5/2d8a87d1508b14f377914bc8bd0779b0'
    assert books[2]['listed_format'] == 'mobi'
    assert books[2]['formats'] == ['epub', 'pdf']  # requested alternatives, not claimed files
    key, created = search.add_spec(book, tmp_path)
    assert created
    spec = parse_file(tmp_path / (key + '.md'))
    assert spec.title == book['title']
    assert spec.authors == book['authors']
    assert spec.formats == ['epub']
    assert search.add_spec(book, tmp_path) == (key, False)


def test_commented_results_and_duplicates():
    cards = HTML.split('-->', 1)[1]  # omit the fixture's descriptive comment
    assert parse_results('<!--' + cards + '-->', BASE) == parse_results(HTML, BASE)
    assert len(parse_results(HTML + HTML, BASE)) == 4


def test_result_limit_missing_fields_and_invalid_links():
    cards = ''.join(f'<a class="js-vim-focus" href="/md5/{i:032x}"><h3>Book {i}</h3></a>'
                    for i in range(12))
    invalid = '<a class="js-vim-focus" href="javascript:alert(1)"><h3>Bad</h3></a>'
    books = parse_results(invalid + cards, BASE)
    assert len(books) == 8
    assert books[0]['title'] == 'Book 0'
    assert books[0]['authors'] == []
    assert books[0]['listed_format'] is None
    assert books[0]['year'] is None


@pytest.mark.parametrize('html,message', [
    ('<title>Just a moment...</title><form id="challenge-form"></form>', 'verification'),
    ('<title>DDoS-Guard</title><p>Checking your browser</p>', 'verification'),
    ('<html><h1>Unexpected site layout</h1></html>', 'unrecognized'),
])
def test_blocked_or_changed_page_is_not_no_matches(html, message):
    with pytest.raises(AnnaSearchError, match=message):
        parse_results(html, BASE)


def test_explicit_empty_search():
    assert parse_results('<form><input name="q"></form><p>No files found.</p>', BASE) == []


def test_query_and_check_parameters_are_encoded(fake_client):
    client = fake_client({'/search': FakeResponse(text=HTML)})
    query = 'Harry Potter & café #1?'
    assert len(lookup(client, query, BASE + '/')) == 4
    url, kwargs = client.calls[0]
    assert url == BASE + '/search'
    prepared = requests.Request('GET', url, params=kwargs['params']).prepare()
    assert parse_qs(urlsplit(prepared.url).query) == {'q': [query], 'check': ['1']}


@pytest.mark.parametrize('status', [403, 429, 503])
def test_http_errors_are_actionable(fake_client, status):
    client = fake_client({'/search': FakeResponse(status)})
    with pytest.raises(AnnaSearchError, match='blocked|could not be reached'):
        lookup(client, 'book', BASE)


def test_network_failure_preserves_other_sources(monkeypatch, make_config):
    closed = []
    class Client:
        def __init__(self, *args):
            self.session = SimpleNamespace(close=lambda: closed.append(True))

        def get(self, url, **kwargs):
            if url.startswith(BASE):
                raise requests.ConnectionError('DNS failure')
            return FakeResponse(json_data={'docs': [{'title': 'Book'}]})

    monkeypatch.setattr(search, 'Client', Client)
    cfg = make_config(adapters=['openlibrary', 'annas_archive'])
    result = search.search('book', cfg)
    assert len(result['results']) == 1
    assert result['results'][0]['source'] == 'openlibrary'
    assert 'could not be reached' in result['warnings'][0]
    assert len(closed) == 2


def test_search_integration_and_download_adapter_separation(monkeypatch, make_config):
    class Client:
        def __init__(self, *args):
            self.session = SimpleNamespace(close=lambda: None)

        def get(self, url, **kwargs):
            return FakeResponse(text=HTML)

    monkeypatch.setattr(search, 'Client', Client)
    cfg = make_config(adapters=['annas_archive'])
    result = search.search('manufacturing consent', cfg)
    assert len(result['results']) == 4
    assert all(b['source'] == 'annas_archive' for b in result['results'])
    assert result['warnings'] == []
    from pipeline.models import WorkSpec
    adapters = build(cfg.adapters, cfg)
    assert len(adapters) == 1
    assert adapters[0].lookup(None, WorkSpec(key='old', title='Book')) == []
    cfg.adapters = []
    assert search.search('book', cfg)['results'] == []


def test_configurable_url(tmp_path, fake_client):
    path = tmp_path / 'config.yaml'
    path.write_text('annas_archive_url: https://catalogue.example\nadapters: [annas_archive]\n')
    cfg = Config.load(str(path))
    client = fake_client({'/search': FakeResponse(text=HTML)})
    books = lookup(client, 'book', cfg.annas_archive_url)
    assert client.calls[0][0] == 'https://catalogue.example/search'
    assert books[0]['source_url'].startswith('https://catalogue.example/md5/')
    with pytest.raises(AnnaSearchError, match='valid HTTP'):
        lookup(client, 'book', 'javascript:alert(1)')
