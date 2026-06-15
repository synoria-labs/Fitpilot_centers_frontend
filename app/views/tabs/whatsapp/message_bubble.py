"""A single chat message bubble (WhatsApp-style)."""
import qtawesome as qta
from PySide6.QtCore import Qt, QSize, QPoint, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy, QToolButton,
)

from ....models.chat import ChatMessage
from . import theme
from .media_widgets import MEDIA_BUBBLE_WIDTH, FailedMediaWidget, create_media_widget
from .message_formatter import display_text_for_message, extract_useful_text

# Quick reactions offered by the picker (same default set as official WhatsApp).
QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"]

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
QLabel#reactionPill {{
    background-color: {theme.BG_PANEL};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.DIVIDER};
    border-radius: 9px;
    padding: 1px 5px;
    font-size: 14px;
}}
QToolButton#reactButton {{
    background-color: {theme.BG_PANEL};
    border: 1px solid {theme.DIVIDER};
    border-radius: 14px;
}}
QToolButton#reactButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
"""

_OUTER_MARGINS = (16, 4, 16, 4)


class ReactionPicker(QFrame):
    """Small frameless popup with the quick-reaction emojis."""

    selected = Signal(str)  # chosen emoji; "" means remove the current reaction

    def __init__(self, current: str = "", parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._current = (current or "").strip()
        self.setObjectName("reactionPicker")
        self.setStyleSheet(
            f"""
            #reactionPicker {{
                background-color: {theme.BG_PANEL};
                border: 1px solid {theme.DIVIDER};
                border-radius: 18px;
            }}
            QToolButton {{ background: transparent; border: none; border-radius: 14px; font-size: 18px; }}
            QToolButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
            QToolButton#active {{ background-color: {theme.ITEM_SELECTED}; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        for emoji in QUICK_REACTIONS:
            button = QToolButton()
            button.setText(emoji)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(30, 30)
            if emoji == self._current:
                button.setObjectName("active")
            button.clicked.connect(lambda _checked=False, e=emoji: self._choose(e))
            layout.addWidget(button)

    def _choose(self, emoji: str) -> None:
        # Clicking the already-selected reaction toggles it off (removal).
        self.selected.emit("" if emoji == self._current else emoji)
        self.close()


class MessageBubble(QWidget):
    retry_requested = Signal(int)         # message id (failed media download)
    reaction_requested = Signal(str, str)  # target wa_message_id, emoji ("" removes)

    _PILL_OVERHANG = 12  # px the reaction pill hangs below the bubble's bottom edge
    _PILL_INSET = 8      # px the pill is pulled over the bubble's inner corner

    def __init__(self, message: ChatMessage, parent=None) -> None:
        super().__init__(parent)
        self.message_id = message.id
        self.wa_message_id = message.wa_message_id
        self._is_inbound = message.is_inbound
        self._outer = None
        self._bubble_frame = None
        self._reaction_pill = None
        self._react_button = None
        self._reaction_picker = None
        self._own_emoji = ""
        self.setStyleSheet(_STYLE)
        self._build(message)

    def _build(self, message: ChatMessage) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(*_OUTER_MARGINS)
        outer.setSpacing(0)
        self._outer = outer

        # An inline photo defines the bubble width (WhatsApp-like): cap the bubble
        # to the image width so the caption wraps underneath at the same width
        # instead of stretching the bubble and leaving air to the image's right.
        has_inline_image = message.media is not None and message.media.media_type == "image"

        bubble = QFrame()
        bubble.setObjectName("bubbleIn" if message.is_inbound else "bubbleOut")
        bubble.setMaximumWidth(MEDIA_BUBBLE_WIDTH + 20 if has_inline_image else 560)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._bubble_frame = bubble

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

    # ------------------------------------------------------------------
    # Reactions (badge pill + send affordance)
    # ------------------------------------------------------------------
    def set_reactions(self, state: dict) -> None:
        """Show/clear the reaction pill.

        ``state`` maps a reactor direction to its emoji, e.g.
        ``{"inbound": "👍", "outbound": "❤️"}``. Missing/empty entries mean no
        reaction from that side. An empty state removes the pill.
        """
        self._own_emoji = (state.get("outbound") or "").strip()
        emojis = [e for e in (state.get("inbound"), state.get("outbound")) if (e or "").strip()]

        if not emojis:
            if self._reaction_pill is not None:
                self._reaction_pill.deleteLater()
                self._reaction_pill = None
                self._update_reaction_margin(active=False)
            return

        if self._reaction_pill is None:
            pill = QLabel(self)
            pill.setObjectName("reactionPill")
            pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            pill.setTextFormat(Qt.TextFormat.PlainText)
            pill.hide()  # revealed by _position_reaction_pill once geometry is valid
            self._reaction_pill = pill
            self._update_reaction_margin(active=True)

        self._reaction_pill.setText("".join(emojis))
        self._reaction_pill.adjustSize()
        self._reaction_pill.raise_()
        self._position_reaction_pill()
        QTimer.singleShot(0, self._position_reaction_pill)  # after the margin relayout

    def _update_reaction_margin(self, *, active: bool) -> None:
        if self._outer is None:
            return
        left, top, right, bottom = _OUTER_MARGINS
        if active:
            bottom += self._PILL_OVERHANG
        self._outer.setContentsMargins(left, top, right, bottom)

    def _position_reaction_pill(self) -> None:
        pill = self._reaction_pill
        if pill is None or self._bubble_frame is None:
            return
        geo = self._bubble_frame.geometry()
        if geo.width() <= 0:
            return
        pw, ph = pill.width(), pill.height()
        y = geo.bottom() - ph + self._PILL_OVERHANG
        if self._is_inbound:
            x = geo.right() - pw + self._PILL_INSET
        else:
            x = geo.left() - self._PILL_INSET
        pill.move(int(x), int(y))
        pill.show()

    def _ensure_react_button(self) -> None:
        if self._react_button is not None or not self.wa_message_id:
            return
        button = QToolButton(self)
        button.setObjectName("reactButton")
        button.setIcon(qta.icon("fa5s.smile", color=theme.TEXT_SECONDARY))
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(28, 28)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("Reaccionar")
        button.clicked.connect(self._open_reaction_picker)
        button.hide()
        self._react_button = button

    def _position_react_button(self) -> None:
        button = self._react_button
        if button is None or self._bubble_frame is None:
            return
        geo = self._bubble_frame.geometry()
        if geo.width() <= 0:
            return
        bw, bh = button.width(), button.height()
        y = geo.top() + max(0, (geo.height() - bh) // 2)
        gap = 4
        if self._is_inbound:
            x = geo.right() + gap
        else:
            x = geo.left() - bw - gap
        button.move(int(x), int(y))

    def _open_reaction_picker(self) -> None:
        if not self.wa_message_id:
            return
        picker = ReactionPicker(current=self._own_emoji, parent=self)
        self._reaction_picker = picker  # keep a reference so it isn't GC'd while open
        picker.selected.connect(self._on_reaction_chosen)
        picker.adjustSize()
        button = self._react_button
        if button is not None:
            anchor = button.mapToGlobal(QPoint(0, 0))
            x = anchor.x() - (picker.width() - button.width()) // 2
            y = anchor.y() - picker.height() - 4
            picker.move(x, y)
        picker.show()

    def _on_reaction_chosen(self, emoji: str) -> None:
        self.reaction_requested.emit(self.wa_message_id or "", emoji)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_reaction_pill()
        self._position_react_button()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._position_reaction_pill()
        self._position_react_button()

    def enterEvent(self, event) -> None:
        if self.wa_message_id:
            self._ensure_react_button()
            if self._react_button is not None:
                self._position_react_button()
                self._react_button.show()
                self._react_button.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._react_button is not None:
            self._react_button.hide()
        super().leaveEvent(event)
