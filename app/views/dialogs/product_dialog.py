"""Create/edit a catalog product."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit,
    QSpinBox, QVBoxLayout,
)


class ProductDialog(QDialog):
    def __init__(self, product: Optional[Dict[str, Any]] = None, parent=None) -> None:
        super().__init__(parent)
        self._product = product or {}
        self.setWindowTitle("Editar producto" if product else "Nuevo producto")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit(self._product.get("name", ""))
        self.sku_input = QLineEdit(self._product.get("sku") or "")
        self.price_input = QDoubleSpinBox()
        self.price_input.setMaximum(1_000_000)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("$ ")
        self.price_input.setValue(float(self._product.get("price") or 0))

        self.track_check = QCheckBox("Controlar inventario (stock)")
        self.track_check.setChecked(bool(self._product.get("trackStock")))
        self.track_check.stateChanged.connect(self._on_track_changed)

        self.stock_input = QSpinBox()
        self.stock_input.setMaximum(1_000_000)
        self.stock_input.setValue(int(self._product.get("stockQty") or 0))

        form.addRow("Nombre:", self.name_input)
        form.addRow("SKU:", self.sku_input)
        form.addRow("Precio:", self.price_input)
        form.addRow("", self.track_check)
        form.addRow("Stock:", self.stock_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._buttons = buttons
        layout.addWidget(buttons)

        self._on_track_changed()

    def _on_track_changed(self) -> None:
        self.stock_input.setEnabled(self.track_check.isChecked())

    def _on_accept(self) -> None:
        if not self.name_input.text().strip():
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        track = self.track_check.isChecked()
        return {
            "name": self.name_input.text().strip(),
            "sku": self.sku_input.text().strip() or None,
            "price": float(self.price_input.value()),
            "track_stock": track,
            "stock_qty": int(self.stock_input.value()) if track else None,
        }
