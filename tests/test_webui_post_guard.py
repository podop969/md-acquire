"""Every POST route (and any future one) must pass the Host + token guard BEFORE routing."""
import http.client
import inspect
import json

import pytest

import pipeline.webui as webui
from tests.test_webui_csrf import TOKEN, _req, server  # noqa: F401  (fixture re-use)

# "/no-such-route" is the point: a guard that runs before routing answers 403
# for it too, so routes added later are covered without editing this list.
POST_ROUTES = ["/run?mode=dry", "/test", "/specs", "/search/annas",
               "/library/position", "/library/reveal", "/no-such-route"]


@pytest.mark.parametrize("path", POST_ROUTES)
@pytest.mark.parametrize("case", ["no-token", "wrong-token", "rebinding-host"])
def test_every_post_route_is_guarded(server, path, case):  # noqa: F811
    port, job = server
    host = f"evil.example:{port}" if case == "rebinding-host" else f"127.0.0.1:{port}"
    # Origin matches Host and Content-Type is JSON, as a rebinding page's fetch() would send.
    hdrs = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json"}
    if case != "no-token":
        hdrs["X-UI-Token"] = TOKEN if case == "rebinding-host" else "wrong"
    status, _ = _req(port, "POST", path, hdrs)
    assert status == 403, f"{case}: POST {path} -> {status}"
    assert job.started == []


def test_handler_defines_do_post_once():
    # Two `def do_POST` in one class is legal Python: the later one silently wins.
    assert inspect.getsource(webui).count("def do_POST(") == 1


@pytest.mark.parametrize("path", ["/library", "/reader"])
def test_library_pages_carry_the_token(server, path):  # noqa: F811
    port, _ = server
    status, page = _req(port, "GET", path)
    assert status == 200
    assert f'<meta name="ui-token" content="{TOKEN}">' in page


def _post_json(port, path, payload):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    origin = f"127.0.0.1:{port}"
    c.request("POST", path, body=json.dumps(payload),
              headers={"Host": origin, "Origin": f"http://{origin}",
                       "Content-Type": "application/json", "X-UI-Token": TOKEN})
    r = c.getresponse()
    body = json.loads(r.read() or b"{}")
    c.close()
    return r.status, body


def test_token_lets_the_pages_post(server, tmp_path):  # noqa: F811
    port, _ = server
    status, body = _post_json(port, "/specs", {"title": "Pride and Prejudice",
                                               "authors": ["Jane Austen"]})
    assert status == 201 and body["created"]
    assert (tmp_path / "specs" / f"{body['key']}.md").exists()
    # Past the guard, the route itself answers: no such book is a 404, not a 403.
    status, _ = _post_json(port, "/library/position",
                           {"id": "0" * 64, "position": {"index": 0, "scroll": 0}})
    assert status == 404
