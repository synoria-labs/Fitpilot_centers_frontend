"""Dialog to add a product line to a POS sale."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QSpinBox, QVBoxLayout,
)

from ...utils.qt_helpers import get_combo_selected_data, populate_combo_safely


class PosProductLineDialog(QDialog):
    def __init__(self, products: List[Dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Agregar producto")
        self.setMinimumWidth(380)
        self._products = [p for p in (products or []) if p.get("isActive", True)]

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.product_combo = QComboBox()
        populate_combo_safely(
            self.product_combo, self._products,
            lambda p: f"{p.get('name')} (${float(p.get('price') or 0):,.2f})",
            lambda p: p,
        )
        self.product_combo.currentIndexChanged.connect(self._on_product_changed)

        self.qty_input = QSpinBox()
        self.qty_input.setMinimum(1)
        self.qty_input.setMaximum(1_000)
        self.qty_input.valueChanged.connect(self._update_total)

        self.price_input = QDoubleSpinBox()
        self.price_input.setMaximum(1_000_000)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("$ ")
        self.price_input.valueChanged.connect(self._update_total)

        self.stock_label = QLabel("")
        self.stock_label.setStyleSheet("color: #888;")
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("font-weight: bold;")

        form.addRow("Producto:", self.product_combo)
        form.addRow("Cantidad:", self.qty_input)
        form.addRow("Precio unitario:", self.price_input)
        form.addRow("", self.stock_label)
        form.addRow("Total:", self.total_label)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Agregar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_product_changed()

    def _selected(self) -> Dict[str, Any]:
        return get_combo_selected_data(self.product_combo) or {}

    def _on_product_changed(self) -> None:
        p = self._selected()
        self.price_input.setValue(float(p.get("price") or 0))
        if p.get("trackStock"):
            stock = p.get("stockQty")
            self.stock_label.setText(f"Stock disponible: {stock if stock is not None else 0}")
            self.qty_input.setMaximum(max(int(stock or 0), 1))
        else:
            self.stock_label.setText("Sin control de inventario")
            self.qty_input.setMaximum(1_000)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(p))
        self._update_total()

    def _update_total(self) -> None:
        total = float(self.price_input.value()) * int(self.qty_input.value())
        self.total_label.setText(f"${total:,.2f}")

    def get_line(self) -> Dict[str, Any]:
        p = self._selected()
        qty = int(self.qty_input.value())
        unit_price = float(self.price_input.value())
        return {
            "line_type": "product",
            "product_id": int(p.get("id")),
            "quantity": qty,
            "unit_price": unit_price,
            "description": f"{qty} x {p.get('name')}" if qty > 1 else p.get("name"),
        }
