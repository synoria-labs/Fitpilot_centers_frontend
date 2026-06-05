"""A single chat message bubble (WhatsApp-style)."""
import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame

from ....models.chat import ChatMessage
from . import theme

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
    def __init__(self, message: ChatMessage, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_STYLE)
        self._build(message)

    def _build(self, message: ChatMessage) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 3, 10, 3)

        bubble = QFrame()
        bubble.setObjectName("bubbleIn" if message.is_inbound else "bubbleOut")
        bubble.setMaximumWidth(520)

        v = QVBoxLayout(bubble)
        v.setContentsMargins(10, 6, 10, 5)
        v.setSpacing(2)

        text_label = QLabel(self._render_text(message))
        text_label.setObjectName("bubbleText")
        text_label.setWordWrap(True)
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
    def _render_text(message: ChatMessage) -> str:
        if message.message_type and message.message_type != "text":
            placeholder = theme.MEDIA_LABELS.get(message.message_type, f"[{message.message_type}]")
            if message.text_content:
                return f"{placeholder}\n{message.text_content}"
            return placeholder
        return message.text_content or ""

    @staticmethod
    def _fmt_time(message: ChatMessage) -> str:
        ts = message.timestamp
        if not ts:
            return ""
        try:
            return ts.strftime("%d/%m %H:%M")
        except Exception:  # noqa: BLE001
            return ""
