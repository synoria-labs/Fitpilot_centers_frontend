"""Paint-based delegate for conversation rows (replaces per-row QWidgets).

Renders the same WhatsApp-style row as the old ``_ConversationItem`` widget
(avatar, name, secondary identity, snippet, time, unread badge) but by painting,
so the list scales to thousands of rows with no per-row widget cost.
"""
from datetime import datetime
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ....models.chat import ChatConversation
from . import theme
from .conversation_list_model import CONVERSATION_ROLE
from .membership_chip import membership_chip_size, paint_membership_chip
from .message_formatter import snippet_for_message

_AVATAR_SIZE = 48
_LEFT_MARGIN = 12
_RIGHT_MARGIN = 14
_GAP = 12         # avatar <-> text
_LINE_GAP = 3     # between text lines
_CHIP_GAP = 8

_HEIGHT_MEMBER = 88
_HEIGHT_PLAIN = 72


class ConversationItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._snippet_cache: Dict[Tuple[int, str], str] = {}

        self._name_font = QFont()
        self._name_font.setPixelSize(14)
        self._name_font.setBold(True)
        self._time_font = QFont()
        self._time_font.setPixelSize(10)
        self._identity_font = QFont()
        self._identity_font.setPixelSize(11)
        self._snippet_font = QFont()
        self._snippet_font.setPixelSize(12)
        self._unread_font = QFont()
        self._unread_font.setPixelSize(10)
        self._unread_font.setBold(True)
        self._chip_font = QFont()
        self._chip_font.setPixelSize(10)
        self._chip_font.setBold(True)
        avatar_px = max(12, _AVATAR_SIZE // 2 - 4)
        self._avatar_font = QFont()
        self._avatar_font.setPixelSize(avatar_px)
        self._avatar_font.setBold(True)

    # ------------------------------------------------------------------
    def sizeHint(self, option, index) -> QSize:
        conv = index.data(CONVERSATION_ROLE)
        height = _HEIGHT_MEMBER if (conv and conv.contact.member_name) else _HEIGHT_PLAIN
        return QSize(50, height)

    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, index) -> None:
        conv: Optional[ChatConversation] = index.data(CONVERSATION_ROLE)
        if conv is None:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Background.
        if selected or hover:
            background_rect = rect.adjusted(6, 4, -6, -4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.color(QPalette.ColorRole.AlternateBase))
            painter.drawRoundedRect(background_rect, 8, 8)
        # Bottom divider.
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        primary = palette.text().color()
        secondary = _secondary_color(palette)

        # Avatar.
        avatar_x = rect.left() + _LEFT_MARGIN
        avatar_y = rect.top() + (rect.height() - _AVATAR_SIZE) // 2
        self._paint_avatar(painter, avatar_x, avatar_y, conv.display_name)

        # Text block geometry.
        text_left = avatar_x + _AVATAR_SIZE + _GAP
        text_right = rect.right() - _RIGHT_MARGIN
        text_width = max(0, text_right - text_left)

        has_member = bool(conv.contact.member_name)
        identity_text = conv.contact.secondary_identity if has_member else ""
        show_identity = has_member and bool(identity_text)

        name_h = QFontMetrics(self._name_font).height()
        identity_h = QFontMetrics(self._identity_font).height() if show_identity else 0
        snippet_h = QFontMetrics(self._snippet_font).height()
        block_h = name_h + snippet_h
        if show_identity:
            block_h += identity_h + _LINE_GAP
        block_h += _LINE_GAP
        start_y = rect.top() + (rect.height() - block_h) // 2

        # --- Top line: name + time ---
        time_text = self._fmt_time(conv.last_activity)
        time_fm = QFontMetrics(self._time_font)
        time_w = time_fm.horizontalAdvance(time_text) if time_text else 0
        top_right = text_right - (time_w + _GAP if time_text else 0)
        top_width = max(0, top_right - text_left)

        chip_size = membership_chip_size(conv.contact.member_membership, self._chip_font)
        draw_chip = chip_size.width() > 0 and top_width >= chip_size.width() + 48
        chip_rect = QRect()
        if draw_chip:
            chip_rect = QRect(
                top_right - chip_size.width(),
                start_y + (name_h - chip_size.height()) // 2,
                chip_size.width(),
                chip_size.height(),
            )

        if time_text:
            painter.setFont(self._time_font)
            painter.setPen(secondary)
            time_rect = QRect(text_right - time_w, start_y, time_w, name_h)
            painter.drawText(time_rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), time_text)

        name_w = (
            max(0, chip_rect.left() - text_left - _CHIP_GAP)
            if draw_chip
            else top_width
        )
        painter.setFont(self._name_font)
        painter.setPen(primary)
        name_fm = QFontMetrics(self._name_font)
        name = name_fm.elidedText(conv.display_name, Qt.TextElideMode.ElideRight, name_w)
        painter.drawText(QRect(text_left, start_y, name_w, name_h),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
        if draw_chip:
            paint_membership_chip(
                painter,
                chip_rect,
                conv.contact.member_membership,
                self._chip_font,
            )

        cursor_y = start_y + name_h + _LINE_GAP

        # --- Identity line (members only) ---
        if show_identity:
            painter.setFont(self._identity_font)
            painter.setPen(secondary)
            identity_fm = QFontMetrics(self._identity_font)
            identity = identity_fm.elidedText(identity_text, Qt.TextElideMode.ElideRight, text_width)
            painter.drawText(QRect(text_left, cursor_y, text_width, identity_h),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), identity)
            cursor_y += identity_h + _LINE_GAP

        # --- Bottom line: snippet + unread badge ---
        unread_w = 0
        if conv.unread_count > 0:
            unread_w = self._paint_unread(painter, conv.unread_count, text_right, cursor_y, snippet_h, selected, palette)
            unread_w += _GAP

        snippet_text = self._snippet(conv)
        painter.setFont(self._snippet_font)
        painter.setPen(secondary)
        snippet_fm = QFontMetrics(self._snippet_font)
        snippet = snippet_fm.elidedText(snippet_text, Qt.TextElideMode.ElideRight, max(0, text_width - unread_w))
        painter.drawText(QRect(text_left, cursor_y, max(0, text_width - unread_w), snippet_h),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), snippet)

        painter.restore()

    # ------------------------------------------------------------------
    def _paint_avatar(self, painter: QPainter, x: int, y: int, name: str) -> None:
        color = QColor(theme.avatar_color(name))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(x, y, _AVATAR_SIZE, _AVATAR_SIZE)
        painter.setFont(self._avatar_font)
        painter.setPen(QColor("white"))
        painter.drawText(QRect(x, y, _AVATAR_SIZE, _AVATAR_SIZE),
                         int(Qt.AlignmentFlag.AlignCenter), theme.avatar_initials(name))

    def _paint_unread(self, painter: QPainter, count: int, right: int, y: int,
                      line_h: int, selected: bool, palette) -> int:
        text = str(count)
        fm = QFontMetrics(self._unread_font)
        diameter = 18
        width = max(diameter, fm.horizontalAdvance(text) + 10)
        badge_y = y + (line_h - diameter) // 2
        badge_rect = QRect(right - width, badge_y, width, diameter)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawRoundedRect(badge_rect, diameter / 2, diameter / 2)
        painter.setFont(self._unread_font)
        painter.setPen(QColor("#0b141a"))
        painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), text)
        return width

    # ------------------------------------------------------------------
    def _snippet(self, conversation: ChatConversation) -> str:
        lm = conversation.last_message
        if not lm:
            return ""
        key = (lm.id, lm.direction)
        cached = self._snippet_cache.get(key)
        if cached is None:
            prefix = "" if lm.is_inbound else "Tu: "
            cached = f"{prefix}{snippet_for_message(lm)}"
            if len(self._snippet_cache) > 4000:
                self._snippet_cache.clear()
            self._snippet_cache[key] = cached
        return cached

    @staticmethod
    def _fmt_time(ts: Optional[datetime]) -> str:
        if not ts:
            return ""
        try:
            return ts.strftime("%d/%m %H:%M")
        except Exception:  # noqa: BLE001
            return ""


def _secondary_color(palette) -> QColor:
    """Blend text over window (~0.6) to match theme.secondary_text_hex()."""
    fg = palette.text().color()
    bg = palette.window().color()
    w = 0.62

    def ch(a: int, b: int) -> int:
        return round(b * (1.0 - w) + a * w)

    return QColor(ch(fg.red(), bg.red()), ch(fg.green(), bg.green()), ch(fg.blue(), bg.blue()))
