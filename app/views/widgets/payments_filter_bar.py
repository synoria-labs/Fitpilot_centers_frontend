"""Filter bar for the Finances tab.

Combines:
  - Temporal preset combo (Hoy, Esta semana, Este mes, ...)
  - Custom date range (QDateEdit start + end), enabled only when preset = Personalizado
  - Status combo (Todos / COMPLETED / PENDING / FAILED / REFUNDED)
  - Method combo (Todos / cash / card / transfer / other)
  - Debounced search QLineEdit

Emits ``filters_changed(PaymentFilters)`` whenever the resolved filter set
changes. Search input is debounced 400 ms; everything else fires immediately.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from ...models.payment_filters import (
    PRESET_LABELS,
    FilterPreset,
    PaymentFilters,
    compute_preset_range,
)


_STATUS_OPTIONS: list[tuple[str, Optional[str]]] = [
    ("Todos", None),
    ("Completados", "COMPLETED"),
    ("Pendientes", "PENDING"),
    ("Fallidos", "FAILED"),
    ("Reembolsados", "REFUNDED"),
]

_METHOD_OPTIONS: list[tuple[str, Optional[str]]] = [
    ("Todos", None),
    ("Efectivo", "cash"),
    ("Tarjeta", "card"),
    ("Transferencia", "transfer"),
    ("Otro", "other"),
]


class PaymentsFilterBar(QWidget):
    filters_changed = Signal(object)  # PaymentFilters

    def __init__(
        self,
        initial: Optional[PaymentFilters] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._filters: PaymentFilters = initial or PaymentFilters.from_preset(
            FilterPreset.THIS_MONTH
        )
        # Suppress emit-on-set during programmatic updates
        self._suppress_signals: bool = False

        self._build_ui()
        self._sync_from_filters(self._filters)

    # ----------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Periodo:"))
        self._preset_combo = QComboBox()
        for preset in FilterPreset:
            self._preset_combo.addItem(PRESET_LABELS[preset], preset)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self._preset_combo)

        self._start_edit = QDateEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_edit.dateChanged.connect(self._on_date_changed)
        layout.addWidget(self._start_edit)

        layout.addWidget(QLabel("a"))

        self._end_edit = QDateEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_edit.dateChanged.connect(self._on_date_changed)
        layout.addWidget(self._end_edit)

        layout.addSpacing(12)

        layout.addWidget(QLabel("Estado:"))
        self._status_combo = QComboBox()
        for label, value in _STATUS_OPTIONS:
            self._status_combo.addItem(label, value)
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        layout.addWidget(self._status_combo)

        layout.addWidget(QLabel("Método:"))
        self._method_combo = QComboBox()
        for label, value in _METHOD_OPTIONS:
            self._method_combo.addItem(label, value)
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        layout.addWidget(self._method_combo)

        layout.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Buscar por nombre, método o estado...")
        self._search_edit.setFixedWidth(240)
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self._search_edit)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self._emit_search)

    # ----------------------------------------------------------------- helpers

    def filters(self) -> PaymentFilters:
        return self._filters

    def _sync_from_filters(self, filters: PaymentFilters) -> None:
        """Push the filter state back into the widgets without re-emitting."""
        self._suppress_signals = True
        try:
            preset_index = self._preset_combo.findData(filters.preset)
            if preset_index >= 0:
                self._preset_combo.setCurrentIndex(preset_index)

            start, end = filters.start_date, filters.end_date
            if start is not None:
                self._start_edit.setDate(QDate(start.year, start.month, start.day))
            if end is not None:
                self._end_edit.setDate(QDate(end.year, end.month, end.day))

            custom = filters.preset is FilterPreset.CUSTOM
            self._start_edit.setEnabled(custom)
            self._end_edit.setEnabled(custom)

            status_index = self._status_combo.findData(filters.status)
            if status_index >= 0:
                self._status_combo.setCurrentIndex(status_index)

            method_index = self._method_combo.findData(filters.method)
            if method_index >= 0:
                self._method_combo.setCurrentIndex(method_index)

            self._search_edit.setText(filters.search or "")
        finally:
            self._suppress_signals = False

    def _emit(self, new_filters: PaymentFilters) -> None:
        if self._suppress_signals or new_filters == self._filters:
            return
        self._filters = new_filters
        self.filters_changed.emit(new_filters)

    # ----------------------------------------------------------------- slots

    def _on_preset_changed(self, _index: int) -> None:
        if self._suppress_signals:
            return
        # Qt stores str-Enum as plain str via QVariant; coerce back.
        preset = FilterPreset(self._preset_combo.currentData())
        if preset is FilterPreset.CUSTOM:
            # Keep the current dates as the seed for the custom range.
            self._start_edit.setEnabled(True)
            self._end_edit.setEnabled(True)
            new_filters = self._filters.with_custom_range(
                self._qdate_to_dt(self._start_edit.date(), end=False),
                self._qdate_to_dt(self._end_edit.date(), end=True),
            )
        else:
            self._start_edit.setEnabled(False)
            self._end_edit.setEnabled(False)
            start, end = compute_preset_range(preset)
            new_filters = self._filters.with_preset(preset)
            # Re-sync date edits to reflect the resolved range
            self._suppress_signals = True
            try:
                if start is not None:
                    self._start_edit.setDate(QDate(start.year, start.month, start.day))
                if end is not None:
                    self._end_edit.setDate(QDate(end.year, end.month, end.day))
            finally:
                self._suppress_signals = False
        self._emit(new_filters)

    def _on_date_changed(self, _date: QDate) -> None:
        if self._suppress_signals:
            return
        # Only meaningful in CUSTOM mode; for presets the dates are derived.
        if FilterPreset(self._preset_combo.currentData()) is not FilterPreset.CUSTOM:
            return
        start = self._qdate_to_dt(self._start_edit.date(), end=False)
        end = self._qdate_to_dt(self._end_edit.date(), end=True)
        if end < start:
            # Defensive: ignore inverted ranges, the user is mid-edit
            return
        self._emit(self._filters.with_custom_range(start, end))

    def _on_status_changed(self, _index: int) -> None:
        if self._suppress_signals:
            return
        status = self._status_combo.currentData()
        self._emit(self._filters.with_status(status))

    def _on_method_changed(self, _index: int) -> None:
        if self._suppress_signals:
            return
        method = self._method_combo.currentData()
        self._emit(self._filters.with_method(method))

    def _on_search_text_changed(self, _text: str) -> None:
        if self._suppress_signals:
            return
        self._search_timer.start()

    def _emit_search(self) -> None:
        text = self._search_edit.text().strip() or None
        self._emit(self._filters.with_search(text))

    @staticmethod
    def _qdate_to_dt(qd: QDate, *, end: bool) -> datetime:
        """Convert a QDate to a tz-aware datetime (local TZ) at start- or end-of-day."""
        py_date = qd.toPython()  # datetime.date
        wall = time.max if end else time.min
        return datetime.combine(py_date, wall).astimezone()
