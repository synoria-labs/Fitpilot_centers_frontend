"""WhatsApp chat tab: conversation list + message thread + composer.

Mirrors the official WhatsApp layout (chats on the left, conversation on the right).
Realtime updates arrive via the controller's WebSocket subscription.
"""
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QStackedWidget, QFrame,
    QToolButton,
)

from ....controllers.whatsapp_chat_controller import WhatsAppChatController
from ....core import container, get_logger
from ....models.chat import ChatConversation, ChatMessage
from ....services.whatsapp_chat_service import PAGE_SIZE
from ....utils.dialog_helpers import show_error
from . import theme
from .avatar import Avatar
from .conversation_list_widget import ConversationListWidget
from .message_thread_widget import MessageThreadWidget
from .composer_widget import ComposerWidget

logger = get_logger(__name__)


def _style() -> str:
    return f"""
#chatTab {{ background-color: palette(window); }}
#chatTab QSplitter::handle {{ background-color: palette(mid); width: 1px; }}
#chatHeader {{
    background-color: palette(alternate-base);
    border-bottom: 1px solid palette(mid);
}}
QLabel#headerName {{ color: palette(text); font-weight: bold; font-size: 14px; background: transparent; }}
QLabel#headerSub {{ color: {theme.secondary_text_hex(background_role=QPalette.ColorRole.AlternateBase)}; font-size: 11px; background: transparent; }}
#chatActionButton {{
    background: transparent;
    border: none;
    border-radius: 17px;
    padding: 7px;
}}
#chatActionButton:hover {{ background-color: palette(base); }}
#emptyState {{ background-color: palette(window); }}
QLabel#emptyIcon {{ font-size: 64px; background: transparent; }}
QLabel#emptyTitle {{ color: palette(text); font-size: 20px; background: transparent; }}
QLabel#emptySub {{ color: {theme.secondary_text_hex()}; font-size: 13px; background: transparent; }}
"""


def _make_header_action(icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("chatActionButton")
    button.setIcon(qta.icon(icon_name, color=theme.palette_hex()))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(36, 36)
    button.setToolTip(tooltip)
    button.setEnabled(False)
    button.setAutoRaise(True)
    return button


class ChatTab(QWidget):
    """Main WhatsApp chat widget. Exposes `.controller` for MainController."""

    def __init__(self) -> None:
        super().__init__()
        logger.info("Initializing ChatTab")
        self.setObjectName("chatTab")
        self.setStyleSheet(_style())

        chat_service = container.get("whatsapp_chat_service")
        self.controller = WhatsAppChatController(chat_service, self)

        self._current_conversation_id: Optional[int] = None

        # Pagination state for the infinite-scroll conversation list.
        self._page_size: int = PAGE_SIZE
        self._offset: int = 0
        self._has_more: bool = True
        self._loading: bool = False
        self._current_search: Optional[str] = None

        self._build_ui()
        self._connect_signals()

        self._load_first_page()
        self.controller.start_realtime()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.conversation_list = ConversationListWidget()
        splitter.addWidget(self.conversation_list)

        # Right side: stack with an empty-state page and the conversation page.
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty_state())   # index 0
        self.right_stack.addWidget(self._build_conversation_pane())  # index 1
        self.right_stack.setCurrentIndex(0)
        splitter.addWidget(self.right_stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 900])
        splitter.setChildrenCollapsible(False)

        root.addWidget(splitter)

    def _build_empty_state(self) -> QWidget:
        page = QWidget()
        page.setObjectName("emptyState")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icon = QLabel("💬")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("FitPilot Chats")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Selecciona un chat para empezar a conversar")
        sub.setObjectName("emptySub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(sub)
        return page

    def _build_conversation_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with avatar + name + phone subtitle.
        header = QFrame()
        header.setObjectName("chatHeader")
        header.setFixedHeight(64)
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 8, 12, 8)
        h.setSpacing(12)

        self._header_avatar = Avatar("", size=40)
        h.addWidget(self._header_avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        name_box = QVBoxLayout()
        name_box.setSpacing(0)
        self._header_name = QLabel("")
        self._header_name.setObjectName("headerName")
        self._header_sub = QLabel("")
        self._header_sub.setObjectName("headerSub")
        name_box.addWidget(self._header_name)
        name_box.addWidget(self._header_sub)
        h.addLayout(name_box, 1)

        h.addWidget(_make_header_action("fa5s.search", "Proximamente: buscar en chat"))
        h.addWidget(_make_header_action("fa5s.video", "Proximamente: videollamada"))
        h.addWidget(_make_header_action("fa5s.phone-alt", "Proximamente: llamada"))
        h.addWidget(_make_header_action("fa5s.ellipsis-v", "Proximamente: mas opciones"))

        layout.addWidget(header)

        self.thread = MessageThreadWidget()
        layout.addWidget(self.thread, 1)

        self.composer = ComposerWidget()
        layout.addWidget(self.composer)
        return pane

    def _connect_signals(self) -> None:
        self.conversation_list.conversation_selected.connect(self._on_conversation_selected)
        self.conversation_list.search_changed.connect(self._on_search)
        self.conversation_list.load_more_requested.connect(self._on_load_more)
        self.composer.send_requested.connect(self._on_send)
        self.composer.attachment_requested.connect(self._on_send_media)
        self.thread.retry_requested.connect(self._on_retry_media)
        self.thread.reaction_requested.connect(self._on_reaction_requested)

        self.controller.conversations_page_loaded.connect(self._on_conversations_page_loaded)
        self.controller.single_conversation_loaded.connect(self._on_single_conversation_loaded)
        self.controller.messages_loaded.connect(self.thread.set_messages)
        self.controller.message_sent.connect(self._on_message_sent)
        self.controller.send_failed.connect(self._on_send_failed)
        self.controller.new_message.connect(self._on_new_message)
        self.controller.message_updated.connect(self._on_message_updated)
        self.controller.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def _load_first_page(self) -> None:
        self._offset = 0
        self._has_more = True
        self._loading = True
        self.controller.load_conversations(
            search=self._current_search,
            limit=self._page_size,
            offset=0,
            reset=True,
        )

    def _on_load_more(self) -> None:
        if self._loading or not self._has_more:
            return
        self._loading = True
        self._offset += self._page_size
        self.controller.load_conversations(
            search=self._current_search,
            limit=self._page_size,
            offset=self._offset,
            reset=False,
        )

    def _on_conversations_page_loaded(self, conversations, reset: bool, has_more: bool) -> None:
        self._loading = False
        self._has_more = has_more
        if reset:
            self.conversation_list.reset_conversations(conversations)
        else:
            self.conversation_list.append_conversations(conversations)
        self._refresh_open_header()

    def _on_single_conversation_loaded(self, conversation: ChatConversation) -> None:
        self.conversation_list.upsert_conversation(conversation)
        self._refresh_open_header()

    def _refresh_open_header(self) -> None:
        if self._current_conversation_id is None:
            return
        conv = self.conversation_list.get_conversation(self._current_conversation_id)
        if conv:
            self._update_header(conv)

    def _on_conversation_selected(self, conversation_id: int) -> None:
        self._current_conversation_id = conversation_id
        self.thread.clear_new_message_indicator()
        conv = self.conversation_list.get_conversation(conversation_id)
        if conv:
            self._update_header(conv)
        self.right_stack.setCurrentIndex(1)
        self.controller.load_messages(conversation_id)

    def _update_header(self, conv: ChatConversation) -> None:
        self._header_avatar.set_name(conv.display_name, size=40)
        self._header_name.setText(conv.display_name)
        identity = conv.contact.secondary_identity or conv.contact.phone_number or conv.contact.wa_id
        self._header_sub.setText(identity)

    def _on_search(self, query: str) -> None:
        self._current_search = query or None
        self._load_first_page()

    def _on_send(self, text: str) -> None:
        if self._current_conversation_id is None:
            return
        self.controller.send_text(self._current_conversation_id, text)

    def _on_send_media(self, file_path: str, caption: str) -> None:
        if self._current_conversation_id is None:
            return
        self.composer.set_sending(True)
        self.controller.send_media(
            self._current_conversation_id, file_path, caption or None
        )

    def _on_retry_media(self, message_id: int) -> None:
        self.controller.retry_media_download(message_id)

    def _on_reaction_requested(self, target_wa_id: str, emoji: str) -> None:
        if self._current_conversation_id is None or not target_wa_id:
            return
        self.controller.send_reaction(self._current_conversation_id, target_wa_id, emoji)

    def _on_message_sent(self, message: ChatMessage) -> None:
        self.composer.set_sending(False)
        if message.conversation_id == self._current_conversation_id:
            self.thread.append_message(
                message,
                force_scroll=True,
                show_new_message_button=False,
            )
        if not message.is_reaction:
            self._apply_message_to_list(message)

    def _on_send_failed(self, error: str) -> None:
        self.composer.set_sending(False)
        show_error(self, error, title="No se pudo enviar")

    def _on_message_updated(self, message: ChatMessage) -> None:
        """A media download finished/failed: re-render the bubble in place."""
        if message.conversation_id == self._current_conversation_id:
            self.thread.update_message(message)
        self._apply_message_to_list(message)

    def _on_new_message(self, message: ChatMessage) -> None:
        if message.conversation_id == self._current_conversation_id:
            self.thread.append_message(
                message,
                force_scroll=False,
                show_new_message_button=True,
            )
        # Reactions don't reorder the chat list or change its preview (WhatsApp behavior).
        if not message.is_reaction:
            self._apply_message_to_list(message)

    def _on_error(self, error: str) -> None:
        logger.error("ChatTab error: %s", error)

    def _apply_message_to_list(self, message: ChatMessage) -> None:
        """Update the list incrementally: bump the conversation, or fetch it if new.

        Avoids reloading the whole list on every message. When the conversation is
        not currently loaded (new chat, or beyond the loaded pages), fetch just that
        one conversation and insert it at the top.
        """
        if not self.conversation_list.apply_message(message):
            self.controller.load_single_conversation(message.conversation_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        try:
            self.controller.stop_realtime()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
