import json
from pathlib import Path
import zipfile

import pytest

from pipeline import library


@pytest.fixture
def epub(tmp_path):
    path = tmp_path / 'book.epub'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
        z.writestr('OPS/book.opf', '<package><metadata><meta name="cover" content="cover"/></metadata><manifest><item id="c" href="text/ch1.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="images/cover.png" media-type="image/png"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr('OPS/text/ch1.xhtml', '<html><body><h1>Chapter one</h1><script>alert(1)</script><img src="../images/cover.png" onerror="alert(1)"><a href="https://example.com">Link</a><iframe src="/run"></iframe><p style="background:url(https://example.com)">Text</p></body></html>')
        z.writestr('OPS/images/cover.png', b'cover')
    return path


def test_library_uses_manifest_and_discovers_other_files(tmp_path):
    (tmp_path / 'book.pdf').write_bytes(b'%PDF-')
    (tmp_path / 'other.epub').write_bytes(b'zip')
    (tmp_path / 'unfinished.pdf.part').write_bytes(b'partial')
    (tmp_path / 'manifest.jsonl').write_text('broken\n' + json.dumps({'saved_as':'book.pdf','title':'A title','authors':['Someone'],'sha256':'abc'}) + '\n')
    rows = library.books(tmp_path)
    assert len(rows) == 2
    assert rows[0]['title'] == 'A title'
    assert rows[0]['authors'] == ['Someone']
    assert library.book(tmp_path, rows[0]['id'])[1].name == 'book.pdf'
    with pytest.raises(FileNotFoundError):
        library.book(tmp_path, '../../private')


def test_library_excludes_symlinks(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    file = outside / 'secret.pdf'
    file.write_bytes(b'secret')
    (tmp_path / 'linked.pdf').symlink_to(file)
    assert not library.books(tmp_path)


def test_position_survives_reload_and_rejects_invalid_data(tmp_path):
    (tmp_path / 'book.pdf').write_bytes(b'%PDF-')
    identifier = library.books(tmp_path)[0]['id']
    library.save_position(tmp_path, identifier, {'index': 4, 'scroll': .25})
    assert library.positions(tmp_path)[identifier] == {'index':4,'scroll':.25}
    for value in ({'index':-1}, {'index':True}, {'index':0,'scroll':float('nan')}, None):
        with pytest.raises(ValueError):
            library.save_position(tmp_path, identifier, value)


def test_epub_spine_cover_and_sanitized_chapters(epub):
    book = library.Epub(epub)
    assert book.chapters == ['OPS/text/ch1.xhtml']
    assert book.image(book.cover) == (b'cover', 'image/png')
    chapter = book.chapter(0, 'abc')
    assert 'Chapter one' in chapter
    assert '/library/image?' in chapter
    assert 'onerror' not in chapter and '<script' not in chapter and '<iframe' not in chapter
    assert 'https://example.com' not in chapter
    with pytest.raises(ValueError):
        book.chapter(2, 'abc')
    with pytest.raises(FileNotFoundError):
        book.image('../../private')


def test_root_package_and_epub3_cover(tmp_path):
    path = tmp_path / 'root.epub'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('META-INF/container.xml', '<container><rootfile full-path="book.opf"/></container>')
        z.writestr('book.opf', '<package><manifest><item id="c" href="chapter.xhtml"/><item id="cover" href="cover.jpg" properties="cover-image"/></manifest><spine><itemref idref="c"/></spine></package>')
    book = library.Epub(path)
    assert book.chapters == ['chapter.xhtml']
    assert book.cover == 'cover.jpg'
