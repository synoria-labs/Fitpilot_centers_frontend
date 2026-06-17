"""Vista de la pestaña de Finanzas - Gestión de pagos."""
from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...controllers.finances_controller import FinancesController
from ...core import container, get_logger
from ...utils.dialog_helpers import show_confirmation, show_error, show_info
from ..dialogs.payment_dialog import PaymentDialog
from ..table_widget_helpers import configure_table_widget
from ..widgets.payments_filter_bar import PaymentsFilterBar
from ..widgets.payments_metrics_panel import PaymentsMetricsPanel

logger = get_logger(__name__)


class FinancesTab(QWidget):
    def __init__(self):
        super().__init__()

        finances_service = container.get("finances_service")
        self.controller = FinancesController(finances_service, self)

        self.setup_ui()
        self.connect_signals()

        # Initial load reflects the default filter (this month).
        self.controller.apply_filters(self.filter_bar.filters())

    # --------------------------------------------------------------- ui

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Finanzas - Pagos")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.edit_btn = QPushButton("Editar Pago")
        self.edit_btn.setObjectName("actionButton")
        self.edit_btn.setEnabled(False)
        header_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Eliminar Pago")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setEnabled(False)
        header_layout.addWidget(self.delete_btn)

        layout.addLayout(header_layout)

        # Filters
        self.filter_bar = PaymentsFilterBar(initial=self.controller.filters())
        layout.addWidget(self.filter_bar)

        # Metrics panel
        self.metrics_panel = PaymentsMetricsPanel()
        layout.addWidget(self.metrics_panel)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Fecha", "Socio", "Monto", "Método", "Estado", "Comentario", "ID Socio"]
        )
        configure_table_widget(self.table)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.hideColumn(7)  # Hide Person ID
        layout.addWidget(self.table)

        # Footer
        footer_layout = QHBoxLayout()
        self.status_label = QLabel("Cargando pagos...")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        layout.addLayout(footer_layout)

    def connect_signals(self):
        self.filter_bar.filters_changed.connect(self.on_filters_changed)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellDoubleClicked.connect(self.on_edit_clicked)
        self.edit_btn.clicked.connect(self.on_edit_clicked)
        self.delete_btn.clicked.connect(self.on_delete_clicked)

        self.controller.state_changed.connect(self.on_state_changed)
        self.controller.metrics_changed.connect(self.metrics_panel.update_metrics)
        self.controller.error_occurred.connect(self.on_error)
        self.controller.action_completed.connect(self.on_action_completed)

    # --------------------------------------------------------------- slots

    @Slot(object)
    def on_filters_changed(self, filters):
        self.controller.apply_filters(filters)

    def on_selection_changed(self):
        has_selection = len(self.table.selectedItems()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    @Slot(object)
    def on_state_changed(self, state):
        # Repopulate the table from the new state
        self.table.setRowCount(0)
        for i, payment in enumerate(state.payments):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(str(payment.get("id"))))

            date_str = payment.get("paidAt", "") or ""
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                pass
            self.table.setItem(i, 1, QTableWidgetItem(date_str))

            self.table.setItem(i, 2, QTableWidgetItem(payment.get("personName") or "N/A"))
            self.table.setItem(i, 3, QTableWidgetItem(f"${float(payment.get('amount', 0) or 0):.2f}"))
            self.table.setItem(i, 4, QTableWidgetItem(payment.get("method", "")))
            self.table.setItem(i, 5, QTableWidgetItem(payment.get("status", "")))
            self.table.setItem(i, 6, QTableWidgetItem(payment.get("comment", "") or ""))
            self.table.setItem(i, 7, QTableWidgetItem(str(payment.get("personId"))))

        self.table.resizeColumnsToContents()

        if state.loading:
            self.status_label.setText("Cargando...")
        else:
            shown = len(state.payments)
            total = state.total or shown
            if total == shown:
                self.status_label.setText(f"{shown} pagos")
            else:
                self.status_label.setText(f"{shown} de {total} pagos")

    @Slot(str)
    def on_error(self, message):
        show_error(self, message, "Error")

    @Slot(str, str)
    def on_action_completed(self, title, message):
        show_info(self, message, title)

    def on_edit_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return

        payment_id = int(self.table.item(row, 0).text())
        amount_str = self.table.item(row, 3).text().replace("$", "").replace(",", "")
        amount = float(amount_str) if amount_str else 0.0
        method = self.table.item(row, 4).text()
        status = self.table.item(row, 5).text()
        comment = self.table.item(row, 6).text()

        data = {
            "amount": amount,
            "method": method,
            "status": status,
            "comment": comment,
        }

        dialog = PaymentDialog(self, data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_data()
            self.controller.update_payment(payment_id, updated_data)

    def on_delete_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return

        payment_id = int(self.table.item(row, 0).text())
        person_name = self.table.item(row, 2).text()

        if show_confirmation(
            self,
            f"¿Está seguro de eliminar el pago de {person_name} (ID: {payment_id})?",
            "Confirmar Eliminación",
        ):
            self.controller.delete_payment(payment_id)
