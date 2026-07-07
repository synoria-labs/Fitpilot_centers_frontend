"""GraphQL subscription client over WebSocket for realtime chat updates.

Runs on the application's single AsyncioExecutor event loop. The long-lived
``run`` coroutine is submitted to the executor by the controller, and incoming
messages are delivered via a callback (which the controller bridges to a Qt signal).

Auth: the desktop cannot read the HttpOnly cookie, so the access token is sent in the
graphql-transport-ws ``connection_init`` payload as ``authToken`` (the backend reads it
from connection_params). Uses gql's WebsocketsTransport (graphql-ws subprotocol), which
the backend enables alongside graphql-transport-ws.

Reconnection policy: the access token is short-lived (~5 min), so before every
(re)connect the token is refreshed if missing or about to expire (via the injected
``refresh_token`` coroutine). Auth errors from the subscription resolver
("Authentication required." / "Signature has expired") trigger a refresh instead of a
blind retry, and the backoff only resets after the connection proves healthy (first
event received or a minimum uptime) — never merely on connect, because a doomed
connection "connects" fine and only fails at the resolver.
"""
import asyncio
import base64
import json
import logging
import random
import time
from typing import Awaitable, Callable, Optional

from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport

from ..core.config import Config

logger = logging.getLogger(__name__)

# Refresh the token if it expires within this many seconds.
_TOKEN_EXPIRY_MARGIN_S = 30
# A connection that survives this long is considered healthy (resets backoff).
_HEALTHY_UPTIME_S = 60
# Max delay between reconnect attempts (transient errors).
_MAX_BACKOFF_S = 60
# After this many consecutive auth failures with no successful refresh, the loop
# goes dormant and only retries a refresh every _DORMANT_RETRY_S (e.g. session
# revoked server-side; hammering the backend is pointless until re-login).
_MAX_AUTH_FAILURES = 5
_DORMANT_RETRY_S = 300

_MESSAGE_FIELDS = """
    id
    conversationId
    contactId
    direction
    messageType
    textContent
    timestamp
    waMessageId
    contextMessageId
    mediaUrl
    media {
        id
        mediaType
        mimeType
        filename
        caption
        fileSize
        mediaUrl
        downloaded
        downloadFailed
    }
"""

MESSAGE_ADDED_SUBSCRIPTION = gql(
    """
    subscription MessageAdded($conversationId: Int) {
        messageAdded(conversationId: $conversationId) { %s }
    }
    """
    % _MESSAGE_FIELDS
)

MESSAGE_UPDATED_SUBSCRIPTION = gql(
    """
    subscription MessageUpdated($conversationId: Int) {
        messageUpdated(conversationId: $conversationId) { %s }
    }
    """
    % _MESSAGE_FIELDS
)


def _token_seconds_left(token: str) -> Optional[float]:
    """Seconds until the JWT expires (no signature check), or None if unreadable."""
    try:
        payload_part = token.split(".")[1]
        padding = -len(payload_part) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_part + "=" * padding))
        exp = payload.get("exp")
        if exp is None:
            return None
        return float(exp) - time.time()
    except Exception:  # noqa: BLE001 - malformed token; treat as unknown
        return None


def _is_auth_error(exc: BaseException) -> bool:
    """Whether the subscription died because of authentication (vs a transient error)."""
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "authentication required",
            "signature has expired",
            "unauthorized",
            "forbidden",
            "4401",
            "4403",
        )
    )


class ChatSubscriptionClient:
    """Maintains WebSocket subscriptions to ``messageAdded``/``messageUpdated``
    with auto-reconnect and access-token refresh."""

    def __init__(self) -> None:
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def _ensure_fresh_token(
        self,
        get_token: Callable[[], Optional[str]],
        refresh_token: Optional[Callable[[], Awaitable[bool]]],
    ) -> Optional[str]:
        """Return an access token, refreshing first if it's missing or near expiry."""
        token = get_token() if callable(get_token) else None
        if refresh_token is None:
            return token
        seconds_left = _token_seconds_left(token) if token else None
        if token and seconds_left is not None and seconds_left > _TOKEN_EXPIRY_MARGIN_S:
            return token
        try:
            if await refresh_token():
                fresh = get_token() if callable(get_token) else None
                if fresh:
                    logger.info("Chat subscription: access token refreshed before connect")
                    return fresh
        except Exception as e:  # noqa: BLE001 - refresh failure is handled by backoff
            logger.warning("Chat subscription: token refresh failed: %s", e)
        return token

    async def run(
        self,
        on_message: Callable[[dict], None],
        get_token: Callable[[], Optional[str]],
        conversation_id: Optional[int] = None,
        on_message_updated: Optional[Callable[[dict], None]] = None,
        refresh_token: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> None:
        """Subscribe and forward each event to its callback until stopped.

        ``refresh_token`` is an async callable (e.g. ``AuthService.refresh_token``)
        returning True when a new access token landed in the shared cookie jar.
        """
        # NOTE: do NOT reset self._stop here. __init__ already sets it False and
        # every start creates a fresh client; resetting on the executor thread
        # could clobber a stop() that raced in from the GUI thread, orphaning an
        # unstoppable subscription.
        backoff = 1
        auth_failures = 0
        healthy = False  # set when the current connection proves itself

        def _mark_healthy() -> None:
            nonlocal backoff, auth_failures, healthy
            backoff = 1
            auth_failures = 0
            healthy = True

        while not self._stop:
            token = await self._ensure_fresh_token(get_token, refresh_token)
            if self._stop:
                break
            init_payload = {"authToken": token} if token else {}
            transport = WebsocketsTransport(
                url=Config.GRAPHQL_WS_URL,
                init_payload=init_payload,
            )
            healthy = False
            connected_at = time.monotonic()
            try:
                client = Client(transport=transport)
                async with client as session:
                    logger.info("Chat subscription connected")
                    connected_at = time.monotonic()
                    consumers = [
                        self._consume(
                            session,
                            MESSAGE_ADDED_SUBSCRIPTION,
                            "messageAdded",
                            on_message,
                            conversation_id,
                            _mark_healthy,
                        )
                    ]
                    if on_message_updated is not None:
                        consumers.append(
                            self._consume(
                                session,
                                MESSAGE_UPDATED_SUBSCRIPTION,
                                "messageUpdated",
                                on_message_updated,
                                conversation_id,
                                _mark_healthy,
                            )
                        )
                    # Both subscriptions share the connection; if one dies the
                    # gather raises and the outer loop reconnects both.
                    await asyncio.gather(*consumers)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                uptime = time.monotonic() - connected_at
                # A quiet but long-lived connection is healthy even without events.
                if healthy or uptime >= _HEALTHY_UPTIME_S:
                    backoff = 1
                    auth_failures = 0
                if _is_auth_error(e):
                    auth_failures += 1
                    refreshed = False
                    if refresh_token is not None and not self._stop:
                        try:
                            refreshed = bool(await refresh_token())
                        except Exception as refresh_err:  # noqa: BLE001
                            logger.warning(
                                "Chat subscription: token refresh after auth error failed: %s",
                                refresh_err,
                            )
                    if auth_failures >= _MAX_AUTH_FAILURES:
                        # Persistent auth failure a refresh cannot resolve. Covers
                        # BOTH a revoked session (refresh fails) AND a valid token
                        # that is simply NOT AUTHORIZED for this subscription
                        # (refresh keeps "succeeding" but the reconnect fails the
                        # same way). auth_failures is reset ONLY by a HEALTHY
                        # connection (first event / >=60s uptime), never by a mere
                        # refresh success — otherwise an authorization error would
                        # loop forever at ~1/s and never go dormant.
                        delay = _DORMANT_RETRY_S
                        logger.error(
                            "Chat subscription: %d consecutive auth failures a refresh does not "
                            "resolve (session revoked or subscription not authorized); "
                            "retrying in %ss",
                            auth_failures,
                            delay,
                        )
                    elif refreshed:
                        delay = 1
                        logger.info(
                            "Chat subscription auth error: %s; token refreshed, reconnecting", e
                        )
                    else:
                        delay = min(backoff, _MAX_BACKOFF_S)
                        backoff = min(backoff * 2, _MAX_BACKOFF_S)
                        logger.warning(
                            "Chat subscription auth error: %s; refresh unavailable/failed, "
                            "reconnecting in ~%ss",
                            e,
                            delay,
                        )
                else:
                    delay = min(backoff, _MAX_BACKOFF_S)
                    backoff = min(backoff * 2, _MAX_BACKOFF_S)
                    logger.warning(
                        "Chat subscription error: %s; reconnecting in ~%ss", e, delay
                    )
                if self._stop:
                    break
                # Jitter avoids synchronized reconnect stampedes across clients.
                await self._sleep_or_stop(delay + random.uniform(0, delay * 0.25))
                continue
            # Clean exit from the session (e.g. stop() during consume).
            if self._stop:
                break
            await self._sleep_or_stop(backoff + random.uniform(0, backoff * 0.25))
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
        logger.info("Chat subscription stopped")

    async def _sleep_or_stop(self, delay: float) -> None:
        """Sleep up to ``delay`` seconds, waking within ~1s if stop() is called.

        The reconnect/dormant delay can be up to _DORMANT_RETRY_S (300s); a plain
        asyncio.sleep would keep the coroutine (and, on the idle path, the backend
        WS) alive that long after a logout. stop() sets self._stop from the GUI
        thread (a plain bool write, GIL-atomic), so we poll it in short slices
        rather than cross-thread signalling an asyncio.Event (which is not
        thread-safe). This only runs in the exceptional backoff/dormant state, so
        the ~1s granularity is not a steady-state busy-wait.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + delay
        while not self._stop:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 1.0))

    async def _consume(
        self,
        session,
        document,
        field: str,
        callback: Callable[[dict], None],
        conversation_id: Optional[int],
        mark_healthy: Callable[[], None],
    ) -> None:
        async for result in session.subscribe(
            document,
            variable_values={"conversationId": conversation_id},
        ):
            if self._stop:
                break
            # First event proves the subscription is authenticated and live.
            mark_healthy()
            data = self._extract(result, field)
            if data:
                try:
                    callback(data)
                except Exception as cb_err:  # noqa: BLE001
                    logger.warning("%s callback error: %s", field, cb_err)

    @staticmethod
    def _extract(result, field: str) -> Optional[dict]:
        """gql yields the data dict; be tolerant of ExecutionResult too."""
        if isinstance(result, dict):
            return result.get(field)
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            return data.get(field)
        return None
