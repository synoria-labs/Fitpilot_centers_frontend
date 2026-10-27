"""Staff reconciliation of paid WhatsApp orders; never offers a second payment."""
from PySide6.QtCore import QDate
from datetime import datetime
from zoneinfo import ZoneInfo
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QDateEdit, QComboBox, QLabel, QHeaderView
from ...controllers.base_controller import BaseController
from ...utils.dialog_helpers import show_confirmation, show_error, show_info
from ..table_widget_helpers import configure_table_widget


class MembershipPurchaseOrdersPanel(QGroupBox):
    def __init__(self, service, parent=None):
        super().__init__("Pagos recibidos pendientes de aplicar", parent)
        self.service, self.rows, self.request_id = service, [], 0
        self.controller = BaseController(self)
        layout = QVBoxLayout(self)
        hint = QLabel("Confirma la nueva fecha con el cliente antes de aplicarla. Esta acción reutiliza el pago recibido; no cobra otra vez.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Cliente", "Plan", "Pago", "Inicio solicitado", "Estado", "Revisión"])
        configure_table_widget(self.table)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(140)
        self.table.setMaximumHeight(260)
        self.table.itemSelectionChanged.connect(self._selection)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        today = datetime.now(ZoneInfo("America/Mexico_City")).date()
        self.date = QDateEdit(QDate(today.year, today.month, today.day))
        self.date.setMinimumDate(QDate(today.year, today.month, today.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.dateChanged.connect(self._selection)
        self.sessions = QComboBox()
        self.sessions.setVisible(False)
        self.refresh = QPushButton("Actualizar pagos")
        self.refresh.clicked.connect(self.load)
        self.confirm = QPushButton("Aplicar a la fecha confirmada")
        self.confirm.clicked.connect(self._confirm)
        self.confirm.setEnabled(False)
        actions.addWidget(QLabel("Nuevo inicio:"))
        actions.addWidget(self.date)
        actions.addWidget(self.sessions, 1)
        actions.addWidget(self.confirm)
        actions.addWidget(self.refresh)
        layout.addLayout(actions)

    def load(self):
        self.controller._execute_authenticated_operation(self.service, "list_purchase_orders", self._loaded, self._error)

    def _loaded(self, rows):
        self.rows = rows or []
        self.table.setRowCount(len(self.rows))
        labels = {"paid_awaiting_start": "Inicio por confirmar", "needs_review": "Revisión del equipo", "paid": "Pago recibido"}
        for i, row in enumerate(self.rows):
            review = row.get("reviewReason") or "—"
            if row.get("providerPaymentId"):
                review += f" · Mercado Pago: {row['providerPaymentId']}"
            values = [row.get("participantName"), row.get("planName"), f"${row.get('amount', 0):.2f}",
                      row.get("startDate"), labels.get(row.get("status"), row.get("status")), review]
            for col, value in enumerate(values):
                self.table.setItem(i, col, QTableWidgetItem(str(value or "")))
            if row.get("externalReference"):
                self.table.item(i, 5).setToolTip("Referencia de la orden: " + row["externalReference"])
        self._selection()

    def selected(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _selection(self):
        self.request_id += 1
        request = self.request_id
        row = self.selected()
        eligible = bool(row and row.get("status") == "paid_awaiting_start" and row.get("paymentId"))
        self.confirm.setEnabled(eligible)
        self.sessions.blockSignals(True)
        self.sessions.clear()
        self.sessions.blockSignals(False)
        daily = bool(row and row.get("actionType") == "buy_day_pass")
        self.sessions.setVisible(daily)
        if daily and eligible:
            self.confirm.setEnabled(False)
            def loaded(options):
                if request != self.request_id:
                    return
                for option in options or []:
                    self.sessions.addItem(option["label"], option["sessionId"])
                self.confirm.setEnabled(self.sessions.count() > 0)
            self.controller._execute_authenticated_operation(self.service, "purchase_start_options", loaded, self._error,
                order_id=row["id"], start_date=self.date.date().toString("yyyy-MM-dd"))

    def _confirm(self):
        row = self.selected()
        if not row or row.get("status") != "paid_awaiting_start":
            return
        day = self.date.date().toString("yyyy-MM-dd")
        if not show_confirmation(self, f"¿Aplicar el pago de {row.get('participantName')} al inicio {self.date.date().toString('dd/MM/yyyy')}? Confirma esta fecha con el cliente.", title="Confirmar inicio"):
            return
        self.confirm.setEnabled(False)
        self.controller._execute_authenticated_operation(self.service, "confirm_purchase_start", self._confirmed, self._error,
            order_id=row["id"], start_date=day, session_id=self.sessions.currentData() if row.get("actionType") == "buy_day_pass" else None)

    def _confirmed(self, result):
        if not result.get("success"):
            self._error(result.get("error") or "No se pudo aplicar el pago")
            return
        show_info(self, result.get("message") or "La membresía quedó registrada.", title="Inicio confirmado")
        self.load()

    def _error(self, error):
        show_error(self, str(error), title="Pagos pendientes")
        row = self.selected()
        eligible = bool(row and row.get("status") == "paid_awaiting_start" and row.get("paymentId"))
        self.confirm.setEnabled(eligible and (row.get("actionType") != "buy_day_pass" or self.sessions.count() > 0))
