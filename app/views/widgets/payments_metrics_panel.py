"""Payments metrics panel for the Finances tab.

Six compact metric cards arranged horizontally, refreshed from the GraphQL
``payment_metrics`` payload. Cards use the shared ``CompactMetricCard`` widget
so the visual language stays consistent with other tabs (Dashboard, etc.).
Orphan and duplicate cards switch to a warning accent when their count is
non-zero, surfacing integrity issues without a separate dashboard.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from .compact_metric_card import CompactMetricCard


# Refined palette. Each accent has enough contrast on both light and dark
# backgrounds; idle/alert pairs let cards "wake up" on bad signals.
_INCOME = "#2ecc71"      # emerald
_COUNT = "#3498db"       # blue
_AVG = "#1abc9c"         # turquoise (distinct from blue/green)
_PENDING = "#f39c12"     # amber
_IDLE = "#bdc3c7"        # silver — readable "all good" state
_ORPHAN_ALERT = "#e74c3c"  # red — broken integrity
_DUP_ALERT = "#e67e22"     # orange — needs review


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


class PaymentsMetricsPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._income = CompactMetricCard("Ingresos", "💵", _INCOME)
        self._count = CompactMetricCard("Transacciones", "🧾", _COUNT)
        self._avg = CompactMetricCard("Ticket promedio", "📊", _AVG)
        self._pending = CompactMetricCard("Pendientes", "⏳", _PENDING)
        self._orphan = CompactMetricCard("Pagos huérfanos", "🔗", _IDLE)
        self._dup = CompactMetricCard("Posibles duplicados", "⚠️", _IDLE)

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
