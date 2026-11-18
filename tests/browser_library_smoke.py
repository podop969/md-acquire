"""Optional browser integration check: python tests/browser_library_smoke.py. Uses temporary files and installed Chrome."""
import base64, json, sys, tempfile, threading, zipfile
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.webui import make_handler, Job
from playwright.sync_api import sync_playwright

def pdf_bytes():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 600] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>', b'<< /Length 38 >>\nstream\nBT /F1 24 Tf 40 500 Td (Page one) Tj ET\nendstream', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 600] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>', b'<< /Length 38 >>\nstream\nBT /F1 24 Tf 40 500 Td (Page two) Tj ET\nendstream', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data=b'%PDF-1.4\n'; offsets=[0]
    for i, obj in enumerate(objects,1):
        offsets.append(len(data)); data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data); data+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]: data+=f'{offset:010d} 00000 n \n'.encode()
    return data+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()

with tempfile.TemporaryDirectory() as d:
    root=Path(d); (root/'specs').mkdir()
    (root/'config.yaml').write_text(f'specs_dir: {root}/specs\nout_dir: {root}\n')
    (root/'Sample.pdf').write_bytes(pdf_bytes())
    with zipfile.ZipFile(root/'Sample.epub','w') as z:
        z.writestr('META-INF/container.xml','<container><rootfile full-path="book.opf"/></container>')
        z.writestr('book.opf','<package><manifest><item id="a" href="a.xhtml"/><item id="b" href="b.xhtml"/><item id="cover" href="cover.png" properties="cover-image"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
        for name in ('a','b'): z.writestr(name+'.xhtml','<html><body><h1>Chapter '+name+'</h1>'+('<p>Reading text</p>'*100)+'<script>parent.document.title="ATTACK"</script></body></html>')
        z.writestr('cover.png',base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP1sAAAAASUVORK5CYII='))
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(str(root/'config.yaml'),Job()))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(origin+'/library'); page.wait_for_selector('.book'); assert page.locator('.book').count()==2
            page.wait_for_selector('.cover canvas')
            rows=page.request.get(origin+'/library/books').json()['books']
            for row in rows:
                page.goto(origin+'/reader?id='+row['id'])
                page.wait_for_function("!document.querySelector('#location').disabled && document.querySelector('#message').textContent === ''",timeout=30000)
                page.locator('#next').click()
                page.wait_for_function("document.querySelector('#location').value==='2' && document.querySelector('#next').disabled")
                page.wait_for_function("!document.querySelector('#location').disabled && document.querySelector('#message').textContent === ''")
                if row['format']=='epub':
                    page.locator('#epub').evaluate('(f)=>f.contentDocument.scrollingElement.scrollTop=500')
                    page.wait_for_timeout(600)
                else:
                    assert page.locator('#pdf').evaluate('(c)=>c.width') > 0
                page.reload(); page.wait_for_function("!document.querySelector('#location').disabled && document.querySelector('#message').textContent === ''")
                assert page.locator('#location').input_value()=='2'
                if row['format']=='epub': assert page.locator('#epub').evaluate('(f)=>f.contentDocument.scrollingElement.scrollTop')>400
            assert not errors, errors
            assert page.request.post(origin+'/library/reveal',data={'id':rows[0]['id']},headers={'Origin':'http://evil.example'}).status==403
            assert page.request.get(origin+'/library/content?id=../../config.yaml').status==404
            print('PASS: library cards, PDF rendering/page resume, EPUB chapter/scroll resume, isolation and route checks')
            browser.close()
    finally: server.shutdown(); server.server_close()
