const id = new URLSearchParams(location.search).get('id');
const $ = s => document.querySelector(s);
const message = $('#message'), viewport = $('#viewport'), frame = $('#epub'), canvas = $('#pdf');
let doc, info, index = 0, count = 0, busy = true, ready = false, saveTimer, savedScroll = 0;
function scrollRatio() {
  const el = info.format === 'epub' ? frame.contentDocument?.scrollingElement : viewport;
  return el ? el.scrollTop / Math.max(1, el.scrollHeight - el.clientHeight) : 0;
}
function persist() {
  if (!ready) return;
  const value = {index, scroll: Math.max(0, Math.min(1, scrollRatio()))};
  fetch('/library/position', {method:'POST', keepalive:true, headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, position:value})})
    .then(r => {if (!r.ok) throw new Error('Could not save reading position.');})
    .catch(e => {message.textContent = e.message;});
}
function onscroll() { clearTimeout(saveTimer); saveTimer = setTimeout(persist, 350); }
function controls() {
  $('#prev').disabled = busy || index <= 0; $('#next').disabled = busy || index >= count - 1;
  $('#location').disabled = busy; $('#zoom').disabled = busy || info?.format === 'epub';
  $('#location').value = index + 1; $('#location').max = count;
  $('#total').textContent = 'of ' + count;
}
async function show(target, scroll = 0) {
  if (busy && ready) return;
  busy = true; ready = false; clearTimeout(saveTimer); index = target; controls();
  message.textContent = 'Loading…';
  try {
    if (info.format === 'pdf') {
      const page = await doc.getPage(index + 1);
      const scale = Number($('#zoom').value);
      const natural = page.getViewport({scale:1});
      const view = page.getViewport({scale:Math.min(1.6, (viewport.clientWidth - 24) / natural.width) * scale});
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(view.width * ratio); canvas.height = Math.floor(view.height * ratio);
      canvas.style.width = view.width + 'px'; canvas.style.height = view.height + 'px';
      await page.render({canvasContext:canvas.getContext('2d'),viewport:view,transform:[ratio,0,0,ratio,0,0]}).promise;
      viewport.scrollTop = scroll * Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    } else {
      const response = await fetch('/library/chapter?id=' + id + '&index=' + index);
      if (!response.ok) throw new Error((await response.json()).error || 'Chapter unavailable');
      const chapter = await response.text();
      await new Promise((resolve, reject) => {
        frame.onload = async () => {
          try {
            const el = frame.contentDocument.scrollingElement;
            await Promise.all([...frame.contentDocument.images].map(img => img.complete ? Promise.resolve() : new Promise(r => {img.onload=r;img.onerror=r;})));
            el.scrollTop = scroll * Math.max(0, el.scrollHeight - el.clientHeight);
            frame.contentWindow.addEventListener('scroll', onscroll); resolve();
          } catch(e) { reject(e); }
        };
        frame.srcdoc = chapter;
      });
    }
    ready = true; message.textContent = ''; persist();
  } catch(e) { message.textContent = 'Could not display this book: ' + e.message + '. You can open the original file above.'; }
  finally { busy = false; controls(); }
}
$('#prev').onclick = () => show(index - 1);
$('#next').onclick = () => show(index + 1);
$('#location').onchange = () => {const n=Number($('#location').value); if(Number.isInteger(n)&&n>=1&&n<=count) show(n-1); else controls();};
$('#zoom').onchange = () => show(index, scrollRatio());
viewport.addEventListener('scroll', onscroll);
window.addEventListener('pagehide', persist);
try {
  const r = await fetch('/library/book?id=' + encodeURIComponent(id || ''));
  if(!r.ok) throw new Error((await r.json()).error);
  info = await r.json(); $('#title').textContent = info.title;
  $('#original').href = '/library/content?id=' + id; $('#original').target='_blank'; $('#original').rel='noopener';
  index = info.position?.index || 0; savedScroll = info.position?.scroll || 0;
  if(info.format === 'pdf') {
    const pdfjs = await import('/assets/pdfjs/build/pdf.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/assets/pdfjs/build/pdf.worker.mjs';
    doc = await pdfjs.getDocument({url:'/library/content?id='+id, isEvalSupported:false,
      cMapUrl:'/assets/pdfjs/cmaps/', cMapPacked:true, standardFontDataUrl:'/assets/pdfjs/standard_fonts/', wasmUrl:'/assets/pdfjs/wasm/'}).promise;
    count = doc.numPages; canvas.hidden=false;
  } else { count=info.chapters; frame.hidden=false; }
  index = Math.min(index, count-1); busy=false; await show(index,savedScroll);
} catch(e) { message.textContent = 'Could not open the book: ' + e.message; }
