"""Explicit recovery by cause, using a single server preview and local filtering."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHeaderView, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...table_widget_helpers import configure_table_widget
from ....utils.datetime_helpers import format_local_datetime


class RecoveryDialog(QDialog):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recuperar no entregados por causa")
        self.resize(1120, 800)
        self.setMinimumSize(820, 600)
        self._recipients = preview.get("recipients") or []
        self._causes = {c["key"]: c for c in preview.get("causes") or []}
        self.cause_checks = {}
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Elige las causas que quieres reintentar dentro de esta misma campaña. "
            "Los bloqueos y la disponibilidad se vuelven a verificar al programar y al enviar. "
            "Elegible no garantiza la entrega por Meta. Las fechas se muestran en hora de México."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        exclusions = QLabel(
            f"Excluidos: {preview.get('delivered', 0)} ya entregados · "
            f"{preview.get('duplicates', 0)} números duplicados · {preview.get('blocked', 0)} bloqueados. "
            "La tabla detalla los bloqueos de las causas seleccionadas."
        )
        exclusions.setWordWrap(True)
        layout.addWidget(exclusions)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(240)
        scroll.setMaximumHeight(370)
        content = QWidget()
        causes_layout = QVBoxLayout(content)
        for key, cause in self._causes.items():
            check = QCheckBox(
                f"{cause.get('total', 0)} · {cause['label']} — "
                f"{cause.get('eligible', 0)} elegibles, {cause.get('blocked', 0)} bloqueados"
            )
            check.setChecked(cause.get("selected_by_default", False))
            check.setEnabled(cause.get("total", 0) > 0)
            self.cause_checks[key] = check
            causes_layout.addWidget(check)
            note = QLabel(cause.get("note", ""))
            note.setWordWrap(True)
            note.setContentsMargins(22, 0, 0, 6)
            causes_layout.addWidget(note)
            check.toggled.connect(self._refresh)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Nombre", "Teléfono", "Causa", "Detalle", "Envío / bloqueo"])
        configure_table_widget(self.table)
        self.table.verticalHeader().setVisible(False)
        for column in range(5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 220)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def selected_causes(self):
        return [key for key, check in self.cause_checks.items() if check.isChecked() and check.isEnabled()]

    def _refresh(self):
        selected = set(self.selected_causes())
        rows = [r for r in self._recipients if r.get("cause") in selected]
        eligible = sum(bool(r.get("eligible")) and r.get("cause") in selected for r in rows)
        self.summary.setText(f"Se reenviará a {eligible} · {sum(not r.get('eligible') for r in rows)} excluidos en la lista")
        self.confirm_button.setText(f"Programar reenvío ({eligible})")
        self.confirm_button.setEnabled(eligible > 0)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for index, recipient in enumerate(rows):
            cause = self._causes.get(recipient.get("cause"), {})
            due = format_local_datetime(recipient.get("send_after")) if recipient.get("eligible") else None
            values = [recipient.get("person_name"), recipient.get("phone"), cause.get("label", "Excluido"),
                      recipient.get("detail"), due or recipient.get("blocked_reason") or "Requiere revisión"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value or "—")
                item.setToolTip(value or "")
                item.setData(Qt.ItemDataRole.UserRole, recipient.get("recipient_id"))
                self.table.setItem(index, column, item)
        self.table.setSortingEnabled(True)

    def accept(self):
        if self.confirm_button.isEnabled():
            super().accept()
