"""Shared rendering helpers for chat membership chips."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from ....models.chat import ChatMembershipSnapshot

_ACTIVE = ("#DCFCE7", "#166534", "#86EFAC")
_EXPIRED = ("#FEE2E2", "#991B1B", "#FCA5A5")
_PENDING = ("#FEF3C7", "#92400E", "#FCD34D")
_NEUTRAL = ("#E5E7EB", "#374151", "#D1D5DB")


def _status_key(membership: Optional[ChatMembershipSnapshot]) -> str:
    return (membership.status if membership else "").strip().lower()


def membership_status_category(membership: Optional[ChatMembershipSnapshot]) -> str:
    """Normalize a membership snapshot to a single filter category.

    Returns one of: 'active', 'expired', 'pending', 'canceled', 'none'.
    'none' covers a missing membership (no linked member) or an unrecognized status.
    """
    status = _status_key(membership)
    if not status:
        return "none"
    if "active" in status or "activo" in status:
        return "active"
    if "expired" in status or "vencido" in status or "vencida" in status:
        return "expired"
    if "pending" in status or "pendiente" in status:
        return "pending"
    if "canceled" in status or "cancel" in status:
        return "canceled"
    return "none"


def membership_chip_text(membership: Optional[ChatMembershipSnapshot]) -> str:
    status = _status_key(membership)
    if not status:
        return ""

    days = membership.remaining_days if membership else None
    if "active" in status or "activo" in status:
        if days == 0:
            return "Activa · hoy"
        if days is not None:
            return f"Activa · {max(days, 0)}d"
        return "Activa"

    if "expired" in status or "vencido" in status or "vencida" in status:
        if days is not None:
            return f"Vencida · {abs(days)}d"
        return "Vencida"

    if "pending" in status or "pendiente" in status:
        return "Pendiente"

    if "canceled" in status or "cancel" in status:
        return "Cancelada"

    return "Sin estado"


def membership_chip_colors(
    membership: Optional[ChatMembershipSnapshot],
) -> Tuple[QColor, QColor, QColor]:
    status = _status_key(membership)
    if "active" in status or "activo" in status:
        colors = _ACTIVE
    elif "expired" in status or "vencido" in status or "vencida" in status:
        colors = _EXPIRED
    elif "pending" in status or "pendiente" in status:
        colors = _PENDING
    else:
        colors = _NEUTRAL
    return tuple(QColor(color) for color in colors)


def membership_chip_size(
    membership: Optional[ChatMembershipSnapshot],
    font: QFont,
) -> QSize:
    text = membership_chip_text(membership)
    if not text:
        return QSize(0, 0)
    metrics = QFontMetrics(font)
    return QSize(metrics.horizontalAdvance(text) + 14, max(18, metrics.height() + 4))


def paint_membership_chip(
    painter: QPainter,
    rect: QRect,
    membership: Optional[ChatMembershipSnapshot],
    font: QFont,
) -> None:
    text = membership_chip_text(membership)
    if not text or rect.width() <= 0 or rect.height() <= 0:
        return

    background, foreground, border = membership_chip_colors(membership)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setFont(font)
    painter.setPen(QPen(border, 1))
    painter.setBrush(background)
    radius = rect.height() / 2
    painter.drawRoundedRect(rect, radius, radius)
    painter.setPen(foreground)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
    painter.restore()


def membership_chip_stylesheet(
    membership: Optional[ChatMembershipSnapshot],
    *,
    object_name: str,
) -> str:
    background, foreground, border = membership_chip_colors(membership)
    return f"""
QLabel#{object_name} {{
    background-color: {background.name()};
    color: {foreground.name()};
    border: 1px solid {border.name()};
    border-radius: 9px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 700;
}}
"""
