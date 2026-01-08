"""
Fila de clase: muestra metadatos de la sesión y los asientos como iconos.
"""
from typing import Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QScrollArea,
    QFrame,
)

from .seat_icon_widget import SeatIconWidget


class ClassRowWidget(QWidget):
    def __init__(self, session: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self._build_ui()

    # -----------------
    # UI
    # -----------------
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        meta = QWidget(self)
        meta_layout = QVBoxLayout(meta)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(2)

        time_label = QLabel(self._format_time_range(self.session.get("startAt"), self.session.get("endAt")))
        time_label.setStyleSheet("font-weight: 600;")

        name = self.session.get("name") or self.session.get("classTypeName") or "Clase"
        name_label = QLabel(str(name))
        name_label.setStyleSheet("color: palette(mid);")

        meta_layout.addWidget(time_label)
        meta_layout.addWidget(name_label)

        layout.addWidget(meta)

        # Contenedor de asientos con scroll horizontal si excede
        seat_container = QScrollArea(self)
        seat_container.setWidgetResizable(True)
        seat_container.setFrameShape(QFrame.Shape.NoFrame)
        seat_container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        seat_container.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        seat_widget = QWidget()
        seats_layout = QHBoxLayout(seat_widget)
        seats_layout.setContentsMargins(0, 0, 0, 0)
        seats_layout.setSpacing(6)

        for seat in self._normalize_seats(self.session.get("seats") or []):
            w = SeatIconWidget(seat_widget)
            w.set_seat(status=seat["status"], will_expire_soon=seat["willExpireSoon"], occupant=seat.get("occupant"))
            seats_layout.addWidget(w)

        seats_layout.addStretch()
        seat_container.setWidget(seat_widget)

        layout.addWidget(seat_container, 1)

    # -----------------
    # Helpers
    # -----------------
    def _format_time_range(self, start_at: Any, end_at: Any) -> str:
        try:
            import datetime as _dt
            def parse(v):
                if isinstance(v, str):
                    return _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
                return v
            s = parse(start_at)
            e = parse(end_at)
            if s and e:
                return f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"
        except Exception:
            pass
        return ""

    def _normalize_seats(self, seats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Asegurar claves camelCase consistentes con el servicio de frontend
        norm = []
        for s in seats:
            norm.append({
                "seatId": s.get("seatId") or s.get("seat_id"),
                "label": s.get("label"),
                "status": s.get("status", "free"),
                "willExpireSoon": bool(s.get("willExpireSoon") or s.get("will_expire_soon")),
                "occupant": s.get("occupant"),
            })
        return norm

