"""Scrollable list of message bubbles for a conversation."""
from typing import List, Set

import qtawesome as qta
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, QSize
from PySide6.QtWidgets import QScrollArea, QToolButton, QWidget, QVBoxLayout

from ....models.chat import ChatMessage
from .message_bubble import MessageBubble
from . import theme


_BOTTOM_THRESHOLD_PX = 48
_SCROLL_RETRY_COUNT = 4
_SCROLL_RETRY_MS = 16
_SCROLL_ANIMATION_MS = 180


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
        self._pending_scroll_mode = ""
        self._pending_scroll_attempts = 0

        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(_SCROLL_ANIMATION_MS)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._jump_button = QToolButton(self.viewport())
        self._jump_button.setObjectName("jumpToLatestButton")
        self._jump_button.setIcon(qta.icon("fa5s.chevron-down", color=theme.TEXT_PRIMARY))
        self._jump_button.setIconSize(QSize(16, 16))
        self._jump_button.setFixedSize(40, 40)
        self._jump_button.setToolTip("Ir al mensaje mas reciente")
        self._jump_button.setAutoRaise(True)
        self._jump_button.hide()
        self._jump_button.clicked.connect(self._on_jump_to_latest_clicked)

        self.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QToolButton#jumpToLatestButton {{
                background-color: {theme.BG_PANEL};
                border: 1px solid {theme.DIVIDER};
                border-radius: 20px;
                padding: 0;
            }}
            QToolButton#jumpToLatestButton:hover {{
                background-color: {theme.ITEM_HOVER};
            }}
            """
        )

    def set_messages(self, messages: List[ChatMessage]) -> None:
        self._clear()
        self.clear_new_message_indicator()
        for m in messages:
            self._add(m)
        self.scroll_to_bottom(animated=False)

    def append_message(
        self,
        message: ChatMessage,
        *,
        force_scroll: bool = False,
        show_new_message_button: bool = True,
    ) -> None:
        if message.id and message.id in self._seen_ids:
            return
        was_near_bottom = self.is_near_bottom()
        self._add(message)

        if force_scroll or was_near_bottom:
            self.clear_new_message_indicator()
            self.scroll_to_bottom(animated=True)
        elif show_new_message_button:
            self._show_new_message_indicator()

    def clear_new_message_indicator(self) -> None:
        self._jump_button.hide()

    def is_near_bottom(self) -> bool:
        scrollbar = self.verticalScrollBar()
        return scrollbar.maximum() - scrollbar.value() <= _BOTTOM_THRESHOLD_PX

    def scroll_to_bottom(self, *, animated: bool) -> None:
        self._pending_scroll_mode = "smooth" if animated else "instant"
        self._pending_scroll_attempts = _SCROLL_RETRY_COUNT
        self._apply_pending_scroll()

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

    def _show_new_message_indicator(self) -> None:
        self._position_jump_button()
        self._jump_button.show()
        self._jump_button.raise_()

    def _on_jump_to_latest_clicked(self) -> None:
        self.clear_new_message_indicator()
        self.scroll_to_bottom(animated=True)

    def _on_scroll_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._pending_scroll_mode == "instant":
            self.verticalScrollBar().setValue(maximum)
        elif self._pending_scroll_mode == "smooth":
            self._scroll_animation.setEndValue(maximum)
        self._position_jump_button()

    def _on_scroll_value_changed(self, _value: int) -> None:
        if self.is_near_bottom():
            self.clear_new_message_indicator()

    def _apply_pending_scroll(self) -> None:
        if not self._pending_scroll_mode:
            return

        scrollbar = self.verticalScrollBar()
        target = scrollbar.maximum()
        if self._pending_scroll_mode == "instant":
            self._scroll_animation.stop()
            scrollbar.setValue(target)

        self._pending_scroll_attempts -= 1
        if self._pending_scroll_attempts > 0:
            QTimer.singleShot(_SCROLL_RETRY_MS, self._apply_pending_scroll)
            return

        mode = self._pending_scroll_mode
        self._pending_scroll_mode = ""

        if mode == "smooth":
            self._animate_to_bottom()
        else:
            scrollbar.setValue(scrollbar.maximum())

    def _animate_to_bottom(self) -> None:
        scrollbar = self.verticalScrollBar()
        target = scrollbar.maximum()
        if scrollbar.value() == target:
            return
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(scrollbar.value())
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.start()

    def _position_jump_button(self) -> None:
        margin = 18
        x = self.viewport().width() - self._jump_button.width() - margin
        y = self.viewport().height() - self._jump_button.height() - margin
        self._jump_button.move(max(0, x), max(0, y))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_jump_button()
