"""GraphQL subscription client over WebSocket for realtime chat updates.

Runs on the application's single AsyncioExecutor event loop. The long-lived
``run`` coroutine is submitted to the executor by the controller, and incoming
messages are delivered via a callback (which the controller bridges to a Qt signal).

Auth: the desktop cannot read the HttpOnly cookie, so the access token is sent in the
graphql-transport-ws ``connection_init`` payload as ``authToken`` (the backend reads it
from connection_params). Uses gql's WebsocketsTransport (graphql-ws subprotocol), which
the backend enables alongside graphql-transport-ws.
"""
import asyncio
import logging
from typing import Callable, Optional

from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport

from ..core.config import Config

logger = logging.getLogger(__name__)

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


class ChatSubscriptionClient:
    """Maintains WebSocket subscriptions to ``messageAdded``/``messageUpdated``
    with auto-reconnect."""

    def __init__(self) -> None:
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def run(
        self,
        on_message: Callable[[dict], None],
        get_token: Callable[[], Optional[str]],
        conversation_id: Optional[int] = None,
        on_message_updated: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """Subscribe and forward each event to its callback until stopped."""
        self._stop = False
        backoff = 1
        while not self._stop:
            token = get_token() if callable(get_token) else None
            init_payload = {"authToken": token} if token else {}
            transport = WebsocketsTransport(
                url=Config.GRAPHQL_WS_URL,
                init_payload=init_payload,
            )
            try:
                client = Client(transport=transport)
                async with client as session:
                    logger.info("Chat subscription connected")
                    backoff = 1
                    consumers = [
                        self._consume(
                            session,
                            MESSAGE_ADDED_SUBSCRIPTION,
                            "messageAdded",
                            on_message,
                            conversation_id,
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
                            )
                        )
                    # Both subscriptions share the connection; if one dies the
                    # gather raises and the outer loop reconnects both.
                    await asyncio.gather(*consumers)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.warning("Chat subscription error: %s; reconnecting in %ss", e, backoff)
            if self._stop:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 20)
        logger.info("Chat subscription stopped")

    async def _consume(
        self,
        session,
        document,
        field: str,
        callback: Callable[[dict], None],
        conversation_id: Optional[int],
    ) -> None:
        async for result in session.subscribe(
            document,
            variable_values={"conversationId": conversation_id},
        ):
            if self._stop:
                break
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
