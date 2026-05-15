"""Theme-aware charts for the Dashboard tab using PySide6.QtCharts.

Four widgets:
  - RevenueByMonthChart     — bar series, X = day in window, Y = $
  - OccupancyByClassChart   — horizontal bars, X = % occupancy, Y = class
  - NewMembersChart         — line series, X = day, Y = count
  - MembershipDistributionChart — donut, slices = active plans

Each chart respects the active ``QPalette`` for background/axis colors so it
matches light/dark themes consistently with the rest of the app. Accents
follow the same palette as the cards in compact_metric_card.py.

Data shape coming from the GraphQL ``dashboardMetrics`` payload:
  revenueByDay / newMembersByDay: list[{day, count, total}]   (day = ISO datetime)
  occupancyByClass:               list[{className, capacity, reserved, occupancyPct}]
  membershipDistribution:         list[{planId, planName, count, total}]
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QDateTimeAxis,
    QHorizontalBarSeries,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, QMargins, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget


# Accent palette — mirrors compact_metric_card / payments_metrics_panel.
_ACCENT_INCOME = "#2ecc71"
_ACCENT_COUNT = "#3498db"
_ACCENT_AVG = "#1abc9c"
_ACCENT_PENDING = "#f39c12"
_ACCENT_NEUTRAL = "#9b59b6"
_PIE_PALETTE = [
    "#2ecc71", "#3498db", "#9b59b6", "#f39c12", "#1abc9c",
    "#e67e22", "#e74c3c", "#34495e", "#16a085", "#2980b9",
]
_GRID_GRAY = "#7f8c8d"


def _parse_iso_day(value: Any) -> Optional[datetime]:
    """Parse the ISO datetime returned by the backend's date_trunc('day', ...)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class _BaseChartView(QChartView):
    """Common helper: empty-state placeholder + palette-aware styling."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chart = QChart()
        self._chart.setTitle(title)
        self._chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self._chart.legend().setVisible(False)
        self._chart.setMargins(QMargins(4, 4, 4, 4))
        self._chart.layout().setContentsMargins(0, 0, 0, 0)
        self.setChart(self._chart)
        self._apply_theme()
        self._show_empty_state()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self) -> None:
        palette = self.palette()
        bg = palette.color(QPalette.ColorRole.AlternateBase)
        text = palette.color(QPalette.ColorRole.Text)

        self._chart.setBackgroundBrush(QBrush(bg))
        self._chart.setBackgroundPen(QPen(palette.color(QPalette.ColorRole.Mid)))
        self._chart.setPlotAreaBackgroundBrush(QBrush(bg))
        self._chart.setPlotAreaBackgroundVisible(True)

        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        self._chart.setTitleFont(title_font)
        self._chart.setTitleBrush(QBrush(text))

    def _styled_axis_value(self, label_format: str = "%.0f") -> QValueAxis:
        axis = QValueAxis()
        axis.setLabelFormat(label_format)
        text = self.palette().color(QPalette.ColorRole.Text)
        axis.setLabelsBrush(QBrush(text))
        axis.setTitleBrush(QBrush(text))
        axis.setLinePen(QPen(QColor(_GRID_GRAY)))
        axis.setGridLinePen(QPen(QColor(_GRID_GRAY), 1, Qt.PenStyle.DotLine))
        return axis

    def _styled_axis_category(self) -> QBarCategoryAxis:
        axis = QBarCategoryAxis()
        text = self.palette().color(QPalette.ColorRole.Text)
        axis.setLabelsBrush(QBrush(text))
        axis.setLinePen(QPen(QColor(_GRID_GRAY)))
        axis.setGridLinePen(QPen(QColor(_GRID_GRAY), 1, Qt.PenStyle.DotLine))
        return axis

    def _styled_axis_datetime(self) -> QDateTimeAxis:
        axis = QDateTimeAxis()
        axis.setFormat("dd MMM")
        text = self.palette().color(QPalette.ColorRole.Text)
        axis.setLabelsBrush(QBrush(text))
        axis.setLinePen(QPen(QColor(_GRID_GRAY)))
        axis.setGridLinePen(QPen(QColor(_GRID_GRAY), 1, Qt.PenStyle.DotLine))
        return axis

    # ------------------------------------------------------------------ state

    def _show_empty_state(self) -> None:
        """Replace the chart contents with a 'sin datos' message."""
        for s in list(self._chart.series()):
            self._chart.removeSeries(s)
        for a in list(self._chart.axes()):
            self._chart.removeAxis(a)
        # Use chart title as the only label; cleanest in QtCharts.
        existing_title = self._chart.title()
        if "(sin datos)" not in existing_title:
            self._chart.setTitle(f"{existing_title.replace(' (sin datos)', '')} (sin datos)")

    def _restore_title(self, base_title: str) -> None:
        self._chart.setTitle(base_title)


# --------------------------------------------------------------------------- #
# Revenue by day                                                              #
# --------------------------------------------------------------------------- #


class RevenueByMonthChart(_BaseChartView):
    """Daily revenue bars over the selected window."""

    _BASE_TITLE = "Ingresos por Día"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(self._BASE_TITLE, parent)

    def set_data(self, series: List[Dict[str, Any]]) -> None:
        # Reset chart
        for s in list(self._chart.series()):
            self._chart.removeSeries(s)
        for a in list(self._chart.axes()):
            self._chart.removeAxis(a)

        points = []
        for p in series or []:
            day = _parse_iso_day(p.get("day"))
            total = float(p.get("total") or 0)
            if day is None:
                continue
            points.append((day, total))

        if not points:
            self._show_empty_state()
            return

        self._restore_title(self._BASE_TITLE)

        bar_set = QBarSet("Ingresos")
        bar_set.setColor(QColor(_ACCENT_INCOME))
        bar_set.setBorderColor(QColor(_ACCENT_INCOME))
        categories: List[str] = []
        max_value = 0.0
        for day, total in points:
            bar_set.append(total)
            categories.append(day.strftime("%d %b"))
            max_value = max(max_value, total)

        bar_series = QBarSeries()
        bar_series.append(bar_set)
        self._chart.addSeries(bar_series)

        axis_x = self._styled_axis_category()
        axis_x.append(categories)
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        bar_series.attachAxis(axis_x)

        axis_y = self._styled_axis_value("$%,.0f")
        axis_y.setRange(0, max(max_value * 1.15, 1))
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        bar_series.attachAxis(axis_y)


# --------------------------------------------------------------------------- #
# Occupancy by class                                                          #
# --------------------------------------------------------------------------- #


class OccupancyByClassChart(_BaseChartView):
    """Horizontal % bars, one per class type."""

    _BASE_TITLE = "Ocupación por Clase"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(self._BASE_TITLE, parent)

    def set_data(self, buckets: List[Dict[str, Any]]) -> None:
        for s in list(self._chart.series()):
            self._chart.removeSeries(s)
        for a in list(self._chart.axes()):
            self._chart.removeAxis(a)

        items = [b for b in (buckets or []) if (b.get("className") and (b.get("capacity") or 0) > 0)]
        if not items:
            self._show_empty_state()
            return

        self._restore_title(self._BASE_TITLE)

        bar_set = QBarSet("Ocupación")
        bar_set.setColor(QColor(_ACCENT_AVG))
        bar_set.setBorderColor(QColor(_ACCENT_AVG))
        categories: List[str] = []
        for b in items:
            bar_set.append(float(b.get("occupancyPct") or 0))
            categories.append(str(b.get("className")))

        bar_series = QHorizontalBarSeries()
        bar_series.append(bar_set)
        self._chart.addSeries(bar_series)

        axis_y = self._styled_axis_category()
        axis_y.append(categories)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        bar_series.attachAxis(axis_y)

        axis_x = self._styled_axis_value("%.0f%%")
        axis_x.setRange(0, 100)
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        bar_series.attachAxis(axis_x)


# --------------------------------------------------------------------------- #
# New members over time                                                       #
# --------------------------------------------------------------------------- #


class NewMembersChart(_BaseChartView):
    """Daily line: new members per day in the window."""

    _BASE_TITLE = "Nuevos Socios"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(self._BASE_TITLE, parent)

    def set_data(self, series: List[Dict[str, Any]]) -> None:
        for s in list(self._chart.series()):
            self._chart.removeSeries(s)
        for a in list(self._chart.axes()):
            self._chart.removeAxis(a)

        line = QLineSeries()
        pen = QPen(QColor(_ACCENT_COUNT))
        pen.setWidth(2)
        line.setPen(pen)

        max_value = 0
        first_day: Optional[datetime] = None
        last_day: Optional[datetime] = None
        for p in series or []:
            day = _parse_iso_day(p.get("day"))
            count = int(p.get("count") or 0)
            if day is None:
                continue
            qdt = QDateTime.fromString(day.strftime("%Y-%m-%dT%H:%M:%S"), Qt.DateFormat.ISODate)
            line.append(qdt.toMSecsSinceEpoch(), float(count))
            max_value = max(max_value, count)
            if first_day is None or day < first_day:
                first_day = day
            if last_day is None or day > last_day:
                last_day = day

        if line.count() == 0:
            self._show_empty_state()
            return

        self._restore_title(self._BASE_TITLE)
        self._chart.addSeries(line)

        axis_x = self._styled_axis_datetime()
        if first_day and last_day:
            axis_x.setRange(
                QDateTime.fromString(
                    first_day.strftime("%Y-%m-%dT%H:%M:%S"), Qt.DateFormat.ISODate
                ),
                QDateTime.fromString(
                    last_day.strftime("%Y-%m-%dT%H:%M:%S"), Qt.DateFormat.ISODate
                ),
            )
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        line.attachAxis(axis_x)

        axis_y = self._styled_axis_value("%.0f")
        axis_y.setRange(0, max(max_value * 1.2, 1))
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        line.attachAxis(axis_y)


# --------------------------------------------------------------------------- #
# Membership distribution                                                     #
# --------------------------------------------------------------------------- #


class MembershipDistributionChart(_BaseChartView):
    """Donut: count of active subscriptions per plan."""

    _BASE_TITLE = "Tipos de Membresía"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(self._BASE_TITLE, parent)
        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self._chart.legend().setLabelBrush(
            QBrush(self.palette().color(QPalette.ColorRole.Text))
        )

    def set_data(self, buckets: List[Dict[str, Any]]) -> None:
        for s in list(self._chart.series()):
            self._chart.removeSeries(s)

        items = [b for b in (buckets or []) if (b.get("count") or 0) > 0]
        if not items:
            self._show_empty_state()
            return

        self._restore_title(self._BASE_TITLE)

        pie = QPieSeries()
        pie.setHoleSize(0.45)  # donut

        for i, b in enumerate(items):
            label = b.get("planName") or f"Plan {b.get('planId')}"
            count = int(b.get("count") or 0)
            slice_ = pie.append(f"{label} ({count})", count)
            color = QColor(_PIE_PALETTE[i % len(_PIE_PALETTE)])
            slice_.setBrush(QBrush(color))
            slice_.setBorderColor(self.palette().color(QPalette.ColorRole.AlternateBase))
            slice_.setBorderWidth(2)
            slice_.setLabelVisible(False)

        self._chart.addSeries(pie)
