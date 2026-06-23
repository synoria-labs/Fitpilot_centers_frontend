"""Corte de caja dialog: shows the expected cash, captures the counted amount."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QVBoxLayout,
)

from ...utils.qt_helpers import PAYMENT_METHOD_OPTIONS

_METHOD_LABELS = {value: label for label, value in PAYMENT_METHOD_OPTIONS}


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _method(value: Optional[str]) -> str:
    key = (value or "").strip().lower()
    return _METHOD_LABELS.get(key, (value or "").capitalize())


class CloseCashSessionDialog(QDialog):
    def __init__(self, report: Optional[Dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Corte de caja")
        self.setMinimumWidth(420)
        self._report = report or {}

        expected = self._report.get("computedExpectedCash")
        if expected is None:
            expected = self._report.get("expectedCash") or 0
        self._expected = float(expected or 0)

        layout = QVBoxLayout(self)
        title = QLabel("Resumen de la caja")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        summary = QFormLayout()
        summary.addRow("Fondo inicial:", QLabel(_money(self._report.get("openingFloat"))))
        summary.addRow("Ventas:", QLabel(
            f"{self._report.get('salesCount', 0)}  ({_money(self._report.get('salesTotal'))})"
        ))
        summary.addRow("Ventas en efectivo:", QLabel(_money(self._report.get("cashSalesTotal"))))
        summary.addRow("Ingresos efectivo:", QLabel(_money(self._report.get("cashIn"))))
        summary.addRow("Retiros efectivo:", QLabel(_money(self._report.get("cashOut"))))
        layout.addLayout(summary)

        # By-method breakdown
        for bucket in self._report.get("byMethod") or []:
            row = QLabel(f"  • {_method(bucket.get('method'))}: {_money(bucket.get('total'))} "
                         f"({bucket.get('count', 0)})")
            row.setStyleSheet("color: #888;")
            layout.addWidget(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        form = QFormLayout()
        self.expected_label = QLabel(_money(self._expected))
        self.expected_label.setStyleSheet("font-weight: bold;")
        self.counted_input = QDoubleSpinBox()
        self.counted_input.setMaximum(1_000_000)
        self.counted_input.setDecimals(2)
        self.counted_input.setPrefix("$ ")
        self.counted_input.setValue(self._expected)
        self.counted_input.valueChanged.connect(self._update_difference)
        self.difference_label = QLabel(_money(0))
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Notas del corte (opcional)")

        form.addRow("Efectivo esperado:", self.expected_label)
        form.addRow("Efectivo contado:", self.counted_input)
        form.addRow("Diferencia:", self.difference_label)
        form.addRow("Notas:", self.notes_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Cerrar caja")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_difference()

    def _update_difference(self) -> None:
        diff = float(self.counted_input.value()) - self._expected
        self.difference_label.setText(_money(diff))
        if abs(diff) < 0.01:
            color = "#2ecc71"
        elif diff < 0:
            color = "#e74c3c"
        else:
            color = "#f39c12"
        self.difference_label.setStyleSheet(f"font-weight: bold; color: {color};")

    def get_data(self) -> Dict[str, Any]:
        return {
            "counted_cash": float(self.counted_input.value()),
            "notes": self.notes_input.text().strip() or None,
        }
