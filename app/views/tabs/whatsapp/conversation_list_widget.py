"""Left-hand conversation list (chats), WhatsApp-style."""
from typing import List

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....models.chat import ChatConversation
from . import theme
from .avatar import Avatar

_STYLE = f"""
#convPanel {{ background-color: palette(window); }}
#convHeader {{ background-color: palette(window); }}
#convTitle {{ color: {theme.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent; }}
#convSearchBar {{ background-color: palette(window); }}
#convFilterBar {{ background-color: palette(window); }}
#convSearch {{
    background-color: {theme.INPUT_BG};
    color: {theme.TEXT_PRIMARY};
    border: none;
    border-radius: 20px;
    padding: 9px 16px;
    font-size: 13px;
}}
#convSearch::placeholder {{ color: {theme.TEXT_SECONDARY}; }}
#convIconButton {{
    background: transparent;
    border: none;
    border-radius: 16px;
    padding: 6px;
}}
#convIconButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
#convChip, #convChipActive {{
    border: 1px solid {theme.DIVIDER};
    border-radius: 15px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}
#convChip {{
    color: {theme.TEXT_SECONDARY};
    background-color: transparent;
}}
#convChipActive {{
    color: {theme.TEXT_PRIMARY};
    background-color: {theme.ITEM_SELECTED};
}}
QListWidget {{
    background-color: palette(window);
    border: none;
    outline: 0;
}}
QListWidget::item {{
    border-bottom: 1px solid {theme.DIVIDER};
    padding: 0;
}}
QListWidget::item:hover {{ background-color: {theme.ITEM_HOVER}; }}
QListWidget::item:selected {{ background-color: {theme.ITEM_SELECTED}; }}
QLabel#convName {{ color: {theme.TEXT_PRIMARY}; font-weight: bold; font-size: 14px; background: transparent; }}
QLabel#convSnippet {{ color: {theme.TEXT_SECONDARY}; font-size: 12px; background: transparent; }}
QLabel#convTime {{ color: {theme.TEXT_SECONDARY}; font-size: 10px; background: transparent; }}
QLabel#convUnread {{
    color: #0b141a;
    background-color: {theme.ACCENT};
    border-radius: 9px;
    min-width: 18px;
    min-height: 18px;
    font-size: 10px;
    font-weight: 700;
}}
"""


def _make_icon_button(icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("convIconButton")
    button.setIcon(qta.icon(icon_name, color=theme.TEXT_PRIMARY))
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


class _ConversationItem(QWidget):
    def __init__(self, conversation: ChatConversation, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 14, 8)
        row.setSpacing(12)

        row.addWidget(Avatar(conversation.display_name, size=48), 0, Qt.AlignmentFlag.AlignVCenter)

        center = QVBoxLayout()
        center.setSpacing(3)
        center.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        name = QLabel(conversation.display_name)
        name.setObjectName("convName")
        top.addWidget(name, 1)
        time = QLabel(self._fmt_time(conversation))
        time.setObjectName("convTime")
        top.addWidget(time, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        center.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        snippet = QLabel(self._snippet(conversation))
        snippet.setObjectName("convSnippet")
        snippet.setMaximumHeight(18)
        bottom.addWidget(snippet, 1)

        if conversation.unread_count > 0:
            unread = QLabel(str(conversation.unread_count))
            unread.setObjectName("convUnread")
            unread.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bottom.addWidget(unread, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        center.addLayout(bottom)
        row.addLayout(center, 1)

    @staticmethod
    def _snippet(conversation: ChatConversation) -> str:
        lm = conversation.last_message
        if not lm:
            return ""
        prefix = "" if lm.is_inbound else "Tu: "
        if lm.message_type and lm.message_type != "text":
            body = theme.MEDIA_LABELS.get(lm.message_type, f"[{lm.message_type}]")
        else:
            body = lm.text_content or ""
        body = body.replace("\n", " ")
        if len(body) > 48:
            body = body[:48] + "..."
        return f"{prefix}{body}"

    @staticmethod
    def _fmt_time(conversation: ChatConversation) -> str:
        ts = conversation.last_activity
        if not ts:
            return ""
        try:
            return ts.strftime("%d/%m %H:%M")
        except Exception:  # noqa: BLE001
            return ""


class ConversationListWidget(QWidget):
    conversation_selected = Signal(int)
    search_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("convPanel")
        self.setStyleSheet(_STYLE)
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

        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_widget, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._emit_search)

        self.search_input.textChanged.connect(self._on_search_text)
        self.list_widget.itemClicked.connect(self._on_item_clicked)

    def current_search(self) -> str:
        return self._search_text

    def set_conversations(self, conversations: List[ChatConversation]) -> None:
        selected_id = self.selected_conversation_id()
        self.list_widget.clear()
        for conv in conversations:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, conv.id)
            widget = _ConversationItem(conv)
            item.setSizeHint(QSize(0, 72))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)
            if conv.id == selected_id:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)

    def selected_conversation_id(self):
        item = self.list_widget.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if conv_id is not None:
            self.conversation_selected.emit(int(conv_id))

    def _on_search_text(self, text: str) -> None:
        self._search_text = text
        self._search_timer.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self._search_text)
