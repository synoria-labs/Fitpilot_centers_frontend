"""A single chat message bubble (WhatsApp-style)."""
import qtawesome as qta
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy

from ....models.chat import ChatMessage
from . import theme
from .media_widgets import FailedMediaWidget, create_media_widget
from .message_formatter import display_text_for_message, extract_useful_text

_STYLE = f"""
#bubbleIn {{
    background-color: {theme.BUBBLE_IN};
    border-top-left-radius: 2px;
    border-top-right-radius: 8px;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}
#bubbleOut {{
    background-color: {theme.BUBBLE_OUT};
    border-top-left-radius: 8px;
    border-top-right-radius: 2px;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}
#bubbleIn QLabel, #bubbleOut QLabel {{ color: {theme.TEXT_PRIMARY}; background: transparent; }}
QLabel#bubbleText {{ font-size: 13px; }}
QLabel#bubbleTime {{ color: {theme.TEXT_SECONDARY}; font-size: 10px; }}
"""


class MessageBubble(QWidget):
    retry_requested = Signal(int)  # message id (failed media download)

    def __init__(self, message: ChatMessage, parent=None) -> None:
        super().__init__(parent)
        self.message_id = message.id
        self.setStyleSheet(_STYLE)
        self._build(message)

    def _build(self, message: ChatMessage) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 4, 16, 4)
        outer.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("bubbleIn" if message.is_inbound else "bubbleOut")
        bubble.setMaximumWidth(560)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        v = QVBoxLayout(bubble)
        v.setContentsMargins(10, 7, 10, 6)
        v.setSpacing(3)

        media_widget = create_media_widget(message, bubble)
        if media_widget is not None:
            if isinstance(media_widget, FailedMediaWidget):
                media_widget.retry_requested.connect(self.retry_requested.emit)
            v.addWidget(media_widget)

        text = self._render_text(message, has_media=media_widget is not None)
        if text:
            text_label = QLabel(text)
            text_label.setObjectName("bubbleText")
            text_label.setTextFormat(Qt.TextFormat.PlainText)
            text_label.setWordWrap(True)
            text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(text_label)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)
        meta.addStretch()

        time_label = QLabel(self._fmt_time(message))
        time_label.setObjectName("bubbleTime")
        meta.addWidget(time_label)

        if not message.is_inbound:
            check_label = QLabel()
            check_label.setPixmap(
                qta.icon("fa5s.check-double", color="#8bd9d0").pixmap(QSize(14, 10))
            )
            meta.addWidget(check_label)

        v.addLayout(meta)

        if message.is_inbound:
            outer.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            outer.addStretch()
        else:
            outer.addStretch()
            outer.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _render_text(message: ChatMessage, *, has_media: bool) -> str:
        if has_media:
            # The attachment is rendered visually; only show the caption text
            # (never the "[image]" style placeholder).
            return extract_useful_text(message.text_content, message.message_type)
        return display_text_for_message(message)

    @staticmethod
    def _fmt_time(message: ChatMessage) -> str:
        ts = message.timestamp
        if not ts:
            return ""
        try:
            return ts.strftime("%d/%m %H:%M")
        except Exception:  # noqa: BLE001
            return ""
