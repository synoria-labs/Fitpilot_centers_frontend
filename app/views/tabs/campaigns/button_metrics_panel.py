"""Exact quick-reply evidence; opening a URL is not an observable callback."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ...table_widget_helpers import configure_table_widget
from ....utils.datetime_helpers import format_local_datetime


class CampaignButtonsPanel(QGroupBox):
    requested = Signal(object, int)

    def __init__(self, parent=None):
        super().__init__("Interacciones con botones", parent)
        self.offset = 0
        self.limit = 50
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.buttons_table = self._table(["Botón", "Pulsaciones", "Personas únicas", "Conversiones posteriores"])
        self.buttons_table.setMaximumHeight(190)
        layout.addWidget(self.buttons_table)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Ver quién pulsó:"))
        self.button_filter = QComboBox()
        self.button_filter.setMinimumWidth(190)
        self.button_filter.currentIndexChanged.connect(self._filter_changed)
        toolbar.addWidget(self.button_filter, 1)
        self.refresh_btn = QPushButton("Actualizar interacciones")
        self.refresh_btn.clicked.connect(lambda: self.requested.emit(self.selected_key(), self.offset))
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)
        self.people_table = self._table(["Persona", "WhatsApp", "Botón pulsado", "Fecha y hora", "Conversión"])
        self.people_table.setMinimumHeight(155)
        self.people_table.setMaximumHeight(310)
        layout.addWidget(self.people_table)
        nav = QHBoxLayout()
        self.page_label = QLabel()
        self.previous_btn = QPushButton("Anterior")
        self.next_btn = QPushButton("Siguiente")
        self.previous_btn.clicked.connect(lambda: self._page(-1))
        self.next_btn.clicked.connect(lambda: self._page(1))
        nav.addWidget(self.page_label, 1)
        nav.addWidget(self.previous_btn)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)
        self.source = QLabel()
        self.source.setWordWrap(True)
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.source)
        self.clear()

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table_widget(table)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    def selected_key(self):
        return self.button_filter.currentData()

    def clear(self):
        self.offset = 0
        self.button_filter.blockSignals(True)
        self.button_filter.clear()
        self.button_filter.addItem("Todos los botones", None)
        self.button_filter.blockSignals(False)
        self.buttons_table.setRowCount(0)
        self.people_table.setRowCount(0)
        self.summary.setText("Cargando interacciones…")
        self.page_label.setText("")
        self.source.setText("")
        self.previous_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

    def _filter_changed(self):
        self.offset = 0
        self.people_table.setRowCount(0)
        self.page_label.setText("Cargando…")
        self.requested.emit(self.selected_key(), 0)

    def _page(self, direction):
        self.offset = max(0, self.offset + direction * self.limit)
        self.people_table.setRowCount(0)
        self.page_label.setText("Cargando…")
        self.requested.emit(self.selected_key(), self.offset)

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def set_analytics(self, data):
        if data.get("error"):
            self.summary.setText("No se pudieron cargar las interacciones: " + str(data["error"]))
            self.buttons_table.setRowCount(0)
            self.people_table.setRowCount(0)
            self.page_label.setText("")
            self.source.setText("")
            self.previous_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return
        self.summary.setText(
            f"Pulsaciones: {data.get('button_clicks', 0)} · Personas únicas: {data.get('button_clickers', 0)} · "
            f"Personas con conversión posterior: {data.get('converted_clickers', 0)}\n"
            f"Respuestas escritas a la campaña: {data.get('text_replies', 0)} · "
            f"Personas que escribieron: {data.get('text_reply_people', 0)} (se cuentan por separado).")
        groups = data.get("buttons") or []
        self._fill(self.buttons_table, [
            [b["label"] + (" (histórico)" if b.get("historical") else "") +
             (" · sin medición individual" if not b.get("measurable") else ""),
             b.get("clicks") if b.get("measurable") else "—",
             b.get("unique_people") if b.get("measurable") else "—",
             b.get("converted_people") if b.get("measurable") else "—"] for b in groups])
        selected = self.selected_key()
        self.button_filter.blockSignals(True)
        self.button_filter.clear()
        self.button_filter.addItem("Todos los botones", None)
        for button in groups:
            self.button_filter.addItem(button["label"], button["key"])
        self.button_filter.setCurrentIndex(max(0, self.button_filter.findData(selected)))
        self.button_filter.blockSignals(False)
        self.offset, self.limit = data.get("offset", 0), data.get("limit", 50)
        items = data.get("items") or []
        self._fill(self.people_table, [
            [e.get("person_name", "Sin nombre"), e.get("phone", ""), e.get("button_label", ""),
             format_local_datetime(e.get("clicked_at")),
             format_local_datetime(e.get("converted_at")) if e.get("converted") else "—"] for e in items])
        total = data.get("total", 0)
        self.page_label.setText(f"{self.offset + 1 if items else 0}–{self.offset + len(items)} de {total} pulsaciones"
                                if items else "Sin pulsaciones verificadas para este filtro")
        self.previous_btn.setEnabled(self.offset > 0)
        self.next_btn.setEnabled(self.offset + self.limit < total)
        updated = format_local_datetime(data.get("updated_at"))
        self.source.setText(
            f"Actualizado: {updated} (hora de México). Solo respuestas vinculadas al mensaje exacto de la campaña. "
            "Las personas se identifican por número de WhatsApp y pueden aparecer en varios botones; los totales únicos no se suman. "
            "Las conversiones son pagos posteriores atribuidos a la campaña y no demuestran causalidad. "
            "Los botones de enlace y llamada no notifican quién los abrió.")
