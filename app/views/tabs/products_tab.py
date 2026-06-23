"""Productos tab: catalog + inventory CRUD (gated by manage_products)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core import container, get_logger
from ...controllers.products_controller import ProductsController
from ...utils.dialog_helpers import show_error, show_info
from ..dialogs.product_dialog import ProductDialog

logger = get_logger(__name__)


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


class ProductsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._service = container.get("products_service")
        self.controller = ProductsController(self._service, self)
        self._products: List[Dict[str, Any]] = []
        self._can_manage = self._resolve_can_manage()

        self._build_ui()
        self._connect()
        self.controller.load_products()

    def _resolve_can_manage(self) -> bool:
        try:
            auth_service = container.get("auth_service")
            return bool(auth_service.has_capability("manage_products"))
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Productos")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.new_btn = QPushButton("+ Nuevo producto")
        self.new_btn.clicked.connect(self._on_new)
        self.edit_btn = QPushButton("Editar")
        self.edit_btn.clicked.connect(self._on_edit)
        self.toggle_btn = QPushButton("Activar/Desactivar")
        self.toggle_btn.clicked.connect(self._on_toggle)
        for b in (self.new_btn, self.edit_btn, self.toggle_btn):
            b.setEnabled(self._can_manage)
            header.addWidget(b)
        root.addLayout(header)

        if not self._can_manage:
            note = QLabel("Solo lectura: no tienes el permiso para gestionar productos.")
            note.setStyleSheet("color: #e67e22;")
            root.addWidget(note)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre", "SKU", "Precio", "Stock", "Activo"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(lambda *_: self._on_edit())
        root.addWidget(self.table, 1)

    def _connect(self) -> None:
        self.controller.products_loaded.connect(self._on_loaded)
        self.controller.action_completed.connect(self._on_action)
        self.controller.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_loaded(self, products: List[Dict[str, Any]]) -> None:
        self._products = products or []
        self.table.setRowCount(len(self._products))
        for i, p in enumerate(self._products):
            stock = p.get("stockQty") if p.get("trackStock") else "—"
            values = [
                str(p.get("id")),
                p.get("name", ""),
                p.get("sku") or "—",
                _money(p.get("price")),
                str(stock),
                "Sí" if p.get("isActive") else "No",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in (3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, col, item)

    @Slot(str, str)
    def _on_action(self, title: str, message: str) -> None:
        show_info(self, message, title=title)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        show_error(self, error, title="Productos")

    # ------------------------------------------------------------------ actions
    def _selected_product(self) -> Optional[Dict[str, Any]]:
        row = self.table.currentRow()
        if 0 <= row < len(self._products):
            return self._products[row]
        return None

    def _on_new(self) -> None:
        dialog = ProductDialog(None, self)
        if dialog.exec():
            self.controller.create_product(dialog.get_data())

    def _on_edit(self) -> None:
        product = self._selected_product()
        if not product:
            return
        dialog = ProductDialog(product, self)
        if dialog.exec():
            self.controller.update_product(int(product["id"]), dialog.get_data())

    def _on_toggle(self) -> None:
        product = self._selected_product()
        if not product:
            return
        self.controller.set_product_active(int(product["id"]), not bool(product.get("isActive")))
