"""
Chrome DevTools Protocol (CDP) WebSocket client with heartbeat, auto-reconnect,
and background message reader for long-running sessions.
"""
import json
import time
import threading
import websocket
import requests

from .config_loader import CDP_PORT, NSFC_HOST
from .notify import push


class CDPClient:
    def __init__(self, port=CDP_PORT):
        self.port = port
        self.ws = None
        self._id = 0
        self._xhr_intercepted = False
        self._saved_tab = None
        self._lock = threading.Lock()
        self._pending = {}         # cmd_id -> response dict
        self._reader_running = False
        self._reader_thread = None

    # ── background reader ────────────────────────────────────────────────────

    def _start_reader(self):
        if self._reader_running:
            return
        self._reader_running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _stop_reader(self):
        self._reader_running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=3)
        self._reader_thread = None

    def _reader_loop(self):
        while self._reader_running:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                with self._lock:
                    for rid, val in list(self._pending.items()):
                        if val is None:
                            self._pending[rid] = {"error": "connection_lost"}
                return
            msg_id = msg.get("id")
            if msg_id is not None:
                with self._lock:
                    self._pending[msg_id] = msg

    # ── connection management ────────────────────────────────────────────────

    def _create_ws(self, ws_url):
        self.ws = websocket.create_connection(
            ws_url, timeout=30,
            origin="http://127.0.0.1",
            suppress_origin=True,
            ping_interval=30,
            ping_timeout=10,
        )
        self.ws.settimeout(30)
        self._start_reader()

    def connect(self, tab=None):
        if tab is None:
            tab = self.find_tab("finalSearchList")
            if tab is None:
                tab = self.find_tab("kd.nsfc.cn")
        if tab is None:
            raise RuntimeError("No suitable tab found")

        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError(f"No WebSocket URL for tab: {tab}")

        print(f"CDP connected: {ws_url[:60]}...")
        self._create_ws(ws_url)
        self._id = 0
        self._saved_tab = tab
        return tab

    def reconnect(self):
        print("  CDP reconnecting...")
        self._stop_reader()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        with self._lock:
            self._pending.clear()
            self._id = 0

        time.sleep(2)

        tab = self.find_tab("finalSearchList")
        if tab is None:
            tab = self.find_tab("kd.nsfc.cn")
        if tab is None:
            raise RuntimeError("No suitable tab for reconnect")
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("No WebSocket URL for reconnect tab")

        self._create_ws(ws_url)
        self._id = 0
        self._saved_tab = tab
        return tab

    # ── command dispatch ─────────────────────────────────────────────────────

    def send(self, method, params=None, timeout=30):
        for attempt in range(2):
            try:
                with self._lock:
                    self._id += 1
                    cmd_id = self._id
                    self._pending[cmd_id] = None

                cmd = {"id": cmd_id, "method": method}
                if params:
                    cmd["params"] = params

                self.ws.send(json.dumps(cmd))

                start = time.time()
                while time.time() - start < timeout:
                    with self._lock:
                        resp = self._pending.get(cmd_id)
                    if resp is not None:
                        with self._lock:
                            self._pending.pop(cmd_id, None)
                        if "result" in resp:
                            return resp["result"]
                        error_info = resp.get("error", "unknown")
                        raise RuntimeError(f"CDP error: {error_info}")
                    time.sleep(0.05)

                with self._lock:
                    self._pending.pop(cmd_id, None)
                raise TimeoutError(f"CDP timeout after {timeout}s: {method}")

            except (websocket.WebSocketException, ConnectionError,
                    ConnectionResetError, OSError) as e:
                if attempt < 1:
                    print(f"  CDP connection lost ({e}), reconnecting...")
                    try:
                        self.reconnect()
                    except Exception:
                        time.sleep(2)
                    continue
                push("CDP 连接失败", f"WebSocket 重连耗尽: {e}")
                raise

            except TimeoutError:
                if attempt < 1:
                    print(f"  CDP timeout, reconnecting...")
                    try:
                        self.reconnect()
                    except Exception:
                        time.sleep(2)
                    continue
                push("CDP 连接超时", f"命令 {method} 超时 {timeout}s，重连耗尽")
                raise

        return None

    # ── high-level helpers ───────────────────────────────────────────────────

    def inject_xhr_interceptor(self):
        if self._xhr_intercepted:
            return
        self.evaluate_js("""
        (() => {
            window._lastApiResponse = null;
            window._apiResponsePromise = null;

            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
                const self = this;
                const origOnReadyStateChange = this.onreadystatechange;
                const origOnLoad = this.onload;

                this.addEventListener('load', function() {
                    try {
                        if (this.responseType === '' || this.responseType === 'text') {
                            window._lastApiResponse = {
                                url: self._apiUrl || '',
                                status: this.status,
                                text: this.responseText,
                            };
                            if (window._apiResponseResolve) {
                                const resolve = window._apiResponseResolve;
                                window._apiResponseResolve = null;
                                resolve(window._lastApiResponse);
                            }
                        }
                    } catch(e) {}
                });

                return origSend.apply(this, arguments);
            };

            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                this._apiUrl = url;
                return origOpen.apply(this, arguments);
            };

            window._xhrInterceptorReady = true;
        })()
        """)
        self._xhr_intercepted = True

    def wait_for_api_response(self, timeout=5):
        self.evaluate_js("window._lastApiResponse = null;")
        start = time.time()
        while time.time() - start < timeout:
            result = self.evaluate_js("window._lastApiResponse")
            val = result.get("result", {}).get("value")
            if val and val != "null":
                return val
            time.sleep(0.2)
        return None

    def evaluate_js(self, expression):
        return self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })

    def navigate(self, url):
        return self.send("Page.navigate", {"url": url})

    def wait_for_load(self, timeout=30):
        self.send("Page.enable")
        start = time.time()
        while time.time() - start < timeout:
            result = self.evaluate_js("document.readyState")
            if result.get("result", {}).get("value") == "complete":
                return True
            time.sleep(0.5)
        return False

    def get_cookies(self, domain=None):
        params = {}
        if domain:
            params["urls"] = [f"https://{domain}"]
        result = self.send("Network.getCookies", params)
        return result.get("cookies", [])

    # ── tab discovery ────────────────────────────────────────────────────────

    def get_browser_info(self):
        resp = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=5)
        return resp.json()

    def get_tabs(self):
        resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
        return resp.json()

    def find_tab(self, keyword=None):
        tabs = self.get_tabs()
        for tab in tabs:
            url = tab.get("url", "")
            if keyword and keyword in url:
                return tab
        for tab in tabs:
            if tab.get("type") == "page" and not tab.get("url", "").startswith("devtools://"):
                return tab
        return None

    def close(self):
        self._stop_reader()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


def call_nsfc_api_via_js(client, api_path, data=None, method="POST"):
    """Call NSFC API through browser JS (cookies carried automatically)."""
    body = ""
    if data:
        body = "&".join(f"{k}={v}" for k, v in data.items())

    js = f"""
    (async () => {{
        try {{
            const resp = await fetch('{NSFC_HOST}{api_path}', {{
                method: '{method}',
                headers: {{
                    'accept': 'application/json, text/plain, */*',
                    'content-type': 'application/x-www-form-urlencoded',
                    'origin': '{NSFC_HOST}',
                    'referer': '{NSFC_HOST}/'
                }},
                body: {json.dumps(body) if body else 'null'}
            }});
            const text = await resp.text();
            return text;
        }} catch (e) {{
            return JSON.stringify({{error: e.message}});
        }}
    }})()
    """
    result = client.evaluate_js(js)
    value = result.get("result", {}).get("value", "")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
