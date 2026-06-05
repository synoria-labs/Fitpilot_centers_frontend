"""Left-hand conversation list (chats), WhatsApp-style.

Backed by a ``QListView`` + ``ConversationListModel`` + ``ConversationItemDelegate``
(paint-based rendering), so the list scales to thousands of rows and supports
incremental updates and infinite scroll without rebuilding per-row widgets.
"""
from typing import List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QModelIndex
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....models.chat import ChatConversation, ChatMessage
from . import theme
from .conversation_list_model import CONVERSATION_ROLE, ConversationListModel
from .conversation_item_delegate import ConversationItemDelegate

# How close to the bottom (px) before requesting the next page.
_LOAD_MORE_THRESHOLD = 240


def _style() -> str:
    return f"""
#convPanel {{ background-color: palette(window); }}
#convHeader {{ background-color: palette(window); }}
#convTitle {{ color: palette(text); font-size: 22px; font-weight: 700; background: transparent; }}
#convSearchBar {{ background-color: palette(window); }}
#convFilterBar {{ background-color: palette(window); }}
#convSearch {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid transparent;
    border-radius: 20px;
    padding: 0 16px;
    min-height: 40px;
    max-height: 40px;
    font-size: 13px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    placeholder-text-color: palette(placeholder-text);
}}
#convSearch:focus {{ border: 1px solid palette(highlight); }}
#convSearch:disabled {{
    background-color: palette(window);
    color: palette(mid);
}}
#convSearch::placeholder {{ color: palette(placeholder-text); }}
#convIconButton {{
    background: transparent;
    border: none;
    border-radius: 16px;
    padding: 6px;
}}
#convIconButton:hover {{ background-color: palette(alternate-base); }}
#convChip, #convChipActive {{
    border: 1px solid palette(mid);
    border-radius: 15px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}
#convChip {{
    color: palette(text);
    background-color: transparent;
}}
#convChipActive {{
    color: palette(highlighted-text);
    background-color: palette(highlight);
    border-color: palette(highlight);
}}
QListView {{
    background-color: palette(window);
    border: none;
    outline: 0;
}}
"""


def _make_icon_button(icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("convIconButton")
    button.setIcon(qta.icon(icon_name, color=theme.palette_hex()))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(34, 34)
    button.setToolTip(tooltip)
    button.setEnabled(False)
    button.setAutoRaise(True)
    return button


def _make_chip(label: str, active: bool = False) -> QLabel:
    chip = QLabel(label)
    chip.setObjectName("convChipActive" if active else "convChip")
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setFixedHeight(30)
    return chip


class ConversationListWidget(QWidget):
    conversation_selected = Signal(int)
    search_changed = Signal(str)
    load_more_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("convPanel")
        self.setStyleSheet(_style())
        self._search_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("convHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 8)
        header_layout.setSpacing(10)

        title = QLabel("Chats")
        title.setObjectName("convTitle")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        header_layout.addWidget(title, 1)
        header_layout.addWidget(_make_icon_button("fa5s.plus", "Proximamente: nuevo chat"))
        header_layout.addWidget(_make_icon_button("fa5s.ellipsis-v", "Proximamente: mas opciones"))
        layout.addWidget(header)

        search_bar = QWidget()
        search_bar.setObjectName("convSearchBar")
        sb_layout = QHBoxLayout(search_bar)
        sb_layout.setContentsMargins(20, 8, 20, 8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("convSearch")
        self.search_input.setPlaceholderText("Buscar un chat o iniciar uno nuevo")
        self.search_input.setClearButtonEnabled(True)
        sb_layout.addWidget(self.search_input)
        layout.addWidget(search_bar)

        filters = QWidget()
        filters.setObjectName("convFilterBar")
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(20, 0, 20, 10)
        filter_layout.setSpacing(8)
        for label, active in (
            ("Todos", True),
            ("No leidos", False),
            ("Favoritos", False),
            ("Grupos", False),
            ("Etiquetas", False),
        ):
            filter_layout.addWidget(_make_chip(label, active))
        filter_layout.addStretch()
        layout.addWidget(filters)

        self._model = ConversationListModel(self)
        self.list_view = QListView()
        self.list_view.setModel(self._model)
        self.list_view.setItemDelegate(ConversationItemDelegate(self.list_view))
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setMouseTracking(True)
        layout.addWidget(self.list_view, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._emit_search)

        self.search_input.textChanged.connect(self._on_search_text)
        self.list_view.clicked.connect(self._on_item_clicked)
        self.list_view.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def current_search(self) -> str:
        return self._search_text

    def reset_conversations(self, conversations: List[ChatConversation]) -> None:
        """Replace the whole list (first page / new search), preserving selection."""
        selected_id = self.selected_conversation_id()
        self._model.reset(conversations)
        if selected_id is not None:
            self._select_conversation(selected_id)

    # Backwards-compatible alias.
    def set_conversations(self, conversations: List[ChatConversation]) -> None:
        self.reset_conversations(conversations)

    def append_conversations(self, conversations: List[ChatConversation]) -> None:
        self._model.append(conversations)

    def upsert_conversation(self, conversation: ChatConversation) -> None:
        selected_id = self.selected_conversation_id()
        self._model.upsert(conversation, promote=True)
        if selected_id is not None:
            self._select_conversation(selected_id)

    def apply_message(self, message: ChatMessage) -> bool:
        selected_id = self.selected_conversation_id()
        moved = self._model.apply_message(message)
        if moved and selected_id is not None:
            self._select_conversation(selected_id)
        return moved

    def get_conversation(self, conversation_id: int) -> Optional[ChatConversation]:
        return self._model.get(conversation_id)

    def selected_conversation_id(self) -> Optional[int]:
        index = self.list_view.currentIndex()
        if index.isValid():
            conv = index.data(CONVERSATION_ROLE)
            if conv is not None:
                return conv.id
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _select_conversation(self, conversation_id: int) -> None:
        row = self._model.index_of(conversation_id)
        if row is not None:
            self.list_view.setCurrentIndex(self._model.index(row))

    def _on_item_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        conv = index.data(CONVERSATION_ROLE)
        if conv is not None:
            self.conversation_selected.emit(int(conv.id))

    def _on_scrolled(self, value: int) -> None:
        bar = self.list_view.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        if value >= bar.maximum() - _LOAD_MORE_THRESHOLD:
            self.load_more_requested.emit()

    def _on_search_text(self, text: str) -> None:
        self._search_text = text
        self._search_timer.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self._search_text)
