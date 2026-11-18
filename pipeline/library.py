"""Local library, bounded EPUB parsing, and persistent reading positions."""
from __future__ import annotations
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import posixpath
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit
import zipfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

_LOCK = threading.Lock()
STATIC = Path(__file__).with_name('static')


def books(root: Path) -> list[dict]:
    root = root.resolve()
    metadata = {}
    manifest = root / 'manifest.jsonl'
    if manifest.exists():
        for line in manifest.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    metadata[row.get('saved_as', '')] = row
            except ValueError:
                continue
    found = []
    if not root.exists():
        return found
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in ('.pdf', '.epub') or not path.is_file() or path.is_symlink():
            continue
        if path.resolve().parent != root:
            continue
        row = metadata.get(path.name, {})
        identity = row.get('sha256') or f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        found.append(dict(id=hashlib.sha256(str(identity).encode()).hexdigest(),
                          title=str(row.get('title') or path.stem),
                          authors=row.get('authors') if isinstance(row.get('authors'), list) else [],
                          format=path.suffix[1:].lower(), name=path.name, size=path.stat().st_size))
    return found


def book(root: Path, identifier: str) -> tuple[dict, Path]:
    for row in books(root):
        if row['id'] == identifier:
            return row, root.resolve() / row['name']
    raise FileNotFoundError('This downloaded book is no longer in the library.')


def positions(root: Path) -> dict:
    try:
        data = json.loads((root / '.reading-positions.json').read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_position(root: Path, identifier: str, value: dict):
    book(root, identifier)
    if not isinstance(value, dict):
        raise ValueError('Invalid reading position.')
    index, scroll = value.get('index'), value.get('scroll', 0)
    if type(index) is not int or not 0 <= index <= 100000 or type(scroll) not in (int, float) or not 0 <= scroll <= 1:
        raise ValueError('Invalid reading position.')
    with _LOCK:
        data = positions(root)
        data[identifier] = {'index': index, 'scroll': scroll}
        tmp = root / '.reading-positions.tmp'
        tmp.write_text(json.dumps(data), encoding='utf-8')
        tmp.replace(root / '.reading-positions.json')


def reveal(root: Path, identifier: str):
    _, path = book(root, identifier)
    if sys.platform == 'darwin':
        args = ['open', '-R', str(path)]
    elif os.name == 'nt':
        args = ['explorer', '/select,', str(path)]
    else:
        args = ['xdg-open', str(path.parent)]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Epub:
    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as z:
            container = ET.fromstring(self.read(z, 'META-INF/container.xml'))
            node = container.find('.//{*}rootfile')
            if node is None:
                raise ValueError('EPUB has no package document.')
            package = node.attrib['full-path']
            opf = ET.fromstring(self.read(z, package))
            self.items = {}
            for item in opf.findall('.//{*}manifest/{*}item'):
                self.items[item.attrib['id']] = {
                    'path': self.relative(package, item.attrib['href']),
                    'type': item.attrib.get('media-type', ''),
                    'properties': item.attrib.get('properties', '').split()}
            self.chapters = [self.items[n.attrib['idref']]['path']
                             for n in opf.findall('.//{*}spine/{*}itemref')
                             if n.attrib.get('idref') in self.items and n.attrib.get('linear') != 'no']
            if not self.chapters:
                raise ValueError('EPUB has no readable chapters.')
            self.cover = next((i['path'] for i in self.items.values() if 'cover-image' in i['properties']), None)
            if not self.cover:
                for meta in opf.findall('.//{*}meta'):
                    if meta.attrib.get('name') == 'cover':
                        self.cover = self.items.get(meta.attrib.get('content'), {}).get('path')

    @staticmethod
    def relative(current: str, href: str) -> str:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or parsed.path.startswith('/'):
            raise ValueError('External EPUB resource rejected.')
        name = posixpath.normpath(posixpath.join(posixpath.dirname(current), unquote(parsed.path)))
        if name == '..' or name.startswith('../') or '\\' in name:
            raise ValueError('Invalid EPUB resource path.')
        return name

    @staticmethod
    def read(z, name):
        info = z.getinfo(name)
        if info.file_size > 16 * 1024 * 1024:
            raise ValueError('EPUB resource is too large to display.')
        return z.read(info)

    def image(self, name):
        if name not in {i['path'] for i in self.items.values()}:
            raise FileNotFoundError('Image not listed in the EPUB.')
        ctype = mimetypes.guess_type(name)[0]
        if ctype not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
            raise ValueError('Unsupported cover or image format.')
        with zipfile.ZipFile(self.path) as z:
            return self.read(z, name), ctype

    def chapter(self, index: int, identifier: str) -> str:
        from urllib.parse import urlencode
        if not 0 <= index < len(self.chapters):
            raise ValueError('Chapter is out of range.')
        current = self.chapters[index]
        with zipfile.ZipFile(self.path) as z:
            soup = BeautifulSoup(self.read(z, current), 'html.parser')
        body = soup.body or soup
        body.attrs = {}
        allowed = set('p div span h1 h2 h3 h4 h5 h6 em strong b i u s blockquote pre code ul ol li br hr img table thead tbody tr th td sup sub a section article figure figcaption dl dt dd'.split())
        for node in list(body.find_all(True)):
            if node.name in ('script', 'style', 'iframe', 'object', 'embed', 'form', 'svg', 'math', 'link', 'meta'):
                node.decompose()
                continue
            if node.name is None:
                continue
            if node.name not in allowed:
                node.unwrap()
                continue
            attrs = {}
            if node.name == 'img':
                try:
                    name = self.relative(current, node.get('src', ''))
                    if name in {i['path'] for i in self.items.values()}:
                        attrs['src'] = '/library/image?' + urlencode({'id': identifier, 'name': name})
                        attrs['alt'] = node.get('alt', '')
                except ValueError:
                    pass
            node.attrs = attrs
        return ('<!doctype html><meta charset="utf-8">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">'
                '<style>body{max-width:44rem;margin:2rem auto;padding:0 1rem;font:20px/1.7 Georgia,serif;color:#24232a;background:#fffaf0;overflow-wrap:anywhere}img{max-width:100%;height:auto}pre{white-space:pre-wrap}table{max-width:100%}</style>' + str(body))


def page(title: str, body: str, script: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><link rel="stylesheet" href="/assets/library.css"></head>'
            '<body><header><a href="/">Search & downloads</a><a href="/library">My library</a></header>'
            f'<main>{body}</main><script type="module" src="/assets/{script}"></script></body></html>')


def library_page():
    return page('My library', '<h1>My library</h1><p>Your downloaded books, ready to read.</p>'
                '<label>Find in library <input id="filter" type="search" placeholder="Title or author"></label>'
                '<p id="message" role="status">Loading books…</p><div id="books" class="grid"></div>', 'library.js')


def reader_page():
    return page('Reader', '<h1 id="title">Reader</h1><div class="controls">'
                '<button id="prev" disabled>Previous</button><label id="location-label">Page / chapter '
                '<input id="location" type="number" min="1" value="1"></label><span id="total"></span>'
                '<button id="next" disabled>Next</button><label>Zoom <select id="zoom">'
                '<option value="1">100%</option><option value="1.25">125%</option><option value="1.5">150%</option></select></label>'
                '<a id="original">Open original file</a></div><p id="message" role="status">Loading…</p>'
                '<div id="viewport"><canvas id="pdf" hidden aria-label="PDF page"></canvas>'
                '<iframe id="epub" title="Book chapter" sandbox="allow-same-origin" hidden></iframe></div>', 'reader.js')
