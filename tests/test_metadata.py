from __future__ import annotations

from pipeline.metadata import enrich
from tests.conftest import FakeResponse


def test_fills_missing_isbn_from_openlibrary(fake_client, make_spec):
    client = fake_client(
        {
            "openlibrary.org": FakeResponse(
                json_data={"docs": [{"isbn": ["0374533555", "9780374533557"]}]}
            )
        }
    )
    spec = make_spec()

    notes = enrich(client, spec)

    assert spec.isbn13 == "9780374533557"
    assert any("isbn13 <-" in n for n in notes)


def test_no_query_when_isbn_present(fake_client, make_spec):
    client = fake_client({})
    spec = make_spec(isbn13="9780374533557")

    enrich(client, spec)

    assert client.calls == []                        # enrichment skipped entirely


def test_upstream_failure_is_swallowed(fake_client, make_spec):
    client = fake_client(
        {
            "openlibrary.org": FakeResponse(503),
        }
    )
    spec = make_spec()

    notes = enrich(client, spec)          # must not raise

    assert spec.isbn13 is None
    assert notes == []


def test_no_match_returns_no_notes(fake_client, make_spec):
    client = fake_client(
        {"openlibrary.org": FakeResponse(json_data={"docs": []})}
    )
    spec = make_spec()

    assert enrich(client, spec) == []


def test_non_13digit_isbns_are_skipped(fake_client, make_spec):
    client = fake_client(
        {"openlibrary.org": FakeResponse(json_data={"docs": [{"isbn": ["0374533555"]}]})}
    )
    spec = make_spec()

    assert enrich(client, spec) == []                # only ISBN-13 accepted