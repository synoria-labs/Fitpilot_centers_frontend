"""Dialog to register a manual cash movement (ingreso / retiro)."""
from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLineEdit, QRadioButton, QVBoxLayout, QWidget,
)


class CashMovementDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Movimiento de efectivo")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        direction_box = QWidget()
        direction_layout = QHBoxLayout(direction_box)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        self.in_radio = QRadioButton("Ingreso")
        self.out_radio = QRadioButton("Retiro")
        self.out_radio.setChecked(True)
        self._group = QButtonGroup(self)
        self._group.addButton(self.in_radio)
        self._group.addButton(self.out_radio)
        direction_layout.addWidget(self.in_radio)
        direction_layout.addWidget(self.out_radio)
        direction_layout.addStretch()

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setMaximum(1_000_000)
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("$ ")
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Motivo (opcional)")

        form.addRow("Tipo:", direction_box)
        form.addRow("Monto:", self.amount_input)
        form.addRow("Motivo:", self.reason_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Registrar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, Any]:
        return {
            "direction": "in" if self.in_radio.isChecked() else "out",
            "amount": float(self.amount_input.value()),
            "reason": self.reason_input.text().strip() or None,
        }
