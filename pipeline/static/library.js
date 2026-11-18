const message = document.querySelector('#message');
let books = [], positions = {};
let thumbnailQueue = Promise.resolve(), pdfLibrary;
const thumbnails = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    thumbnails.unobserve(entry.target);
    thumbnailQueue = thumbnailQueue.then(async () => {
      const cover = entry.target;
      if (!cover.isConnected) return;
      let doc;
      try {
        pdfLibrary ||= import('/assets/pdfjs/build/pdf.mjs');
        const pdfjs = await pdfLibrary;
        pdfjs.GlobalWorkerOptions.workerSrc = '/assets/pdfjs/build/pdf.worker.mjs';
        doc = await pdfjs.getDocument({url:'/library/content?id='+cover.dataset.id, isEvalSupported:false,
          cMapUrl:'/assets/pdfjs/cmaps/', cMapPacked:true, standardFontDataUrl:'/assets/pdfjs/standard_fonts/', wasmUrl:'/assets/pdfjs/wasm/'}).promise;
        const page = await doc.getPage(1), natural = page.getViewport({scale:1});
        const view = page.getViewport({scale:240/natural.height});
        const canvas = document.createElement('canvas'); canvas.width=view.width; canvas.height=view.height;
        canvas.setAttribute('aria-label','First page preview');
        await page.render({canvasContext:canvas.getContext('2d'),viewport:view}).promise;
        if (cover.isConnected) cover.replaceChildren(canvas);
      } catch (_) { /* Keep the title card when no preview is available. */ }
      finally { if (doc) await doc.destroy(); }
    }).catch(() => {});
  }
});
function render() {
  thumbnails.disconnect();
  const query = document.querySelector('#filter').value.toLowerCase();
  const visible = books.filter(b => [b.title, ...b.authors].join(' ').toLowerCase().includes(query));
  const grid = document.querySelector('#books'); grid.replaceChildren();
  message.textContent = books.length ? `${visible.length} of ${books.length} files` : 'No downloaded books yet. Search for a title and Fetch it to start your library.';
  for (const book of visible) {
    const card = document.createElement('article'); card.className = 'book';
    const cover = document.createElement('div'); cover.className = 'cover'; cover.textContent = book.title;
    if (book.format === 'epub') {
      const img = new Image(); img.alt = `Cover of ${book.title}`; img.loading = 'lazy';
      img.onload = () => cover.replaceChildren(img);
      img.src = '/library/cover?id=' + book.id;
    }
    const title = document.createElement('h2'); title.textContent = book.title;
    const author = document.createElement('p'); author.textContent = book.authors.join(', ') || 'Author not recorded';
    const details = document.createElement('p'); details.textContent = book.format.toUpperCase() + ' · ' + (book.size / 1048576).toFixed(1) + ' MB';
    const actions = document.createElement('div'); actions.className = 'actions';
    const read = document.createElement('a'); read.href = '/reader?id=' + book.id;
    read.textContent = positions[book.id] ? 'Continue reading' : 'Read';
    const folder = document.createElement('button'); folder.textContent = 'Show in folder';
    folder.onclick = async () => {
      try {
        const r = await fetch('/library/reveal', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:book.id})});
        if (!r.ok) throw new Error((await r.json()).error);
        message.textContent = 'Opened the book’s folder.';
      } catch (e) { message.textContent = e.message; }
    };
    actions.append(read, folder); card.append(cover, title, author, details, actions); grid.append(card);
    if (book.format === 'pdf') { cover.dataset.id = book.id; thumbnails.observe(cover); }
  }
}
document.querySelector('#filter').oninput = render;
try {
  const response = await fetch('/library/books');
  if (!response.ok) throw new Error('Could not load the library. Reload to try again.');
  ({books, positions} = await response.json()); render();
} catch (e) { message.textContent = e.message; }
