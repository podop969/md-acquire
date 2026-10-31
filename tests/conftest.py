from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable

import pytest
import requests

from pipeline.adapters.base import Adapter
from pipeline.config import Config
from pipeline.models import Candidate, WorkSpec


# ---------- fake HTTP layer ----------


class FakeResponse:
    def __init__(self, status_code=200, *, json_data=None, text="", content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.content = content
        self.headers = headers or {"content-type": "application/octet-stream"}

    def json(self):
        if self._json is None:
            raise ValueError("no JSON payload")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i: i + chunk_size]


class FakeClient:
    """Drop-in for pipeline.http.Client with no throttling and recorded calls."""

    def __init__(self, handler: Callable[[str, dict], FakeResponse]):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


def route(mapping: dict, default_status: int = 404):
    """Build a handler from {url_substring: FakeResponse | callable}."""

    def handler(url, kwargs):
        for needle, resp in mapping.items():
            if needle in url:
                return resp(url, kwargs) if callable(resp) else resp
        return FakeResponse(default_status)

    return handler


@pytest.fixture
def fake_client():
    """fake_client({...}) -> FakeClient. Keys are URL substrings."""
    def _make(mapping, default_status=404):
        return FakeClient(route(mapping, default_status))

    return _make


@pytest.fixture
def make_config(tmp_path):
    def _make(**overrides):
        cfg = Config(
            specs_dir=tmp_path / "specs",
            out_dir=tmp_path / "library",
            contact_email="test@example.org",
            min_interval=0.0,
            timeout=5,
            retries=1,
            adapters=["arxiv", "openlibrary", "gutenberg", "unpaywall"],
        )
        for k, v in overrides.items():
            setattr(cfg, k, v)
        cfg.specs_dir.mkdir(parents=True, exist_ok=True)
        return cfg

    return _make


@pytest.fixture
def make_spec():
    def _make(**overrides):
        base = dict(key="demo", title="Thinking, Fast and Slow", authors=["Daniel Kahneman"])
        base.update(overrides)
        return WorkSpec(**base)

    return _make


class MockAdapter(Adapter):
    """Adapter stub: returns preset candidates, or raises preset exception."""

    name = "mock"

    def __init__(self, candidates=None, raises=None, name="mock"):
        self.candidates = list(candidates or [])
        self.raises = raises
        self.name = name

    def lookup(self, client, spec):
        if self.raises:
            raise self.raises
        return list(self.candidates)


@pytest.fixture
def mock_adapter():
    return MockAdapter


# ---------- shared CLI wiring for orchestration tests ----------


def wire_cli(monkeypatch, client, adapters):
    """Point pipeline.cli at an offline client and adapter list."""
    monkeypatch.setattr("pipeline.cli.Client", lambda *a, **k: client)
    monkeypatch.setattr("pipeline.cli.build_adapters", lambda names, cfg: adapters)


# ---------- sample payloads ----------


@pytest.fixture
def pdf_bytes():
    return b"%PDF-1.4\n%test pdf body\n%%EOF\n"


@pytest.fixture
def make_epub(tmp_path):
    def _make(name="book.epub", mimetype=b"application/epub+zip"):
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", mimetype)
            zf.writestr("META-INF/container.xml", "<container/>")
        return path

    return _make


@pytest.fixture
def spec_markdown():
    return """---
title: "Thinking, Fast and Slow"
authors: ["Daniel Kahneman"]
isbn13: "978-0-374-53355-7"
formats: ["epub", "pdf"]
---
Why I need this edition.
"""