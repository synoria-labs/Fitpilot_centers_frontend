"""A single chat message bubble, drawn with the same pieces as the template preview."""
import re
from dataclasses import dataclass
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ....models.chat import ChatMessage
from . import theme
from .media_widgets import MEDIA_BUBBLE_WIDTH, FailedMediaWidget, create_media_widget
from .message_formatter import clock_text, display_text_for_message, extract_useful_text, message_html
from .theme import WaPalette
from .wa_mockup import (
    BUBBLE_RADIUS,
    BUBBLE_TAIL,
    BubbleMeta,
    ButtonRow,
    QuoteBox,
    button_hint,
    button_icon_name,
    button_label,
    button_type,
    collapse_buttons,
    ideal_text_width,
    paint_bubble,
    wa_icon,
)

# Quick reactions offered by the picker (same default set as official WhatsApp).
QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"]

_SIDE_MARGIN = 20      # thread edge -> bubble tail
_RUN_GAP = 1           # above a bubble that continues its sender's run
_NEW_RUN_GAP = 7       # above the first bubble of a run (the one with the tail)
_INSET = 3             # quote/media inset from the bubble edge, as in the preview
_TEXT_INSET = 6        # on top of _INSET: text sits 9px from the edge
_CONTENT_BOTTOM = 7    # text bottom -> bubble edge (the timestamp sits in it)
_MAX_TEXT_WIDTH = 560

# The invisible run that reserves the timestamp's room at the end of the text
# (see wa_mockup.time_spacer_html): left out when the text is copied. ``\s`` also
# matches the non-breaking spaces it is made of.
_TIME_SPACER_RE = re.compile(r"\s{2,}\d{1,2}:\d{2}\s[ap]\.\s?m\.\s*$")

# Hairline above the template buttons of an outgoing (green) bubble; incoming ones use
# the palette's divider, which is tuned for the gray bubble.
_OUTGOING_BUTTON_DIVIDER = {"dark": "#2EFFFFFF", "light": "#17000000"}


@dataclass(frozen=True)
class QuotedMessage:
    """The message a reply quotes, as its quote box shows it."""

    author: str
    text: str
    accent: str


def _reaction_qss(pal: WaPalette) -> str:
    return f"""
QLabel#reactionPill {{
    background-color: {pal.bubble_in};
    color: {pal.text};
    border: 2px solid {pal.wallpaper};
    border-radius: 11px;
    padding: 0 5px;
    font-size: 14px;
}}
QToolButton#reactButton {{
    background-color: {pal.sheet_bg};
    border: none;
    border-radius: 14px;
}}
QToolButton#reactButton:hover {{ background-color: {pal.media_bg}; }}
"""


class ReactionPicker(QFrame):
    """Small frameless popup with the quick-reaction emojis."""

    selected = Signal(str)  # chosen emoji; "" means remove the current reaction

    def __init__(self, current: str = "", parent=None, *, pal: Optional[WaPalette] = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        pal = pal or theme.app_palette()
        self._current = (current or "").strip()
        self.setObjectName("reactionPicker")
        self.setStyleSheet(
            f"""
            #reactionPicker {{
                background-color: {pal.sheet_bg};
                border: 1px solid {pal.divider};
                border-radius: 18px;
            }}
            QToolButton {{ background: transparent; border: none; border-radius: 14px; font-size: 18px; }}
            QToolButton:hover {{ background-color: {pal.hover}; }}
            QToolButton#active {{ background-color: {pal.media_bg}; }}
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


class _BubbleText(QLabel):
    """Bubble text: WhatsApp formatting, selectable, links open in the browser. Copying
    leaves out the invisible run that keeps the timestamp's room.

    It asks for its unwrapped width (up to the bubble's maximum), so short messages hug
    their text with the timestamp on the same line, as in WhatsApp, and only long ones
    wrap; a narrow chat still squeezes it (QLabel's own minimum applies)."""

    _MIN_WIDTH = 60

    def __init__(self, html_text: str, pal: WaPalette, max_width: int, parent=None) -> None:
        super().__init__(parent)
        self._hovered_link = ""
        self._max_width = max_width
        self._ideal_width: Optional[int] = None
        self.setObjectName("bubbleText")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setOpenExternalLinks(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        font = self.font()
        font.setPixelSize(14)
        self.setFont(font)
        self.setStyleSheet(f"color: {pal.text}; background: transparent;")
        self.setText(html_text)
        self.linkHovered.connect(self._on_link_hovered)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        if self._ideal_width is None:
            self._ideal_width = ideal_text_width(self)
        width = max(self._MIN_WIDTH, min(self._max_width, self._ideal_width))
        return QSize(width, self.heightForWidth(width))

    def copy_selection(self) -> None:
        text = self.selectedText().replace(" ", "\n").replace(" ", "\n")
        QGuiApplication.clipboard().setText(_TIME_SPACER_RE.sub("", text).replace(" ", " "))

    def _on_link_hovered(self, link: str) -> None:
        self._hovered_link = link

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.matches(QKeySequence.StandardKey.Copy) and self.hasSelectedText():
            self.copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt override)
        menu = QMenu(self)
        copy = menu.addAction("Copiar")
        copy.setEnabled(self.hasSelectedText())
        copy.triggered.connect(self.copy_selection)
        if self._hovered_link:
            link = self._hovered_link
            menu.addAction("Copiar enlace").triggered.connect(
                lambda: QGuiApplication.clipboard().setText(link)
            )
        menu.exec(event.globalPos())


class _BubbleFrame(QFrame):
    """The bubble: painted by the preview's painter, with a column for the tail on its side
    (kept even without the tail, so the bubbles of a run line up), the timestamp overlaid
    at the bottom-right of its content and, for a template, its buttons underneath."""

    def __init__(self, pal: WaPalette, *, outgoing: bool, tail: bool, parent=None) -> None:
        super().__init__(parent)
        self._pal = pal
        self._outgoing = outgoing
        self._tail = tail
        self.meta: Optional[BubbleMeta] = None
        self.meta_bottom = _CONTENT_BOTTOM
        self.buttons_height = 0  # template button rows below the content

    def body_rect(self) -> QRectF:
        left = 0 if self._outgoing else BUBBLE_TAIL
        return QRectF(left, 0, self.width() - BUBBLE_TAIL, self.height() - 1)

    def place_meta(self) -> None:
        if self.meta is None:
            return
        body = self.body_rect()
        x = body.right() - _INSET - _TEXT_INSET - self.meta.width()
        y = self.height() - 1 - self.buttons_height - self.meta_bottom + 1 - self.meta.height()
        self.meta.move(int(x), int(y))
        self.meta.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._pal.bubble_out if self._outgoing else self._pal.bubble_in
        side = ("right" if self._outgoing else "left") if self._tail else None
        paint_bubble(painter, self.body_rect(), color, self._pal.shadow, tail=side)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.place_meta()


class MessageBubble(QWidget):
    retry_requested = Signal(int)         # message id (failed media download)
    reaction_requested = Signal(str, str)  # target wa_message_id, emoji ("" removes)

    _PILL_OVERHANG = 14  # px the reaction pill hangs below the bubble's bottom edge
    _PILL_INSET = 8      # px the pill is pulled over the bubble's inner corner

    def __init__(
        self,
        message: ChatMessage,
        parent=None,
        *,
        pal: Optional[WaPalette] = None,
        tail: bool = True,
        quote: Optional[QuotedMessage] = None,
    ) -> None:
        super().__init__(parent)
        self.message_id = message.id
        self.wa_message_id = message.wa_message_id
        self.has_tail = tail
        self.quote = quote
        self._pal = pal or theme.app_palette()
        self._is_inbound = message.is_inbound
        self._outer_margins = (_SIDE_MARGIN, _NEW_RUN_GAP if tail else _RUN_GAP, _SIDE_MARGIN, 1)
        self._outer = None
        self._bubble_frame = None
        self._reaction_pill = None
        self._react_button = None
        self._reaction_picker = None
        self._own_emoji = ""
        self._template_buttons = list(message.template_buttons)
        self.setStyleSheet(_reaction_qss(self._pal))
        self._build(message)

    def _build(self, message: ChatMessage) -> None:
        pal = self._pal
        outer = QHBoxLayout(self)
        outer.setContentsMargins(*self._outer_margins)
        outer.setSpacing(0)
        self._outer = outer

        # An inline photo defines the bubble width (WhatsApp-like): cap the bubble
        # to the image width so the caption wraps underneath at the same width
        # instead of stretching the bubble and leaving air to the image's right.
        has_inline_image = message.media is not None and message.media.media_type == "image"

        bubble = _BubbleFrame(pal, outgoing=not message.is_inbound, tail=self.has_tail)
        bubble.setObjectName("bubbleIn" if message.is_inbound else "bubbleOut")
        content_width = MEDIA_BUBBLE_WIDTH if has_inline_image else _MAX_TEXT_WIDTH
        bubble.setMaximumWidth(content_width + 2 * _INSET + BUBBLE_TAIL)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._bubble_frame = bubble

        tail_left = 0 if not message.is_inbound else BUBBLE_TAIL
        tail_right = BUBBLE_TAIL if not message.is_inbound else 0
        # The content keeps its inset; template buttons below it run edge to edge.
        frame = QVBoxLayout(bubble)
        frame.setSpacing(0)
        frame.setContentsMargins(tail_left, 0, tail_right, 1)
        content = QWidget(bubble)
        frame.addWidget(content)
        v = QVBoxLayout(content)
        v.setSpacing(0)

        if self.quote is not None:
            v.addWidget(
                QuoteBox(
                    self.quote.author,
                    self.quote.text,
                    None,
                    pal,
                    background=pal.quote_in_bg if message.is_inbound else pal.quote_bg,
                    accent=self.quote.accent,
                )
            )

        media_widget = create_media_widget(message, bubble, pal)
        if media_widget is not None:
            if isinstance(media_widget, FailedMediaWidget):
                media_widget.retry_requested.connect(self.retry_requested.emit)
            if self.quote is not None:
                v.addSpacing(_INSET)
            v.addWidget(media_widget)

        meta = BubbleMeta(
            pal,
            outgoing=not message.is_inbound,
            checks_color=pal.meta_out if not message.is_inbound else None,
            parent=bubble,
        )
        meta.set_text(self._fmt_time(message))
        bubble.meta = meta

        text = self._render_text(message, has_media=media_widget is not None)
        bubble_color = pal.bubble_in if message.is_inbound else pal.bubble_out
        if text:
            label = _BubbleText(
                message_html(text, pal, clickable_links=True) + meta.spacer_html(bubble_color),
                pal,
                content_width,
            )
            label.setContentsMargins(_TEXT_INSET, 4, _TEXT_INSET, 0)
            v.addWidget(label)
            bottom = _CONTENT_BOTTOM
        else:
            # Media alone: the timestamp gets its own strip under it.
            strip = QWidget()
            strip.setFixedHeight(meta.height() + 2)
            v.addWidget(strip)
            bottom = 2
        bubble.meta_bottom = bottom
        v.setContentsMargins(_INSET, _INSET, _INSET, bottom)
        if self._template_buttons:
            bubble.buttons_height = self._add_template_buttons(frame, bubble, outgoing=not message.is_inbound)

        if message.is_inbound:
            outer.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            outer.addStretch()
        else:
            outer.addStretch()
            outer.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)

    def _add_template_buttons(self, frame: QVBoxLayout, bubble: QWidget, *, outgoing: bool) -> int:
        """The template's buttons under the bubble, drawn as the member saw them (past three,
        «Ver todas las opciones»). Returns the height they take."""
        shown = collapse_buttons(self._template_buttons)
        divider = _OUTGOING_BUTTON_DIVIDER[self._pal.mode] if outgoing else self._pal.divider
        height = 0
        for index, button in enumerate(shown):
            row = ButtonRow(
                button,
                self._pal,
                last=index == len(shown) - 1,
                corner=BUBBLE_RADIUS,
                divider=divider,
                parent=bubble,
            )
            row.activated.connect(self._on_template_button)
            frame.addWidget(row)
            height += row.minimumHeight()
        return height

    def _on_template_button(self, button: dict) -> None:
        """The buttons only show what was sent: a click tells what it does for the member
        (and «Ver todas las opciones» lists them all)."""
        if button_type(button) != "SEE_ALL":
            QToolTip.showText(QCursor.pos(), button_hint(button), self)
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for item in self._template_buttons:
            action = menu.addAction(wa_icon(button_icon_name(item), self._pal.link), button_label(item))
            action.setToolTip(button_hint(item))
        menu.exec(QCursor.pos())

    @staticmethod
    def _render_text(message: ChatMessage, *, has_media: bool) -> str:
        if has_media:
            # The attachment is rendered visually; only show the caption text
            # (never the "[image]" style placeholder).
            return extract_useful_text(message.text_content, message.message_type)
        return display_text_for_message(message)

    @staticmethod
    def _fmt_time(message: ChatMessage) -> str:
        return clock_text(message.timestamp) if message.timestamp else ""

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
        left, top, right, bottom = self._outer_margins
        if active:
            bottom += self._PILL_OVERHANG
        self._outer.setContentsMargins(left, top, right, bottom)

    def _body_geometry(self):
        """The painted bubble (the frame minus its tail column), in this widget's coordinates."""
        geo = self._bubble_frame.geometry()
        if self._is_inbound:
            return geo.adjusted(BUBBLE_TAIL, 0, 0, 0)
        return geo.adjusted(0, 0, -BUBBLE_TAIL, 0)

    def _position_reaction_pill(self) -> None:
        pill = self._reaction_pill
        if pill is None or self._bubble_frame is None:
            return
        geo = self._body_geometry()
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
        button.setIcon(qta.icon("mdi6.emoticon-happy-outline", color=self._pal.header_icon))
        button.setIconSize(QSize(18, 18))
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
        geo = self._body_geometry()
        if geo.width() <= 0:
            return
        bw, bh = button.width(), button.height()
        y = geo.top() + max(0, (geo.height() - bh) // 2)
        gap = 6
        if self._is_inbound:
            x = geo.right() + gap
        else:
            x = geo.left() - bw - gap
        button.move(int(x), int(y))

    def _open_reaction_picker(self) -> None:
        if not self.wa_message_id:
            return
        picker = ReactionPicker(current=self._own_emoji, parent=self, pal=self._pal)
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
