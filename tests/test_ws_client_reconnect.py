"""Tests for the WS subscription client's token-refresh/backoff logic (fix for the
reconnection storm: expired access token + backoff reset on connect)."""
from __future__ import annotations

import asyncio
import base64
import json
import time

import app.graphql.ws_client as wsc
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


class _AuthErrorSession:
    """A gql session whose subscribe() always fails as if unauthorized."""

    async def subscribe(self, *args, **kwargs):
        raise Exception("forbidden")
        yield  # pragma: no cover - makes this an async generator


class _AuthErrorClient:
    def __init__(self, transport=None):
        pass

    async def __aenter__(self):
        return _AuthErrorSession()

    async def __aexit__(self, *a):
        return False


def test_persistent_authz_error_goes_dormant_even_when_refresh_succeeds(monkeypatch):
    """Storm-fix regression guard: a persistent AUTHORIZATION error (the token is
    valid so refresh keeps succeeding, but the subscription stays forbidden) must
    escalate to the dormant delay instead of looping at ~1s forever. A prior
    version reset auth_failures=0 on every successful refresh, so dormancy never
    fired and the client hammered the backend ~1x/s indefinitely."""
    monkeypatch.setattr(wsc, "Client", _AuthErrorClient)
    monkeypatch.setattr(wsc, "WebsocketsTransport", lambda **k: object())

    client = ChatSubscriptionClient()
    delays: list[float] = []

    async def fake_sleep_or_stop(delay: float) -> None:
        delays.append(delay)
        # Stop as soon as we observe the loop escalate to the dormant interval,
        # so the test terminates deterministically.
        if delay >= wsc._DORMANT_RETRY_S:
            client.stop()

    monkeypatch.setattr(client, "_sleep_or_stop", fake_sleep_or_stop)

    async def refresh() -> bool:
        return True  # refresh always "succeeds" (token valid, just not authorized)

    async def scenario():
        await asyncio.wait_for(
            client.run(
                on_message=lambda d: None,
                get_token=lambda: _make_jwt(300),
                refresh_token=refresh,
            ),
            timeout=5.0,
        )

    asyncio.run(scenario())

    assert any(d >= wsc._DORMANT_RETRY_S for d in delays), f"never went dormant: {delays}"
    # It must have taken roughly _MAX_AUTH_FAILURES fast retries before escalating,
    # not stayed pinned at ~1s forever.
    assert len(delays) <= wsc._MAX_AUTH_FAILURES + 2, delays


def test_sleep_or_stop_wakes_early_on_stop(monkeypatch):
    """_sleep_or_stop must return well before a long dormant delay once stop() is
    set, so logout/teardown isn't blocked for up to 300s."""
    client = ChatSubscriptionClient()
    client.stop()  # already stopped
    # Even with a 300s delay, a stopped client returns immediately.
    asyncio.run(asyncio.wait_for(client._sleep_or_stop(300.0), timeout=1.0))
