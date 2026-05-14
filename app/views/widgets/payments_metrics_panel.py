"""Payments metrics panel for the Finances tab.

Six compact metric cards arranged horizontally, refreshed from the GraphQL
``payment_metrics`` payload. Cards are theme-aware: backgrounds and secondary
text use ``palette(...)`` so the panel matches whatever Qt theme (light/dark)
is active. Orphan and duplicate cards switch to a warning accent when their
count is non-zero, surfacing integrity issues without a separate dashboard.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# Refined palette. Each accent has enough contrast on both light and dark
# backgrounds; idle/alert pairs let cards "wake up" on bad signals.
# Secondary text uses a hard-coded medium gray instead of palette(mid) because
# palette(mid) is intended for separators and reads as nearly invisible on most
# dark themes.
_INCOME = "#2ecc71"      # emerald
_COUNT = "#3498db"       # blue
_AVG = "#1abc9c"         # turquoise (distinct from blue/green)
_PENDING = "#f39c12"     # amber
_IDLE = "#bdc3c7"        # silver — readable "all good" state
_ORPHAN_ALERT = "#e74c3c"  # red — broken integrity
_DUP_ALERT = "#e67e22"     # orange — needs review

_SECONDARY_TEXT = "#a0a8b0"  # readable on dark + acceptable on light


_CARD_QSS_TEMPLATE = """
QFrame#compactMetricCard {{
    background-color: palette(alternate-base);
    border: 1px solid palette(mid);
    border-left: 3px solid {accent};
    border-radius: 5px;
}}
"""


def _money(value: float | int | None) -> str:
    if value is None:
        return "$0"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0"


def _count(value: float | int | None) -> str:
    if value is None:
        return "0"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _top_method_trend(metrics: Dict[str, Any]) -> Optional[str]:
    by_method = metrics.get("byMethod") or []
    if not by_method:
        return None
    top = max(by_method, key=lambda b: float(b.get("total") or 0))
    return f"Top: {top.get('method', '?')}"


class _CompactMetricCard(QFrame):
    """Compact, theme-aware metric card.

    Layout:
        ▎ 💵  Ingresos
        ▎ $4,400.00
        ▎ Top: cash
    """

    def __init__(
        self, title: str, icon: str, accent: str, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("compactMetricCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._accent = accent
        self._build()
        self._apply_accent()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(1)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.setContentsMargins(0, 0, 0, 0)
        self._icon = QLabel(self._icon_text() if hasattr(self, "_icon_text") else "")
        header.addWidget(self._icon)
        self._title = QLabel("")
        header.addWidget(self._title)
        header.addStretch()
        outer.addLayout(header)

        self._value = QLabel("0")
        outer.addWidget(self._value)

        self._trend = QLabel("")
        self._trend.setVisible(False)
        outer.addWidget(self._trend)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(78)

    def _apply_accent(self) -> None:
        self.setStyleSheet(_CARD_QSS_TEMPLATE.format(accent=self._accent))
        self._icon.setStyleSheet(
            f"font-size: 14px; color: {self._accent}; background: transparent; border: none;"
        )
        self._title.setStyleSheet(
            f"font-size: 11px; color: {_SECONDARY_TEXT}; background: transparent; "
            f"border: none; font-weight: 500;"
        )
        self._value.setStyleSheet(
            f"font-size: 19px; font-weight: bold; color: {self._accent}; "
            f"background: transparent; border: none;"
        )
        self._trend.setStyleSheet(
            f"font-size: 10px; color: {_SECONDARY_TEXT}; background: transparent; border: none;"
        )

    # ----------------------------------------------------------------- public

    def configure(self, *, icon: str, title: str) -> None:
        self._icon.setText(icon)
        self._title.setText(title)

    def set_value(self, value: str, trend: Optional[str] = None) -> None:
        self._value.setText(value)
        if trend:
            self._trend.setText(trend)
            self._trend.setVisible(True)
        else:
            self._trend.setVisible(False)

    def set_accent(self, accent: str) -> None:
        if accent == self._accent:
            return
        self._accent = accent
        self._apply_accent()


class PaymentsMetricsPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._income = _CompactMetricCard("Ingresos", "💵", _INCOME)
        self._income.configure(icon="💵", title="Ingresos")

        self._count = _CompactMetricCard("Transacciones", "🧾", _COUNT)
        self._count.configure(icon="🧾", title="Transacciones")

        self._avg = _CompactMetricCard("Ticket promedio", "📊", _AVG)
        self._avg.configure(icon="📊", title="Ticket promedio")

        self._pending = _CompactMetricCard("Pendientes", "⏳", _PENDING)
        self._pending.configure(icon="⏳", title="Pendientes")

        self._orphan = _CompactMetricCard("Pagos huérfanos", "🔗", _IDLE)
        self._orphan.configure(icon="🔗", title="Pagos huérfanos")

        self._dup = _CompactMetricCard("Posibles duplicados", "⚠️", _IDLE)
        self._dup.configure(icon="⚠️", title="Posibles duplicados")

        for card in (
            self._income,
            self._count,
            self._avg,
            self._pending,
            self._orphan,
            self._dup,
        ):
            layout.addWidget(card, 1)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(86)

    # ----------------------------------------------------------------- public

    def update_metrics(self, metrics: Optional[Dict[str, Any]]) -> None:
        if not metrics:
            self.clear()
            return

        completed = metrics.get("completedAmount", metrics.get("totalAmount"))
        self._income.set_value(_money(completed), trend=_top_method_trend(metrics))

        self._count.set_value(_count(metrics.get("totalCount")))

        self._avg.set_value(_money(metrics.get("avgAmount")))

        pending_amount = metrics.get("pendingAmount") or 0
        pending_count = int(metrics.get("pendingCount") or 0)
        trend = f"{pending_count} pago(s)" if pending_count else None
        self._pending.set_value(_money(pending_amount), trend=trend)

        orphan_count = int(metrics.get("orphanCount") or 0)
        self._orphan.set_accent(_ORPHAN_ALERT if orphan_count > 0 else _IDLE)
        self._orphan.set_value(_count(orphan_count))

        dup_count = int(metrics.get("duplicateSuspectCount") or 0)
        self._dup.set_accent(_DUP_ALERT if dup_count > 0 else _IDLE)
        self._dup.set_value(_count(dup_count))

    def clear(self) -> None:
        self._income.set_value("$0")
        self._count.set_value("0")
        self._avg.set_value("$0")
        self._pending.set_value("$0")
        self._orphan.set_accent(_IDLE)
        self._orphan.set_value("0")
        self._dup.set_accent(_IDLE)
        self._dup.set_value("0")
