"""Punto de Venta (POS) tab: checkout that reuses the enrollment/renewal flow."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core import container, get_logger
from ...controllers.pos_controller import PosController
from ...threads.authenticated_operations import start_authenticated_operation
from ...utils.dialog_helpers import show_error, show_info
from ...utils.qt_helpers import get_combo_selected_data, populate_payment_methods
from ..dialogs.pos_member_line_dialog import PosMembershipLineDialog
from ..dialogs.pos_product_line_dialog import PosProductLineDialog

logger = get_logger(__name__)


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


class PosTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pos_service = container.get("pos_service")
        self._members_service = container.get("members_service")
        self._memberships_service = container.get("memberships_service")
        self._cash_service = container.get("cash_register_service")
        self._products_service = container.get("products_service")
        self._printing = container.get("printing_service")
        self.controller = PosController(
            self._pos_service, self._members_service, self._memberships_service, self
        )

        self._plans: List[Any] = []
        self._products: List[Dict[str, Any]] = []
        self._lines: List[Dict[str, Any]] = []
        self._tenders: List[Dict[str, Any]] = []
        self._current_member: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._connect()
        self.controller.load_plans()
        self._load_products()
        self._refresh_caja_banner()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Punto de Venta")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.caja_banner = QLabel("")
        self.caja_banner.setStyleSheet("font-size: 13px;")
        header.addWidget(self.caja_banner)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_left_panel(), 3)
        body.addWidget(self._build_right_panel(), 2)
        root.addLayout(body, 1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Member search (for renewals / attaching the sale to a member)
        member_box = QGroupBox("Socio")
        member_layout = QVBoxLayout(member_box)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar socio por nombre, teléfono o email…")
        self.search_input.returnPressed.connect(self._on_search)
        search_btn = QPushButton("Buscar")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(search_btn)
        member_layout.addLayout(search_row)

        self.member_combo = QComboBox()
        self.member_combo.currentIndexChanged.connect(self._on_member_selected)
        member_layout.addWidget(self.member_combo)
        self.member_info = QLabel("Sin socio seleccionado.")
        self.member_info.setStyleSheet("color: #888;")
        member_layout.addWidget(self.member_info)
        layout.addWidget(member_box)

        # Add-line buttons
        add_row = QHBoxLayout()
        self.renew_btn = QPushButton("Renovar membresía")
        self.renew_btn.clicked.connect(self._on_add_renewal)
        self.renew_btn.setEnabled(False)
        self.new_btn = QPushButton("Alta nuevo socio")
        self.new_btn.clicked.connect(self._on_add_new)
        self.product_btn = QPushButton("Agregar producto")
        self.product_btn.clicked.connect(self._on_add_product)
        add_row.addWidget(self.renew_btn)
        add_row.addWidget(self.new_btn)
        add_row.addWidget(self.product_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # Cart
        self.cart_table = QTableWidget(0, 2)
        self.cart_table.setHorizontalHeaderLabels(["Concepto", "Importe"])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.cart_table, 1)

        remove_row = QHBoxLayout()
        remove_btn = QPushButton("Quitar concepto")
        remove_btn.clicked.connect(self._on_remove_line)
        remove_row.addStretch()
        remove_row.addWidget(remove_btn)
        layout.addLayout(remove_row)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        pay_box = QGroupBox("Pago")
        pay_layout = QVBoxLayout(pay_box)
        tender_row = QHBoxLayout()
        self.method_combo = QComboBox()
        populate_payment_methods(self.method_combo)
        self.tender_amount = QDoubleSpinBox()
        self.tender_amount.setMaximum(1_000_000)
        self.tender_amount.setDecimals(2)
        self.tender_amount.setPrefix("$ ")
        add_tender_btn = QPushButton("Agregar pago")
        add_tender_btn.clicked.connect(self._on_add_tender)
        tender_row.addWidget(self.method_combo)
        tender_row.addWidget(self.tender_amount)
        tender_row.addWidget(add_tender_btn)
        pay_layout.addLayout(tender_row)

        exact_btn = QPushButton("Pago exacto en efectivo")
        exact_btn.clicked.connect(self._on_exact_cash)
        pay_layout.addWidget(exact_btn)

        self.tender_table = QTableWidget(0, 2)
        self.tender_table.setHorizontalHeaderLabels(["Método", "Monto"])
        self.tender_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tender_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tender_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tender_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        pay_layout.addWidget(self.tender_table)

        remove_tender_btn = QPushButton("Quitar pago")
        remove_tender_btn.clicked.connect(self._on_remove_tender)
        pay_layout.addWidget(remove_tender_btn, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(pay_box, 1)

        # Totals
        totals = QFrame()
        totals.setStyleSheet("QFrame { background: rgba(255,255,255,0.04); border-radius: 8px; }")
        totals_layout = QVBoxLayout(totals)
        self.total_label = QLabel("Total: $0.00")
        self.total_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.paid_label = QLabel("Pagado: $0.00")
        self.change_label = QLabel("Cambio: $0.00")
        for lbl in (self.total_label, self.paid_label, self.change_label):
            totals_layout.addWidget(lbl)
        layout.addWidget(totals)

        self.print_check = QCheckBox("Imprimir ticket al cobrar")
        self.print_check.setChecked(True)
        layout.addWidget(self.print_check)

        action_row = QHBoxLayout()
        self.clear_btn = QPushButton("Limpiar")
        self.clear_btn.clicked.connect(self._reset_sale)
        self.charge_btn = QPushButton("Cobrar")
        self.charge_btn.setStyleSheet(
            "QPushButton { background: #67b6df; color: white; font-weight: bold; padding: 10px; border-radius: 6px; }"
        )
        self.charge_btn.clicked.connect(self._on_charge)
        action_row.addWidget(self.clear_btn)
        action_row.addWidget(self.charge_btn, 1)
        layout.addLayout(action_row)
        return panel

    def _connect(self) -> None:
        self.controller.plans_loaded.connect(self._on_plans_loaded)
        self.controller.members_loaded.connect(self._on_members_loaded)
        self.controller.sale_completed.connect(self._on_sale_completed)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading)

    # ------------------------------------------------------------------ caja banner
    def _refresh_caja_banner(self) -> None:
        def on_ok(session):
            if session:
                self.caja_banner.setText("🟢 Caja abierta")
                self.caja_banner.setStyleSheet("color: #2ecc71; font-size: 13px;")
            else:
                self.caja_banner.setText("⚪ Caja cerrada — abre la caja para cobrar en efectivo")
                self.caja_banner.setStyleSheet("color: #e67e22; font-size: 13px;")

        start_authenticated_operation(
            service=self._cash_service,
            method_name="get_open_cash_session",
            parent=self,
            on_success=on_ok,
            on_error=lambda err: logger.warning("No se pudo leer estado de caja: %s", err),
        )

    def _load_products(self) -> None:
        def on_ok(products):
            self._products = list(products or [])

        start_authenticated_operation(
            service=self._products_service,
            method_name="get_products",
            parent=self,
            on_success=on_ok,
            on_error=lambda err: logger.warning("No se pudieron cargar productos: %s", err),
            include_inactive=False,
        )

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_plans_loaded(self, plans: List[Any]) -> None:
        self._plans = plans or []

    @Slot(object)
    def _on_members_loaded(self, members: List[Any]) -> None:
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        self.member_combo.addItem("— Selecciona un socio —", None)
        for m in members:
            label = getattr(m, "full_name", None) or "Socio"
            am = getattr(m, "active_membership", None)
            if am and getattr(am, "plan_name", None):
                label = f"{label} · {am.plan_name}"
            self.member_combo.addItem(label, m)
        self.member_combo.blockSignals(False)
        if not members:
            show_info(self, "Sin resultados para la búsqueda.", title="Socios")

    @Slot(int)
    def _on_member_selected(self, _index: int) -> None:
        m = get_combo_selected_data(self.member_combo)
        if m is None:
            self._current_member = None
            self.member_info.setText("Sin socio seleccionado.")
            self.renew_btn.setEnabled(False)
            return
        self._current_member = {
            "id": getattr(m, "id", None),
            "full_name": getattr(m, "full_name", None),
            "email": getattr(m, "email", None),
            "phone_number": getattr(m, "phone_number", None),
        }
        am = getattr(m, "active_membership", None)
        if am and getattr(am, "plan_name", None):
            self.member_info.setText(
                f"Plan actual: {am.plan_name} · vence en {getattr(am, 'remaining_days', '—')} días"
            )
        else:
            self.member_info.setText("Sin membresía activa.")
        self.renew_btn.setEnabled(True)

    @Slot(object)
    def _on_sale_completed(self, sale: Optional[Dict[str, Any]]) -> None:
        if not sale:
            show_error(self, "La venta no devolvió datos.", title="POS")
            return
        if self.print_check.isChecked():
            try:
                self._printing.imprimir_ticket_venta(sale)
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo imprimir el ticket: %s", exc)
        show_info(self, f"Venta #{sale.get('id')} registrada por {_money(sale.get('total'))}.", title="Venta")
        self._reset_sale()
        self._refresh_caja_banner()

    @Slot(str)
    def _on_error(self, error: str) -> None:
        show_error(self, error, title="POS")

    @Slot(bool)
    def _on_loading(self, loading: bool) -> None:
        self.charge_btn.setEnabled(not loading)

    # ------------------------------------------------------------------ member search
    def _on_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        self.controller.search_members(query)

    # ------------------------------------------------------------------ lines
    def _on_add_renewal(self) -> None:
        if not self._current_member:
            return
        dialog = PosMembershipLineDialog("renewal", self._plans, self._current_member, self)
        if dialog.exec():
            self._add_line(dialog.get_line())

    def _on_add_new(self) -> None:
        dialog = PosMembershipLineDialog("new", self._plans, None, self)
        if dialog.exec():
            self._add_line(dialog.get_line())

    def _on_add_product(self) -> None:
        if not self._products:
            show_info(self, "No hay productos en el catálogo. Créalos en la pestaña Productos.", title="Productos")
            return
        dialog = PosProductLineDialog(self._products, self)
        if dialog.exec():
            self._add_line(dialog.get_line())

    def _add_line(self, line: Dict[str, Any]) -> None:
        self._lines.append(line)
        self._render_cart()
        self._recompute()

    def _on_remove_line(self) -> None:
        row = self.cart_table.currentRow()
        if 0 <= row < len(self._lines):
            self._lines.pop(row)
            self._render_cart()
            self._recompute()

    @staticmethod
    def _line_total(line: Dict[str, Any]) -> float:
        unit = float(line.get("unit_price") or 0)
        qty = int(line.get("quantity") or 1)
        discount = float(line.get("discount") or 0)
        return unit * qty - discount

    def _render_cart(self) -> None:
        self.cart_table.setRowCount(len(self._lines))
        for i, line in enumerate(self._lines):
            self.cart_table.setItem(i, 0, QTableWidgetItem(line.get("description", "")))
            amount_item = QTableWidgetItem(_money(self._line_total(line)))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(i, 1, amount_item)

    # ------------------------------------------------------------------ tenders
    def _on_add_tender(self) -> None:
        amount = float(self.tender_amount.value())
        if amount <= 0:
            return
        method = get_combo_selected_data(self.method_combo) or "cash"
        self._tenders.append({"method": method, "amount": amount})
        self.tender_amount.setValue(0)
        self._render_tenders()
        self._recompute()

    def _on_exact_cash(self) -> None:
        remaining = self._total() - self._paid()
        if remaining <= 0:
            return
        self._tenders.append({"method": "cash", "amount": round(remaining, 2)})
        self._render_tenders()
        self._recompute()

    def _on_remove_tender(self) -> None:
        row = self.tender_table.currentRow()
        if 0 <= row < len(self._tenders):
            self._tenders.pop(row)
            self._render_tenders()
            self._recompute()

    def _render_tenders(self) -> None:
        from ...utils.qt_helpers import PAYMENT_METHOD_OPTIONS
        labels = {v: l for l, v in PAYMENT_METHOD_OPTIONS}
        self.tender_table.setRowCount(len(self._tenders))
        for i, t in enumerate(self._tenders):
            self.tender_table.setItem(i, 0, QTableWidgetItem(labels.get(t["method"], t["method"])))
            amt = QTableWidgetItem(_money(t["amount"]))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tender_table.setItem(i, 1, amt)

    # ------------------------------------------------------------------ totals
    def _total(self) -> float:
        return float(sum(self._line_total(l) for l in self._lines))

    def _paid(self) -> float:
        return float(sum(float(t.get("amount") or 0) for t in self._tenders))

    def _recompute(self) -> None:
        total = self._total()
        paid = self._paid()
        change = max(paid - total, 0.0)
        self.total_label.setText(f"Total: {_money(total)}")
        self.paid_label.setText(f"Pagado: {_money(paid)}")
        self.change_label.setText(f"Cambio: {_money(change)}")
        can_charge = bool(self._lines) and paid + 0.01 >= total and total > 0
        self.charge_btn.setEnabled(can_charge)

    # ------------------------------------------------------------------ charge
    def _on_charge(self) -> None:
        if not self._lines:
            show_error(self, "Agrega al menos un concepto.", title="POS")
            return
        if self._paid() + 0.01 < self._total():
            show_error(self, "El pago es menor al total.", title="POS")
            return
        person_id = self._current_member.get("id") if self._current_member else None
        self.controller.finalize_sale(self._lines, self._tenders, person_id, None)

    def _reset_sale(self) -> None:
        self._lines = []
        self._tenders = []
        self._render_cart()
        self._render_tenders()
        self._recompute()
