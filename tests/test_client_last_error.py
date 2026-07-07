"""GraphQLClient.execute() must populate last_error on failure (so callers can
distinguish "no data" from "failed") while keeping the data-or-None return
contract unchanged."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.graphql.client import GraphQLClient


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text="", raise_json=False):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text
        self.cookies = httpx.Cookies()
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._json


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.cookies = httpx.Cookies()
        self.is_closed = False

    async def post(self, url, json=None, headers=None):
        return self._resp


def _client_with(monkeypatch, resp):
    c = GraphQLClient()
    fake = _FakeClient(resp)

    async def _get_client():
        return fake

    monkeypatch.setattr(c, "_get_client", _get_client)
    return c


def test_success_returns_data_and_clears_last_error(monkeypatch):
    c = _client_with(monkeypatch, _FakeResp(200, {"data": {"x": 1}}))
    data = asyncio.run(c.execute("query { x }"))
    assert data == {"x": 1}
    assert c.last_error is None


def test_http_error_sets_last_error_and_returns_none(monkeypatch):
    c = _client_with(monkeypatch, _FakeResp(500, text="boom"))
    data = asyncio.run(c.execute("query { x }"))
    assert data is None
    assert c.last_error == "HTTP 500"


def test_graphql_errors_set_last_error(monkeypatch):
    c = _client_with(monkeypatch, _FakeResp(200, {"errors": [{"message": "Boom"}]}))
    data = asyncio.run(c.execute("query { x }", use_auth=False))
    assert data is None
    assert c.last_error == "Boom"


def test_json_decode_error_sets_last_error(monkeypatch):
    c = _client_with(monkeypatch, _FakeResp(200, raise_json=True))
    data = asyncio.run(c.execute("query { x }"))
    assert data is None
    assert c.last_error and "JSON" in c.last_error


def test_last_error_does_not_leak_internal_exception_text(monkeypatch):
    """Failure messages must be generic (detail goes to logs), not raw str(e)."""
    c = _client_with(monkeypatch, _FakeResp(503, text="Traceback: secret internals"))
    asyncio.run(c.execute("query { x }"))
    assert "Traceback" not in (c.last_error or "")
    assert "secret" not in (c.last_error or "")
