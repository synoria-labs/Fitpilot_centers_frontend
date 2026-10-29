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
from ..services.whatsapp_chat_service import PAGE_SIZE
from ..threads.asyncio_executor import get_global_executor
from ..graphql.client import GraphQLClient
from ..graphql.ws_client import ChatSubscriptionClient

logger = get_logger(__name__)


class _WsBridge(QObject):
    """Bridges WS callbacks (executor thread) to the GUI thread via a queued signal."""
    message_received = Signal(object)
    message_update_received = Signal(object)


class WhatsAppChatController(BaseController):
    # (conversations, reset, has_more): reset -> replace list; else append page
    conversations_page_loaded = Signal(object, bool, bool)
    single_conversation_loaded = Signal(object)  # ChatConversation (incremental upsert)
    messages_loaded = Signal(object)        # List[ChatMessage]
    message_sent = Signal(object)           # ChatMessage
    send_failed = Signal(str)
    new_message = Signal(object)            # ChatMessage (realtime)
    message_updated = Signal(object)        # ChatMessage (media download finished/failed)
    bot_state_changed = Signal(int, bool)   # confirmed server state, even if another chat is open
    bot_state_save_failed = Signal(int, str)
    error_occurred = Signal(str)

    def __init__(self, chat_service, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = chat_service
        self._current_conversation_id: Optional[int] = None
        self._bot_states: dict[int, bool] = {}
        self._bot_state_revisions: dict[int, int] = {}
        self._pending_bot_updates: set[int] = set()

        self._ws_bridge = _WsBridge()
        self._ws_bridge.message_received.connect(
            self._on_ws_message, Qt.ConnectionType.QueuedConnection
        )
        self._ws_bridge.message_update_received.connect(
            self._on_ws_message_updated, Qt.ConnectionType.QueuedConnection
        )
        self._ws_client: Optional[ChatSubscriptionClient] = None
        self._ws_signals = None  # keep TaskSignals reference alive

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------
    def load_conversations(
        self,
        search: Optional[str] = None,
        limit: int = PAGE_SIZE,
        offset: int = 0,
        reset: bool = True,
    ) -> None:
        revisions = self._bot_state_revisions.copy()

        def _on_loaded(conversations: List[ChatConversation]) -> None:
            convs = conversations or []
            for conversation in convs:
                self._merge_bot_state(conversation, revisions.get(conversation.id, 0))
            has_more = len(convs) >= limit
            self.conversations_page_loaded.emit(convs, reset, has_more)

        self._execute_authenticated_operation(
            self._service,
            "get_conversations",
            _on_loaded,
            self._on_error,
            limit=limit,
            offset=offset,
            search=search,
        )

    def load_single_conversation(self, conversation_id: int) -> None:
        revision = self._bot_state_revisions.get(conversation_id, 0)

        def _on_loaded(conversation: Optional[ChatConversation]) -> None:
            if conversation is not None:
                self._merge_bot_state(conversation, revision)
                self._on_single_conversation_loaded(conversation)

        self._execute_authenticated_operation(
            self._service,
            "get_conversation",
            _on_loaded,
            self._on_error,
            conversation_id=conversation_id,
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

    def set_conversation_bot_enabled(self, conversation_id: int, enabled: bool) -> None:
        """Publish the confirmed state instead of discarding the mutation result."""
        if conversation_id in self._pending_bot_updates:
            return
        self._pending_bot_updates.add(conversation_id)
        self._bump_bot_revision(conversation_id)

        def _on_failed(error: str) -> None:
            self._pending_bot_updates.discard(conversation_id)
            self._bump_bot_revision(conversation_id)
            self.bot_state_save_failed.emit(conversation_id, error)
            logger.error("Bot state save failed for conversation %s: %s", conversation_id, error)
            # A lost response may still have committed on the server.
            self.load_single_conversation(conversation_id)

        def _on_saved(result: dict) -> None:
            if not result or not result.get("success") or not isinstance(result.get("bot_enabled"), bool):
                _on_failed((result or {}).get("error") or "No se pudo guardar el estado del bot.")
                return
            self._pending_bot_updates.discard(conversation_id)
            self._bump_bot_revision(conversation_id)
            self._bot_states[conversation_id] = result["bot_enabled"]
            self.bot_state_changed.emit(conversation_id, result["bot_enabled"])

        self._execute_authenticated_operation(
            self._service,
            "set_conversation_bot_enabled",
            _on_saved,
            _on_failed,
            conversation_id=conversation_id,
            enabled=enabled,
        )

    def _bump_bot_revision(self, conversation_id: int) -> None:
        self._bot_state_revisions[conversation_id] = self._bot_state_revisions.get(conversation_id, 0) + 1

    def _merge_bot_state(self, conversation: ChatConversation, revision: int) -> None:
        """Do not let a read started before/during a save undo its confirmed state."""
        cid = conversation.id
        stale = revision != self._bot_state_revisions.get(cid, 0) or cid in self._pending_bot_updates
        if stale and cid in self._bot_states:
            conversation.bot_enabled = self._bot_states[cid]
        else:
            self._bot_states[cid] = conversation.bot_enabled

    def mark_conversation_read(self, conversation_id: int) -> None:
        """Mark a conversation read on the backend (clears unread + sends read receipt).

        Fire-and-forget: the list badge is cleared locally for instant feedback; backend
        errors are logged but not surfaced (a failed read receipt must not disrupt the UI).
        """
        self._execute_authenticated_operation(
            self._service,
            "mark_conversation_read",
            lambda _result: None,
            lambda error: logger.warning("mark_conversation_read failed: %s", error),
            conversation_id=conversation_id,
        )

    def send_media(
        self,
        conversation_id: Optional[int],
        file_path: str,
        caption: Optional[str] = None,
        wa_id: Optional[str] = None,
        voice_note: bool = False,
    ) -> None:
        self._execute_authenticated_operation(
            self._service,
            "send_media_message",
            self._on_sent,
            self._on_error,
            conversation_id=conversation_id,
            wa_id=wa_id,
            file_path=file_path,
            caption=caption,
            voice_note=voice_note,
        )

    def send_reaction(
        self, conversation_id: Optional[int], message_id: str, emoji: str
    ) -> None:
        """React to a message (emoji="" removes it). The persisted reaction is applied
        to the target bubble via the ``new_message`` path (idempotent with the realtime echo)."""
        def _on_reacted(result: dict) -> None:
            if result and result.get("success") and result.get("message"):
                self.new_message.emit(result["message"])
            else:
                error = (result or {}).get("error") or "No se pudo enviar la reacción."
                self.error_occurred.emit(error)

        self._execute_authenticated_operation(
            self._service,
            "send_reaction",
            _on_reacted,
            self._on_error,
            conversation_id=conversation_id,
            message_id=message_id,
            emoji=emoji,
        )

    def retry_media_download(self, message_id: int) -> None:
        def _on_retry(result: dict) -> None:
            # The refreshed message (download pending again) re-renders the bubble.
            if result and result.get("success") and result.get("message"):
                self.message_updated.emit(result["message"])
            else:
                error = (result or {}).get("error") or "No se pudo reintentar la descarga."
                self.error_occurred.emit(error)

        self._execute_authenticated_operation(
            self._service,
            "retry_media_download",
            _on_retry,
            self._on_error,
            message_id=message_id,
        )

    @property
    def current_conversation_id(self) -> Optional[int]:
        return self._current_conversation_id

    # ------------------------------------------------------------------
    # Result handlers
    # ------------------------------------------------------------------
    def _on_single_conversation_loaded(self, conversation: Optional[ChatConversation]) -> None:
        if conversation is not None:
            self.single_conversation_loaded.emit(conversation)

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
            # The access token lives ~5 min; the WS client refreshes it (before
            # connecting and after auth errors) via the AuthService coroutine.
            refresh_token = None
            try:
                from ..core.di import container

                auth_service = container.get("auth_service")
                if auth_service is not None:
                    refresh_token = auth_service.refresh_token
            except Exception as e:  # noqa: BLE001 - realtime still works, sin refresh
                logger.warning("Chat realtime: auth_service unavailable for refresh: %s", e)

            self._ws_client = ChatSubscriptionClient()
            executor = get_global_executor()
            coro = self._ws_client.run(
                on_message=lambda data: self._ws_bridge.message_received.emit(data),
                get_token=GraphQLClient.current_access_token,
                conversation_id=None,  # all conversations; filter per view
                on_message_updated=lambda data: self._ws_bridge.message_update_received.emit(data),
                refresh_token=refresh_token,
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

    def _on_ws_message_updated(self, data: object) -> None:
        try:
            message = ChatMessage.from_dict(data) if isinstance(data, dict) else None
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to parse realtime message update: %s", e)
            return
        if message:
            self.message_updated.emit(message)
