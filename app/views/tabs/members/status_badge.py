"""Utilities for rendering membership status icons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QBrush


def status_color(estado: str) -> QColor:
    estado_clean = (estado or "").strip().lower()
    if "activo" in estado_clean or "active" in estado_clean:
        return QColor(76, 175, 80)
    if "vencido" in estado_clean or "expired" in estado_clean:
        return QColor(244, 67, 54)
    if "vence pronto" in estado_clean or "pendiente" in estado_clean or "pending" in estado_clean:
        return QColor(255, 193, 7)
    return QColor(158, 158, 158)


def create_status_icon(estado: str, size: int = 14) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = status_color(estado)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.darker(130), 1))
    diameter = size - 2
    painter.drawEllipse(1, 1, diameter, diameter)
    painter.end()

    return QIcon(pixmap)
