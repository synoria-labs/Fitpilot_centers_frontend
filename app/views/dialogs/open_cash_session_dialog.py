"""Dialog to open the caja with an initial float (fondo inicial)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)


class OpenCashSessionDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Abrir caja")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Abre la caja con el efectivo inicial en el cajón."))

        form = QFormLayout()
        self.float_input = QDoubleSpinBox()
        self.float_input.setMaximum(1_000_000)
        self.float_input.setDecimals(2)
        self.float_input.setPrefix("$ ")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Opcional")
        form.addRow("Fondo inicial:", self.float_input)
        form.addRow("Notas:", self.notes_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Abrir caja")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, Any]:
        return {
            "opening_float": float(self.float_input.value()),
            "notes": self.notes_input.text().strip() or None,
        }
