"""Dashboard tab with real KPIs (cards) + 4 charts.

Cards reuse the shared :class:`CompactMetricCard` so the visual language stays
consistent with the Finanzas tab. Period selector uses the same ``FilterPreset``
enum as Finanzas so semantics match across the app.

Stock vs flow KPI distinction:
  - Stock cards (Socios Totales, Socios Activos, Ocupación) keep their label
    constant regardless of period; the underlying value still respects the
    window via ``end_date`` snapshot semantics on the backend.
  - Flow cards (Ingresos, Reservas, Nuevos Socios) adapt their label to the
    selected period (``Ingresos del Mes`` vs ``Ingresos de Hoy``, etc.).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...controllers.dashboard_controller import DashboardController
from ...core import container, get_logger
from ...models.payment_filters import PRESET_LABELS, FilterPreset
from ..widgets.compact_metric_card import CompactMetricCard
from ..widgets.dashboard_charts import (
    MembershipDistributionChart,
    NewMembersChart,
    OccupancyByClassChart,
    RevenueByMonthChart,
)

logger = get_logger(__name__)


# Card accent palette (mirrors Finanzas for consistency)
_INCOME = "#2ecc71"
_COUNT = "#3498db"
_AVG = "#1abc9c"
_PENDING = "#f39c12"
_ALERT = "#e74c3c"
_NEUTRAL = "#9b59b6"

# Period presets exposed to the user. We keep the dashboard short list:
# the granular Finanzas presets exist but are overkill for a dashboard.
_DASHBOARD_PRESETS: list[FilterPreset] = [
    FilterPreset.TODAY,
    FilterPreset.THIS_WEEK,
    FilterPreset.THIS_MONTH,
    FilterPreset.LAST_MONTH,
    FilterPreset.THIS_YEAR,
]

# Per-preset label suffix for flow cards.
_FLOW_LABEL_SUFFIX: Dict[FilterPreset, str] = {
    FilterPreset.TODAY: "de Hoy",
    FilterPreset.THIS_WEEK: "de la Semana",
    FilterPreset.THIS_MONTH: "del Mes",
    FilterPreset.LAST_MONTH: "del Mes Anterior",
    FilterPreset.THIS_YEAR: "del Año",
}


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


def _percent(value: float | int | None) -> str:
    if value is None:
        return "0%"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0%"


def _sales_plan_name(bucket: Optional[Dict[str, Any]]) -> str:
    if not bucket or not bucket.get("count"):
        return "Sin ventas"
    return str(bucket.get("planName") or f"Plan {bucket.get('planId')}")


def _sales_detail(bucket: Optional[Dict[str, Any]]) -> Optional[str]:
    if not bucket or not bucket.get("count"):
        return None
    return f"{_count(bucket.get('count'))} ventas · {_money(bucket.get('total'))}"


class DashboardTab(QWidget):
    """Dashboard with 8 real KPI cards + 4 charts + period selector."""

    refresh_requested = Signal()
    export_requested = Signal(str)

    def __init__(self):
        super().__init__()

        dashboard_service = container.get("dashboard_service")
        self.controller = DashboardController(dashboard_service, self)

        self._setup_ui()
        self._connect_signals()

        # Auto-refresh every 60 seconds
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.controller.load_metrics)
        self._refresh_timer.start(60000)

        # Initial load
        self.controller.load_metrics()

    # ------------------------------------------------------------------ ui

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header: title + period combo + actions
        header_layout = QHBoxLayout()
        title = QLabel("Dashboard - Métricas Principales")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        header_layout.addWidget(QLabel("Período:"))
        self.period_combo = QComboBox()
        for preset in _DASHBOARD_PRESETS:
            self.period_combo.addItem(PRESET_LABELS[preset], preset)
        # Default index matches controller's default (THIS_MONTH)
        default_idx = _DASHBOARD_PRESETS.index(FilterPreset.THIS_MONTH)
        self.period_combo.setCurrentIndex(default_idx)
        header_layout.addWidget(self.period_combo)

        self.refresh_btn = QPushButton("🔄 Actualizar")
        self.refresh_btn.setObjectName("actionButton")
        header_layout.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("📥 Exportar")
        self.export_btn.setObjectName("actionButton")
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Cards: 4-column grid, 2 rows
        cards_grid = QGridLayout()
        cards_grid.setSpacing(8)

        self.card_total_members = CompactMetricCard("Socios Totales", "👥", _COUNT)
        self.card_active_members = CompactMetricCard("Socios Activos", "✅", _INCOME)
        self.card_top_membership_all_time = CompactMetricCard(
            "Top Membresía Histórica", "#", _NEUTRAL
        )
        self.card_top_membership_period = CompactMetricCard(
            "Top Membresía del Mes", "#", _COUNT
        )
        self.card_revenue = CompactMetricCard("Ingresos del Mes", "💰", _PENDING)
        self.card_reservations = CompactMetricCard("Reservas del Mes", "📅", _ALERT)
        self.card_occupancy = CompactMetricCard("Ocupación Promedio", "📊", _NEUTRAL)
        self.card_new_members = CompactMetricCard("Nuevos Socios del Mes", "🆕", _AVG)

        cards_grid.addWidget(self.card_total_members, 0, 0)
        cards_grid.addWidget(self.card_active_members, 0, 1)
        cards_grid.addWidget(self.card_top_membership_all_time, 0, 2)
        cards_grid.addWidget(self.card_top_membership_period, 0, 3)
        cards_grid.addWidget(self.card_revenue, 1, 0)
        cards_grid.addWidget(self.card_reservations, 1, 1)
        cards_grid.addWidget(self.card_occupancy, 1, 2)
        cards_grid.addWidget(self.card_new_members, 1, 3)

        layout.addLayout(cards_grid)

        # Charts
        charts_label = QLabel("Gráficas")
        charts_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(charts_label)

        charts_grid = QGridLayout()
        charts_grid.setSpacing(8)

        self.chart_revenue = RevenueByMonthChart()
        self.chart_occupancy = OccupancyByClassChart()
        self.chart_new_members = NewMembersChart()
        self.chart_membership = MembershipDistributionChart()

        charts_grid.addWidget(self.chart_revenue, 0, 0)
        charts_grid.addWidget(self.chart_occupancy, 0, 1)
        charts_grid.addWidget(self.chart_new_members, 1, 0)
        charts_grid.addWidget(self.chart_membership, 1, 1)

        layout.addLayout(charts_grid, stretch=1)

    def _connect_signals(self) -> None:
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.refresh_btn.clicked.connect(self.controller.load_metrics)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit("pdf"))

        self.controller.metrics_changed.connect(self._on_metrics)
        self.controller.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------ slots

    @Slot(int)
    def _on_period_changed(self, index: int) -> None:
        if index < 0:
            return
        preset = self.period_combo.itemData(index)
        if not isinstance(preset, FilterPreset):
            preset = FilterPreset(preset)
        self._adapt_flow_card_labels(preset)
        self.controller.set_period(preset)

    def _adapt_flow_card_labels(self, preset: FilterPreset) -> None:
        suffix = _FLOW_LABEL_SUFFIX.get(preset, "del Período")
        self.card_revenue.configure(icon="💰", title=f"Ingresos {suffix}")
        self.card_reservations.configure(icon="📅", title=f"Reservas {suffix}")
        self.card_new_members.configure(icon="🆕", title=f"Nuevos Socios {suffix}")
        self.card_top_membership_period.configure(
            icon="#", title=f"Top Membresía {suffix}"
        )

    @Slot(object)
    def _on_metrics(self, metrics: Optional[Dict[str, Any]]) -> None:
        if not metrics:
            self._clear_cards()
            return

        # Stock KPIs
        self.card_total_members.set_value(_count(metrics.get("totalMembers")))
        self.card_total_members.set_trend_delta(
            metrics.get("totalMembers"), metrics.get("totalMembersPrev")
        )

        self.card_active_members.set_value(_count(metrics.get("activeMembers")))
        self.card_active_members.set_trend_delta(
            metrics.get("activeMembers"), metrics.get("activeMembersPrev")
        )

        top_all_time = metrics.get("topMembershipSalesAllTime")
        self.card_top_membership_all_time.set_value(
            _sales_plan_name(top_all_time),
            _sales_detail(top_all_time),
        )

        top_period = metrics.get("topMembershipSalesPeriod")
        self.card_top_membership_period.set_value(
            _sales_plan_name(top_period),
            _sales_detail(top_period),
        )

        self.card_occupancy.set_value(_percent(metrics.get("avgOccupancy")))
        self.card_occupancy.set_trend_delta(
            metrics.get("avgOccupancy"), metrics.get("avgOccupancyPrev")
        )

        # Flow KPIs
        self.card_revenue.set_value(_money(metrics.get("periodRevenue")))
        self.card_revenue.set_trend_delta(
            metrics.get("periodRevenue"), metrics.get("revenuePrev")
        )

        self.card_reservations.set_value(_count(metrics.get("periodReservations")))
        self.card_reservations.set_trend_delta(
            metrics.get("periodReservations"), metrics.get("reservationsPrev")
        )

        self.card_new_members.set_value(_count(metrics.get("newMembers")))
        self.card_new_members.set_trend_delta(
            metrics.get("newMembers"), metrics.get("newMembersPrev")
        )

        # Charts
        self.chart_revenue.set_data(metrics.get("revenueByDay") or [])
        self.chart_occupancy.set_data(metrics.get("occupancyByClass") or [])
        self.chart_new_members.set_data(metrics.get("newMembersByDay") or [])
        self.chart_membership.set_data(metrics.get("membershipDistribution") or [])

    def _clear_cards(self) -> None:
        for card in (
            self.card_total_members,
            self.card_active_members,
            self.card_top_membership_all_time,
            self.card_top_membership_period,
            self.card_revenue,
            self.card_reservations,
            self.card_occupancy,
            self.card_new_members,
        ):
            card.set_value("—")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        logger.warning("Dashboard error: %s", message)

    # ------------------------------------------------------------------ legacy

    def load_metrics(self) -> None:
        """Backwards-compat shim — older callers may invoke this."""
        self.controller.load_metrics()
