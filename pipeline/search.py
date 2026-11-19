"""Catalogue discovery and safe, duplicate-aware creation of wishlist specs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import threading
import xml.etree.ElementTree as ET

import yaml

from .config import Config
from .http import Client
from .spec import parse_file
from .annas_archive import AnnaSearchError, lookup as search_annas_archive, record_md5
from .annas_browser import lookup as search_annas_browser

_WRITE_LOCK = threading.Lock()
SOURCES = ('openlibrary', 'gutenberg', 'arxiv', 'annas_archive')
CATALOGUE_SOURCES = tuple(s for s in SOURCES if s != 'annas_archive')


def _lookup(source: str, query: str, cfg: Config) -> list[dict]:
    if source == 'annas_archive':
        if cfg.annas_archive_mode == 'browser':
            return search_annas_browser(query, cfg)
        if cfg.annas_archive_mode != 'http':
            raise AnnaSearchError('Set annas_archive_mode to browser or http in config.yaml.')
    client = Client(max(cfg.min_interval, 3 if source == 'arxiv' else 1),
                    min(cfg.timeout, 15), 1)
    try:
        if source == 'annas_archive':
            return search_annas_archive(client, query, cfg.annas_archive_url)
        if source == 'openlibrary':
            r = client.get('https://openlibrary.org/search.json', params={
                'q': query, 'limit': 8, 'fields': 'title,author_name,isbn,first_publish_year'})
            r.raise_for_status()
            return [dict(title=b['title'], authors=b.get('author_name') or [],
                         isbn13=next((i for i in b.get('isbn', []) if len(i) == 13), None),
                         year=b.get('first_publish_year'), formats=['epub', 'pdf'])
                    for b in r.json().get('docs', []) if b.get('title')]
        if source == 'gutenberg':
            r = client.get('https://gutendex.com/books/', params={'search': query})
            r.raise_for_status()
            return [dict(title=b['title'], authors=[a['name'] for a in b.get('authors', [])],
                         formats=[fmt for mime, fmt in [('application/epub+zip', 'epub'),
                                  ('application/pdf', 'pdf')] if mime in b.get('formats', {})]
                                  or ['epub'])
                    for b in r.json().get('results', [])[:8] if b.get('title')]
        r = client.get('https://export.arxiv.org/api/query', params={
            'search_query': 'all:"' + query.replace('"', ' ') + '"', 'max_results': 8})
        r.raise_for_status()
        ns = {'a': 'http://www.w3.org/2005/Atom', 'x': 'http://arxiv.org/schemas/atom'}
        root = ET.fromstring(r.text)
        results = []
        for entry in root.findall('a:entry', ns):
            if '/api/errors' in entry.findtext('a:id', '', ns):
                raise ValueError('arXiv could not process this query')
            title = ' '.join(entry.findtext('a:title', '', ns).split())
            if title:
                results.append(dict(title=title, authors=[a.text or '' for a in
                    entry.findall('a:author/a:name', ns)], formats=['pdf'],
                    doi=entry.findtext('x:doi', None, ns),
                    year=entry.findtext('a:published', '', ns)[:4]))
        return results
    finally:
        client.session.close()


def search(query: str, cfg: Config, *, sources: tuple[str, ...] | None = None) -> dict:
    query = query.strip()
    if not 2 <= len(query) <= 300:
        raise ValueError('Enter between 2 and 300 characters.')
    selected = SOURCES if sources is None else sources
    enabled = [s for s in SOURCES if s in selected and s in cfg.adapters]
    results, warnings = [], []
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        pending = [(source, pool.submit(_lookup, source, query, cfg)) for source in enabled]
        for source, future in pending:
            try:
                results.extend(dict(book, source=source) for book in future.result())
            except AnnaSearchError as exc:
                warnings.append(str(exc))
            except Exception:
                warnings.append(f'{source} could not be reached or returned an invalid response. Try again.')
    if not enabled and sources is None:
        warnings.append('Enable openlibrary, gutenberg, arxiv, or annas_archive in config.yaml to search.')
    return {'results': results, 'warnings': warnings}


def _normal(text: str) -> str:
    return re.sub(r'[^\w]+', '', text.casefold())


def add_spec(book: dict, directory: Path) -> tuple[str, bool]:
    if not isinstance(book, dict):
        raise ValueError('Choose a search result to add.')
    title, authors = book.get('title'), book.get('authors', [])
    if not isinstance(title, str) or not title.strip() or len(title) > 1000:
        raise ValueError('A valid title is required.')
    if not isinstance(authors, list) or len(authors) > 200 or any(
            not isinstance(a, str) or len(a) > 500 for a in authors):
        raise ValueError('Invalid authors.')
    formats = book.get('formats', ['epub', 'pdf'])
    if not isinstance(formats, list) or not formats or any(f not in ('pdf', 'epub') for f in formats):
        raise ValueError('Choose PDF or EPUB.')
    data = {'title': title.strip(), 'authors': authors, 'formats': list(dict.fromkeys(formats))}
    selected_md5 = None
    if book.get('source') == 'annas_archive':
        selected_md5 = record_md5(book.get('source_url'))
        fmt = book.get('listed_format')
        if fmt not in ('pdf', 'epub'):
            raise ValueError("Choose a PDF or EPUB result from Anna's Archive.")
        data.update(source='annas_archive', source_url=book['source_url'], source_format=fmt, formats=[fmt])
    for field in ('isbn13', 'doi'):
        value = book.get(field)
        if value:
            if not isinstance(value, str) or len(value) > 500:
                raise ValueError(f'Invalid {field}.')
            data[field] = value
    with _WRITE_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob('*.md'):
            try:
                spec = parse_file(path)
            except Exception:
                continue
            if selected_md5 or spec.source == 'annas_archive':
                if (selected_md5 and spec.source == 'annas_archive'
                        and selected_md5 == record_md5(spec.source_url)):
                    return spec.key, False
                # Different files/editions must not collapse into a title-only spec.
                continue
            same_id = any(data.get(f) and data[f] == getattr(spec, f) for f in ('isbn13', 'doi'))
            same_title = _normal(spec.title) == _normal(title)
            same_author = not authors or not spec.authors or bool(
                {_normal(a) for a in authors} & {_normal(a) for a in spec.authors})
            if same_id or (same_title and same_author):
                return spec.key, False
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:90] or 'work'
        text = '---\n' + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + '---\n'
        number = 1
        while True:
            key = slug if number == 1 else f'{slug}-{number}'
            try:
                with (directory / f'{key}.md').open('x', encoding='utf-8') as fh:
                    fh.write(text)
                return key, True
            except FileExistsError:
                number += 1
