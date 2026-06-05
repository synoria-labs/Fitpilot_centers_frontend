"""Controller for the WhatsApp chat tab.

Follows the BaseController pattern: data operations run through the AsyncioExecutor via
``_execute_authenticated_operation``; results are delivered as Qt signals. Realtime
updates come from a long-lived WebSocket subscription whose callback is bridged to the
GUI thread via a Qt signal.
"""
from typing import Optional, List

from PySide6.QtCore import QObject, Signal, Qt

from .base_controller import BaseController
from ..core.logging import get_logger
from ..models.chat import ChatConversation, ChatMessage
from ..threads.asyncio_executor import get_global_executor
from ..graphql.client import GraphQLClient
from ..graphql.ws_client import ChatSubscriptionClient

logger = get_logger(__name__)


class _WsBridge(QObject):
    """Bridges WS callbacks (executor thread) to the GUI thread via a queued signal."""
    message_received = Signal(object)


class WhatsAppChatController(BaseController):
    conversations_loaded = Signal(object)   # List[ChatConversation]
    messages_loaded = Signal(object)        # List[ChatMessage]
    message_sent = Signal(object)           # ChatMessage
    send_failed = Signal(str)
    new_message = Signal(object)            # ChatMessage (realtime)
    error_occurred = Signal(str)

    def __init__(self, chat_service, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = chat_service
        self._current_conversation_id: Optional[int] = None

        self._ws_bridge = _WsBridge()
        self._ws_bridge.message_received.connect(
            self._on_ws_message, Qt.ConnectionType.QueuedConnection
        )
        self._ws_client: Optional[ChatSubscriptionClient] = None
        self._ws_signals = None  # keep TaskSignals reference alive

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------
    def load_conversations(self, search: Optional[str] = None) -> None:
        self._execute_authenticated_operation(
            self._service,
            "get_conversations",
            self._on_conversations_loaded,
            self._on_error,
            search=search,
        )

    def load_messages(self, conversation_id: int) -> None:
        self._current_conversation_id = conversation_id
        self._execute_authenticated_operation(
            self._service,
            "get_messages",
            self._on_messages_loaded,
            self._on_error,
            conversation_id=conversation_id,
        )

    def send_text(self, conversation_id: Optional[int], text: str, wa_id: Optional[str] = None) -> None:
        self._execute_authenticated_operation(
            self._service,
            "send_text_message",
            self._on_sent,
            self._on_error,
            conversation_id=conversation_id,
            wa_id=wa_id,
            text=text,
        )

    @property
    def current_conversation_id(self) -> Optional[int]:
        return self._current_conversation_id

    # ------------------------------------------------------------------
    # Result handlers
    # ------------------------------------------------------------------
    def _on_conversations_loaded(self, conversations: List[ChatConversation]) -> None:
        self.conversations_loaded.emit(conversations or [])

    def _on_messages_loaded(self, messages: List[ChatMessage]) -> None:
        self.messages_loaded.emit(messages or [])

    def _on_sent(self, result: dict) -> None:
        if result and result.get("success") and result.get("message"):
            self.message_sent.emit(result["message"])
        else:
            error = (result or {}).get("error") or "No se pudo enviar el mensaje."
            self.send_failed.emit(error)

    def _on_error(self, error: str) -> None:
        logger.error("WhatsApp chat operation error: %s", error)
        self.error_occurred.emit(error)

    # ------------------------------------------------------------------
    # Realtime
    # ------------------------------------------------------------------
    def start_realtime(self) -> None:
        if self._ws_client is not None:
            return
        try:
            self._ws_client = ChatSubscriptionClient()
            executor = get_global_executor()
            coro = self._ws_client.run(
                on_message=lambda data: self._ws_bridge.message_received.emit(data),
                get_token=GraphQLClient.current_access_token,
                conversation_id=None,  # all conversations; filter per view
            )
            self._ws_signals = executor.submit_coroutine(coro)
            self._ws_signals.error.connect(
                lambda e: logger.warning("Chat subscription task error: %s", e)
            )
            logger.info("WhatsApp chat realtime started")
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to start chat realtime: %s", e)
            self._ws_client = None

    def stop_realtime(self) -> None:
        if self._ws_client is not None:
            self._ws_client.stop()
            self._ws_client = None

    def _on_ws_message(self, data: object) -> None:
        try:
            message = ChatMessage.from_dict(data) if isinstance(data, dict) else None
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to parse realtime message: %s", e)
            return
        if message:
            self.new_message.emit(message)
