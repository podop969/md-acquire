"""CSRF / DNS-rebinding guard on the local trigger UI.

A real server on a free loopback port; the job is a recorder, so nothing runs.
"""
from __future__ import annotations

import http.client
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest

from pipeline.webui import make_handler

TOKEN = "test-token-123"


class RecordingJob:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start(self, kind, work) -> bool:
        self.started.append(kind)
        return True

    def status(self) -> dict:
        return {"running": False, "kind": "", "exit_code": None, "log": ""}


@pytest.fixture()
def server(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"specs_dir: {tmp_path / 'specs'}\nout_dir: {tmp_path / 'out'}\n",
                   encoding="utf-8")
    job = RecordingJob()
    srv = ThreadingHTTPServer(("127.0.0.1", port),
                              make_handler(str(cfg), job, port=port, token=TOKEN))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port, job
    srv.shutdown()
    srv.server_close()


def _req(port, method, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": f"127.0.0.1:{port}"}
    h.update(headers or {})
    c.request(method, path, headers=h)
    r = c.getresponse()
    body = r.read().decode("utf-8", "replace")
    c.close()
    return r.status, body


@pytest.mark.parametrize("path", ["/run?mode=force", "/test"])
def test_get_cannot_start_a_job(server, path):
    port, job = server
    status, _ = _req(port, "GET", path)
    assert status == 405
    assert job.started == []


@pytest.mark.parametrize("hdrs", [{}, {"X-UI-Token": "wrong"}])
def test_post_without_valid_token_is_refused(server, hdrs):
    port, job = server
    status, _ = _req(port, "POST", "/run?mode=run", hdrs)
    assert status == 403
    assert job.started == []


def test_rebinding_host_is_refused(server):
    port, job = server
    status, _ = _req(port, "POST", "/test",
                     {"Host": f"evil.example:{port}", "X-UI-Token": TOKEN})
    assert status == 403
    assert job.started == []
    status, _ = _req(port, "GET", "/status", {"Host": "evil.example"})
    assert status == 403


def test_page_token_lets_the_ui_start_jobs(server):
    port, job = server
    status, page = _req(port, "GET", "/")
    assert status == 200
    assert f"name='ui-token' content='{TOKEN}'" in page
    assert _req(port, "POST", "/run?mode=dry", {"X-UI-Token": TOKEN})[0] == 200
    assert _req(port, "POST", "/test", {"X-UI-Token": TOKEN})[0] == 200
    assert job.started == ["bulk run", "test suite"]
