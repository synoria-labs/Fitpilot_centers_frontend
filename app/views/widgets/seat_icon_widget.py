"""
SeatIconWidget: icono de asiento con color por estado y tooltip.
"""
from typing import Optional, Dict, Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget, QSizePolicy


class SeatIconWidget(QWidget):
    """Pequeño widget circular que representa un asiento.

    Estados:
    - libre (verde)
    - ocupado por vencer pronto (amarillo)
    - ocupado (rojo)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._status: str = "free"
        self._will_expire_soon: bool = False
        self._occupant: Optional[Dict[str, Any]] = None
        self._size = 22

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("Disponible")

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt signature)
        return QSize(self._size, self._size)

    # -----------------
    # Public API
    # -----------------
    def set_seat(self, *, status: str, will_expire_soon: bool, occupant: Optional[Dict[str, Any]]) -> None:
        self._status = status or "free"
        self._will_expire_soon = bool(will_expire_soon)
        self._occupant = occupant
        if self._status == "free" or self._occupant is None:
            self.setToolTip("Disponible")
        else:
            name = (self._occupant.get("fullName") or self._occupant.get("full_name") or "?") if isinstance(self._occupant, dict) else "?"
            self.setToolTip(f"Ocupado por: {name}")
        self.update()

    # -----------------
    # Painting
    # -----------------
    def _color(self) -> QColor:
        if self._status != "free":
            if self._will_expire_soon:
                return QColor("#FFC107")  # amarillo
            return QColor("#F44336")  # rojo
        return QColor("#4CAF50")  # verde

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self._color()
        pen = QPen(QColor(0, 0, 0, 60))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))

        size = min(self.width(), self.height())
        r = size - 2
        painter.drawEllipse(1, 1, r, r)

        # Indicador interno para ocupado (punto central) para mejor legibilidad
        if self._status != "free":
            inner = max(4, r // 3)
            painter.setBrush(QBrush(QColor(255, 255, 255, 180)))
            painter.setPen(Qt.PenStyle.NoPen)
            cx = 1 + r // 2 - inner // 2
            cy = 1 + r // 2 - inner // 2
            painter.drawEllipse(cx, cy, inner, inner)

