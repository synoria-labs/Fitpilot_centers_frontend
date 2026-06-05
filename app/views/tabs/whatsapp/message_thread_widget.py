"""Scrollable list of message bubbles for a conversation."""
from typing import List, Set

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout

from ....models.chat import ChatMessage
from .message_bubble import MessageBubble


class MessageThreadWidget(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("threadScroll")

        self._container = QWidget()
        self._container.setObjectName("threadContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)
        self._layout.addStretch()  # index 0: keeps bubbles stacked from the top

        self.setWidget(self._container)
        self.setStyleSheet(
            "#threadScroll { border: none; background-color: palette(window); }"
            " #threadContainer { background-color: palette(window); }"
        )

        self._seen_ids: Set[int] = set()

    def set_messages(self, messages: List[ChatMessage]) -> None:
        self._clear()
        for m in messages:
            self._add(m)
        self._scroll_to_bottom()

    def append_message(self, message: ChatMessage) -> None:
        if message.id and message.id in self._seen_ids:
            return
        self._add(message)
        self._scroll_to_bottom()

    def _add(self, message: ChatMessage) -> None:
        if message.id:
            if message.id in self._seen_ids:
                return
            self._seen_ids.add(message.id)
        bubble = MessageBubble(message)
        self._layout.addWidget(bubble)

    def _clear(self) -> None:
        self._seen_ids.clear()
        while self._layout.count() > 1:  # keep the trailing stretch at index 0
            item = self._layout.takeAt(self._layout.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))
