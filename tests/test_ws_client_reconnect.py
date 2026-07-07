"""Tests for the WS subscription client's token-refresh/backoff logic (fix for the
reconnection storm: expired access token + backoff reset on connect)."""
from __future__ import annotations

import asyncio
import base64
import json
import time

from app.graphql.ws_client import (
    ChatSubscriptionClient,
    _is_auth_error,
    _token_seconds_left,
)


def _make_jwt(seconds_from_now: float) -> str:
    payload = {"exp": time.time() + seconds_from_now}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.sig"


def test_token_seconds_left_reads_exp():
    left = _token_seconds_left(_make_jwt(120))
    assert left is not None and 100 < left <= 121


def test_token_seconds_left_tolerates_garbage():
    assert _token_seconds_left("not-a-jwt") is None
    assert _token_seconds_left("a.b.c") is None


def test_is_auth_error_classification():
    assert _is_auth_error(Exception("Authentication required."))
    assert _is_auth_error(Exception("Signature has expired"))
    assert not _is_auth_error(Exception("connection reset by peer"))
    assert not _is_auth_error(Exception("timeout"))


def test_ensure_fresh_token_refreshes_expired_token():
    tokens = {"current": _make_jwt(-10)}  # already expired
    refreshed = []

    async def refresh() -> bool:
        refreshed.append(True)
        tokens["current"] = _make_jwt(300)
        return True

    client = ChatSubscriptionClient()
    token = asyncio.run(
        client._ensure_fresh_token(lambda: tokens["current"], refresh)
    )
    assert refreshed, "expired token must trigger a refresh"
    assert token == tokens["current"]
    assert _token_seconds_left(token) > 100


def test_ensure_fresh_token_skips_refresh_when_valid():
    valid = _make_jwt(300)
    refreshed = []

    async def refresh() -> bool:
        refreshed.append(True)
        return True

    client = ChatSubscriptionClient()
    token = asyncio.run(client._ensure_fresh_token(lambda: valid, refresh))
    assert token == valid
    assert not refreshed, "a token far from expiry must not be refreshed"


def test_ensure_fresh_token_survives_refresh_failure():
    stale = _make_jwt(-10)

    async def refresh() -> bool:
        raise RuntimeError("network down")

    client = ChatSubscriptionClient()
    token = asyncio.run(client._ensure_fresh_token(lambda: stale, refresh))
    # falls back to the stale token; run() handles the auth error afterwards
    assert token == stale


def test_ensure_fresh_token_without_refresh_callable():
    stale = _make_jwt(-10)
    client = ChatSubscriptionClient()
    token = asyncio.run(client._ensure_fresh_token(lambda: stale, None))
    assert token == stale
