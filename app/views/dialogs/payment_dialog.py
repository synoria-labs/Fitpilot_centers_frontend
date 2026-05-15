"""Dialog para editar pagos."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox, 
    QComboBox, QTextEdit, QDialogButtonBox
)
from PySide6.QtCore import Qt

class PaymentDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data or {}
        self.setup_ui()
        if self.data:
            self.load_data(self.data)

    def setup_ui(self):
        self.setWindowTitle("Editar Pago" if self.data else "Nuevo Pago")
        self.setModal(True)
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Amount
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setMaximum(999999.0)
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("$ ")
        form_layout.addRow("Monto:", self.amount_input)

        # Method
        self.method_input = QComboBox()
        self.method_input.addItems(["cash", "credit_card", "debit_card", "transfer", "other"])
        form_layout.addRow("Método:", self.method_input)

        # Status
        self.status_input = QComboBox()
        self.status_input.addItems(["COMPLETED", "PENDING", "FAILED", "REFUNDED"])
        form_layout.addRow("Estado:", self.status_input)

        # Comment
        self.comment_input = QTextEdit()
        self.comment_input.setMaximumHeight(80)
        form_layout.addRow("Comentario:", self.comment_input)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_data(self, data):
        self.amount_input.setValue(float(data.get('amount', 0.0)))
        
        method = data.get('method', 'cash')
        idx = self.method_input.findText(method)
        if idx >= 0: 
            self.method_input.setCurrentIndex(idx)
            
        status = data.get('status', 'COMPLETED')
        idx = self.status_input.findText(status)
        if idx >= 0: 
            self.status_input.setCurrentIndex(idx)
            
        self.comment_input.setPlainText(data.get('comment') or "")

    def get_data(self):
        return {
            'amount': self.amount_input.value(),
            'method': self.method_input.currentText(),
            'status': self.status_input.currentText(),
            'comment': self.comment_input.toPlainText()
        }
