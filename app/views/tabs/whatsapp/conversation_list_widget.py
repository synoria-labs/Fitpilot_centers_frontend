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
from .message_formatter import snippet_for_message


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
QListWidget {{
    background-color: palette(window);
    border: none;
    outline: 0;
}}
QListWidget::item {{
    border-bottom: 1px solid palette(mid);
    padding: 0;
}}
QListWidget::item:hover {{ background-color: palette(alternate-base); }}
QListWidget::item:selected {{
    background-color: palette(highlight);
    color: palette(highlighted-text);
}}
#convItem {{ background-color: transparent; }}
#convItem[selected="true"] {{ background-color: palette(highlight); }}
QLabel#convName {{ color: palette(text); font-weight: bold; font-size: 14px; background: transparent; }}
QLabel#convIdentity {{ color: {theme.secondary_text_hex()}; font-size: 11px; background: transparent; }}
QLabel#convSnippet {{ color: {theme.secondary_text_hex()}; font-size: 12px; background: transparent; }}
QLabel#convTime {{ color: {theme.secondary_text_hex()}; font-size: 10px; background: transparent; }}
#convItem[selected="true"] QLabel#convName,
#convItem[selected="true"] QLabel#convIdentity,
#convItem[selected="true"] QLabel#convSnippet,
#convItem[selected="true"] QLabel#convTime {{
    color: palette(highlighted-text);
}}
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


class _ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        width = max(0, self.width())
        text = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            width,
        )
        super().setText(text)


class _ConversationItem(QWidget):
    def __init__(self, conversation: ChatConversation, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("convItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._has_member_name = bool(conversation.contact.member_name)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 14, 8)
        row.setSpacing(12)

        row.addWidget(Avatar(conversation.display_name, size=48), 0, Qt.AlignmentFlag.AlignVCenter)

        center = QVBoxLayout()
        center.setSpacing(3)
        center.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        name = _ElidedLabel(conversation.display_name)
        name.setObjectName("convName")
        top.addWidget(name, 1)
        time = QLabel(self._fmt_time(conversation))
        time.setObjectName("convTime")
        top.addWidget(time, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        center.addLayout(top)

        identity_text = conversation.contact.secondary_identity if self._has_member_name else ""
        if identity_text:
            identity = _ElidedLabel(identity_text)
            identity.setObjectName("convIdentity")
            identity.setMaximumHeight(16)
            center.addWidget(identity)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        snippet = _ElidedLabel(self._snippet(conversation))
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

    @property
    def item_height(self) -> int:
        return 88 if self._has_member_name else 72

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        for label in self.findChildren(QLabel):
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()
        self.update()

    @staticmethod
    def _snippet(conversation: ChatConversation) -> str:
        lm = conversation.last_message
        if not lm:
            return ""
        prefix = "" if lm.is_inbound else "Tu: "
        body = snippet_for_message(lm)
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

        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_widget, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._emit_search)

        self.search_input.textChanged.connect(self._on_search_text)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemSelectionChanged.connect(self._refresh_item_selection)

    def current_search(self) -> str:
        return self._search_text

    def set_conversations(self, conversations: List[ChatConversation]) -> None:
        selected_id = self.selected_conversation_id()
        self.list_widget.clear()
        for conv in conversations:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, conv.id)
            widget = _ConversationItem(conv)
            item.setSizeHint(QSize(0, widget.item_height))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)
            if conv.id == selected_id:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)
        self._refresh_item_selection()

    def selected_conversation_id(self):
        item = self.list_widget.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if conv_id is not None:
            self.conversation_selected.emit(int(conv_id))

    def _refresh_item_selection(self) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            widget = self.list_widget.itemWidget(item)
            if hasattr(widget, "set_selected"):
                widget.set_selected(item.isSelected())

    def _on_search_text(self, text: str) -> None:
        self._search_text = text
        self._search_timer.start()

    def _emit_search(self) -> None:
        self.search_changed.emit(self._search_text)
