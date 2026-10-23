"""Pestaña «Eventos especiales»: clases únicas con cupo y precio propios.

Un evento especial (p. ej. Halloween) no es una clase regular ni una membresía: tiene sus
propias bicicletas, se cobra aparte por Mercado Pago y comprarlo no toca la membresía de nadie.
Cuando cae en el horario de una clase regular, el personal decide explícitamente sustituirla
después de ver a quién afecta; esos clientes quedan en una lista de seguimiento manual.

La pantalla tiene cuatro pestañas, en el orden en que se trabaja un evento:

1. **Evento** — los datos, el estado de publicación y lo que falta para publicar.
2. **Horario regular** — vista previa de clases y clientes afectados, aplicar la sustitución y,
   si el evento se cancela, restituir el horario con vista previa.
3. **Participantes** — quién pagó, quién tiene un lugar apartado y hasta cuándo.
4. **Clientes desplazados** — registrar cuándo se avisó a cada cliente y cómo se compensó.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import QDate, QSize, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...controllers.special_events_controller import SpecialEventsController
from ...core import container, get_logger
from ...utils.datetime_helpers import format_local_datetime
from ...utils.dialog_helpers import show_confirmation, show_error, show_info
from ..screen_style import screen_qss
from ..table_widget_helpers import configure_table_widget
from .whatsapp import theme

logger = get_logger(__name__)

_TITLE = "Eventos especiales"
_DEFAULT_TZ = "America/Mexico_City"

EVENT_STATUS = {
    "draft": "Borrador",
    "published": "Publicado",
    "canceled": "Cancelado",
    "completed": "Terminado",
}
ORDER_STATUS = {
    "awaiting_payment": "Esperando pago",
    "paid": "Pagado",
    "expired": "Apartado vencido",
    "canceled": "Cancelado",
    "refund_pending": "Por reembolsar",
    "refunded": "Reembolsado",
    "needs_review": "En revisión",
}
FOLLOW_UP_STATUS = {"pending": "Pendiente", "notified": "Avisado", "resolved": "Resuelto"}
COMPENSATIONS = [
    ("make_up_class", "Reposición de clase"),
    ("membership_extension", "Extensión de membresía"),
    ("event_access", "Acceso al evento"),
    ("credit", "Saldo a favor"),
    ("refund", "Devolución"),
    ("not_needed", "No requirió compensación"),
    ("other", "Otra"),
]
COMPENSATION_LABELS = dict(COMPENSATIONS)
PAYMENT_METHODS = [
    ("cash", "Efectivo"),
    ("card", "Tarjeta"),
    ("transfer", "Transferencia"),
    ("courtesy", "Cortesía (sin cobro)"),
]
PAYMENT_LABELS = {"mercadopago": "Mercado Pago", **dict(PAYMENT_METHODS)}
RESTORATION = {"restored": "Reactivada", "kept_displaced": "Sigue desplazada"}
NOTICE_CHANNELS = ["WhatsApp", "Llamada", "En persona", "Otro"]

_STATUS_COLORS = {
    "published": "#2e7d32",
    "draft": "#8d6e00",
    "canceled": "#c62828",
    "completed": "#616161",
    "paid": "#2e7d32",
    "awaiting_payment": "#8d6e00",
    "needs_review": "#c62828",
    "refund_pending": "#c62828",
    "pending": "#c62828",
    "notified": "#8d6e00",
    "resolved": "#2e7d32",
}


def _icon(name: str, primary: bool = False):
    return qta.icon(name, color="#ffffff" if primary else theme.palette_hex())


def _item(text: Any, *, user_data: Any = None, status: Optional[str] = None) -> QTableWidgetItem:
    item = QTableWidgetItem("" if text is None else str(text))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if user_data is not None:
        item.setData(Qt.ItemDataRole.UserRole, user_data)
    if status and status in _STATUS_COLORS:
        from PySide6.QtGui import QColor

        item.setForeground(QColor(_STATUS_COLORS[status]))
    return item


def _money(value: Any, currency: str = "MXN") -> str:
    try:
        return f"${float(value):,.2f} {currency}"
    except (TypeError, ValueError):
        return "—"


class SpecialEventsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        service = container.get("special_events_service")
        self.controller = SpecialEventsController(service, self)
        self._events: List[Dict[str, Any]] = []
        self._detail: Optional[Dict[str, Any]] = None
        self._options: Optional[Dict[str, Any]] = None
        self._campaigns: List[Dict[str, Any]] = []
        self._takeover_preview: Optional[Dict[str, Any]] = None
        self._restore_preview: Optional[Dict[str, Any]] = None
        self._creating = False
        self._pending_select: Optional[int] = None

        self._build_ui()
        self._connect_controller()
        self.controller.load_options()
        self.controller.load_campaigns()
        self.controller.load_events()

    # ================================================================== UI
    def _build_ui(self) -> None:
        self.setObjectName("eventsTab")
        self.setStyleSheet(screen_qss("events"))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("eventsHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 12)
        header_layout.setSpacing(8)
        row = QHBoxLayout()
        title = QLabel(_TITLE)
        title.setObjectName("eventsTitle")
        row.addWidget(title)
        row.addStretch()
        self.past_check = QCheckBox("Mostrar pasados")
        self.past_check.toggled.connect(lambda _=False: self._reload_events())
        row.addWidget(self.past_check)
        self.refresh_btn = QPushButton("Actualizar")
        self.refresh_btn.setIcon(_icon("fa5s.sync"))
        self.refresh_btn.setIconSize(QSize(14, 14))
        self.refresh_btn.clicked.connect(self._refresh_all)
        row.addWidget(self.refresh_btn)
        self.new_btn = QPushButton("Nuevo evento")
        self.new_btn.setObjectName("eventsPrimaryButton")
        self.new_btn.setIcon(_icon("fa5s.plus", primary=True))
        self.new_btn.setIconSize(QSize(14, 14))
        self.new_btn.clicked.connect(self._start_new_event)
        row.addWidget(self.new_btn)
        header_layout.addLayout(row)
        hint = QLabel(
            "Clases únicas con cupo y precio propios (por ejemplo, Halloween). No usan ni "
            "modifican membresías. El asistente de WhatsApp solo vende eventos publicados y "
            "cobra siempre con Mercado Pago; nunca confirma un lugar sin pago acreditado."
        )
        hint.setObjectName("eventsHint")
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list_pane())
        splitter.addWidget(self._build_detail_pane())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([400, 1000])
        root.addWidget(splitter, 1)

    def _build_list_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("eventsListPane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 12, 6, 12)
        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels(["Evento", "Fecha", "Estado", "Vendidos"])
        configure_table_widget(self.events_table)
        self.events_table.verticalHeader().setVisible(False)
        header = self.events_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.events_table.itemSelectionChanged.connect(self._on_event_selected)
        layout.addWidget(self.events_table)
        self.empty_label = QLabel("Todavía no hay eventos especiales.")
        self.empty_label.setObjectName("eventsHint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        return pane

    def _build_detail_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("eventsConfigPane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 12, 12, 12)
        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(self._scroll(self._build_event_tab()), "Evento")
        self.detail_tabs.addTab(self._scroll(self._build_takeover_tab()), "Horario regular")
        self.detail_tabs.addTab(self._build_participants_tab(), "Participantes")
        self.detail_tabs.addTab(self._build_displaced_tab(), "Clientes desplazados")
        layout.addWidget(self.detail_tabs)
        self._set_detail_enabled(False)
        return pane

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("eventsConfigScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ------------------------------------------------------------- tab: Evento
    def _build_event_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)

        self.status_label = QLabel("Selecciona un evento o crea uno nuevo.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.status_label)

        form_box = QGroupBox("Datos del evento")
        form = QFormLayout(form_box)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Halloween · 2.º aniversario")
        form.addRow("Nombre", self.name_edit)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setFixedHeight(64)
        form.addRow("Descripción", self.description_edit)
        self.includes_edit = QPlainTextEdit()
        self.includes_edit.setFixedHeight(84)
        self.includes_edit.setPlaceholderText("Un elemento por línea (kit, snacks, DJ…)")
        form.addRow("Incluye", self.includes_edit)
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Vacío = dirección de la sede")
        form.addRow("Dirección para clientes", self.address_edit)

        self.venue_combo = QComboBox()
        self.venue_combo.currentIndexChanged.connect(self._on_venue_changed)
        form.addRow("Sede", self.venue_combo)
        self.instructor_combo = QComboBox()
        form.addRow("Instructora", self.instructor_combo)
        self.class_type_combo = QComboBox()
        form.addRow("Tipo de clase", self.class_type_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Fecha", self.date_edit)
        self.start_edit = QTimeEdit()
        self.start_edit.setDisplayFormat("HH:mm")
        form.addRow("Hora de inicio", self.start_edit)
        end_row = QHBoxLayout()
        self.end_edit = QTimeEdit()
        self.end_edit.setDisplayFormat("HH:mm")
        self.end_unknown = QCheckBox("Aún no sé la duración")
        self.end_unknown.toggled.connect(lambda checked: self.end_edit.setEnabled(not checked))
        end_row.addWidget(self.end_edit)
        end_row.addWidget(self.end_unknown)
        end_row.addStretch()
        form.addRow("Hora de fin", end_row)
        self.timezone_label = QLabel(_DEFAULT_TZ)
        self.timezone_label.setObjectName("eventsHint")
        form.addRow("Zona horaria", self.timezone_label)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 100000)
        self.price_spin.setDecimals(2)
        self.price_spin.setPrefix("$ ")
        self.price_spin.setSuffix(" MXN")
        form.addRow("Precio por participante", self.price_spin)
        cap_row = QHBoxLayout()
        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 500)
        self.capacity_unknown = QCheckBox("Aún no sé el cupo")
        self.capacity_unknown.toggled.connect(lambda checked: self.capacity_spin.setEnabled(not checked))
        cap_row.addWidget(self.capacity_spin)
        cap_row.addWidget(self.capacity_unknown)
        cap_row.addStretch()
        form.addRow("Cupo", cap_row)
        self.hold_spin = QSpinBox()
        self.hold_spin.setRange(5, 240)
        self.hold_spin.setSuffix(" min")
        self.hold_spin.setToolTip(
            "Mientras el cliente paga, su bicicleta queda apartada este tiempo. El enlace de "
            "pago vence a la misma hora; después el lugar vuelve a estar disponible."
        )
        form.addRow("Apartado mientras paga", self.hold_spin)

        seats_box = QVBoxLayout()
        self.seats_list = QListWidget()
        self.seats_list.setMaximumHeight(150)
        seats_box.addWidget(self.seats_list)
        seats_buttons = QHBoxLayout()
        all_btn = QPushButton("Todas")
        all_btn.clicked.connect(lambda: self._check_all_seats(True))
        none_btn = QPushButton("Ninguna")
        none_btn.clicked.connect(lambda: self._check_all_seats(False))
        seats_buttons.addWidget(all_btn)
        seats_buttons.addWidget(none_btn)
        seats_buttons.addStretch()
        seats_box.addLayout(seats_buttons)
        form.addRow("Bicicletas del evento", seats_box)
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        self.save_btn.setObjectName("eventsPrimaryButton")
        self.save_btn.clicked.connect(self._save_event)
        self.publish_btn = QPushButton("Publicar")
        self.publish_btn.clicked.connect(self._publish)
        self.unpublish_btn = QPushButton("Volver a borrador")
        self.unpublish_btn.clicked.connect(self._unpublish)
        self.cancel_event_btn = QPushButton("Cancelar evento")
        self.cancel_event_btn.setObjectName("dangerButton")
        self.cancel_event_btn.clicked.connect(self._cancel_event)
        for btn in (self.save_btn, self.publish_btn, self.unpublish_btn, self.cancel_event_btn):
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        campaigns_box = QGroupBox("Campañas de WhatsApp vinculadas")
        campaigns_layout = QVBoxLayout(campaigns_box)
        note = QLabel(
            "Vincula la campaña que promociona este evento: cuando un cliente toque «Quiero "
            "reservar» o «Más información», el asistente sabrá de qué evento se trata y "
            "consultará sus datos reales (precio, horario y lugares)."
        )
        note.setObjectName("eventsHint")
        note.setWordWrap(True)
        campaigns_layout.addWidget(note)
        self.linked_label = QLabel("—")
        self.linked_label.setWordWrap(True)
        campaigns_layout.addWidget(self.linked_label)
        link_row = QHBoxLayout()
        self.campaign_combo = QComboBox()
        link_row.addWidget(self.campaign_combo, 1)
        self.link_btn = QPushButton("Vincular")
        self.link_btn.clicked.connect(lambda: self._link_campaign(True))
        self.unlink_btn = QPushButton("Desvincular")
        self.unlink_btn.clicked.connect(lambda: self._link_campaign(False))
        link_row.addWidget(self.link_btn)
        link_row.addWidget(self.unlink_btn)
        campaigns_layout.addLayout(link_row)
        layout.addWidget(campaigns_box)
        layout.addStretch()
        return body

    # ------------------------------------------------------ tab: Horario regular
    def _build_takeover_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)
        explain = QLabel(
            "Si en el horario del evento hay una clase regular en la misma sede, el evento la "
            "sustituye: la clase queda marcada como «desplazada» y deja de venderse. Las "
            "reservas de esa clase se conservan (no cuentan como falta ni consumen clase) y sus "
            "clientes pasan a «Clientes desplazados» para que ustedes les avisen y decidan la "
            "compensación. No se cambian membresías ni se envían mensajes. El horario de otras "
            "fechas no se modifica."
        )
        explain.setWordWrap(True)
        layout.addWidget(explain)

        preview_box = QGroupBox("Sustituir el horario regular")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_btn = QPushButton("Revisar clases afectadas")
        self.preview_btn.clicked.connect(self._load_takeover_preview)
        preview_layout.addWidget(self.preview_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.preview_summary = QLabel("Revisa la vista previa antes de aplicar la sustitución.")
        self.preview_summary.setWordWrap(True)
        preview_layout.addWidget(self.preview_summary)
        self.preview_table = QTableWidget(0, 6)
        self.preview_table.setHorizontalHeaderLabels(
            ["Clase", "Cliente", "Teléfono", "Bici", "Membresía", "Origen"]
        )
        configure_table_widget(self.preview_table)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setMinimumHeight(180)
        preview_layout.addWidget(self.preview_table)
        self.takeover_confirm = QCheckBox(
            "Revisé la lista y entiendo que estas clases quedarán desplazadas"
        )
        self.takeover_confirm.toggled.connect(lambda _=False: self._update_takeover_button())
        preview_layout.addWidget(self.takeover_confirm)
        self.apply_takeover_btn = QPushButton("Aplicar sustitución")
        self.apply_takeover_btn.setObjectName("eventsPrimaryButton")
        self.apply_takeover_btn.clicked.connect(self._apply_takeover)
        preview_layout.addWidget(self.apply_takeover_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(preview_box)

        restore_box = QGroupBox("Restituir el horario regular (si el evento se cancela)")
        restore_layout = QVBoxLayout(restore_box)
        restore_note = QLabel(
            "Reactiva las clases sustituidas. Solo se reactivan las reservas que siguen tal "
            "como las dejó la sustitución y sin compensación registrada; las demás se quedan "
            "desplazadas, con el motivo, para revisarlas a mano."
        )
        restore_note.setWordWrap(True)
        restore_note.setObjectName("eventsHint")
        restore_layout.addWidget(restore_note)
        self.restore_preview_btn = QPushButton("Revisar restitución")
        self.restore_preview_btn.clicked.connect(self._load_restore_preview)
        restore_layout.addWidget(self.restore_preview_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.restore_summary = QLabel("—")
        self.restore_summary.setWordWrap(True)
        restore_layout.addWidget(self.restore_summary)
        self.restore_table = QTableWidget(0, 3)
        self.restore_table.setHorizontalHeaderLabels(["Cliente", "Resultado", "Motivo"])
        configure_table_widget(self.restore_table)
        self.restore_table.verticalHeader().setVisible(False)
        self.restore_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.restore_table.horizontalHeader().setStretchLastSection(True)
        self.restore_table.setMinimumHeight(120)
        restore_layout.addWidget(self.restore_table)
        self.restore_btn = QPushButton("Restituir horario regular")
        self.restore_btn.clicked.connect(self._restore_schedule)
        restore_layout.addWidget(self.restore_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(restore_box)

        history_box = QGroupBox("Historial de sustituciones")
        history_layout = QVBoxLayout(history_box)
        self.takeovers_table = QTableWidget(0, 4)
        self.takeovers_table.setHorizontalHeaderLabels(["Clase", "Estado", "Aplicó", "Restituyó"])
        configure_table_widget(self.takeovers_table)
        self.takeovers_table.verticalHeader().setVisible(False)
        self.takeovers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.takeovers_table.setMinimumHeight(90)
        history_layout.addWidget(self.takeovers_table)
        layout.addWidget(history_box)
        layout.addStretch()
        return body

    # ---------------------------------------------------------- tab: Participantes
    def _build_participants_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        self.participants_summary = QLabel("—")
        self.participants_summary.setWordWrap(True)
        layout.addWidget(self.participants_summary)
        self.seats_summary = QLabel("—")
        self.seats_summary.setObjectName("eventsHint")
        self.seats_summary.setWordWrap(True)
        layout.addWidget(self.seats_summary)
        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(
            ["Participante", "Teléfono", "Bici", "Estado", "Importe", "Pago", "Pagado / apartado hasta", "Notas"]
        )
        configure_table_widget(self.orders_table)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.orders_table, 1)
        buttons = QHBoxLayout()
        self.add_participant_btn = QPushButton("Registrar participante")
        self.add_participant_btn.clicked.connect(self._add_participant)
        self.cancel_order_btn = QPushButton("Cancelar compra no pagada")
        self.cancel_order_btn.clicked.connect(self._cancel_order)
        self.refund_btn = QPushButton("Reembolsar")
        self.refund_btn.setObjectName("dangerButton")
        self.refund_btn.clicked.connect(self._refund_order)
        for btn in (self.add_participant_btn, self.cancel_order_btn, self.refund_btn):
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return body

    # ---------------------------------------------------- tab: Clientes desplazados
    def _build_displaced_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        note = QLabel(
            "Clientes cuya clase regular fue sustituida por el evento. El sistema no les envía "
            "mensajes ni extiende membresías: registra aquí cuándo les avisaron y cómo se "
            "resolvió su compensación."
        )
        note.setObjectName("eventsHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.displaced_summary = QLabel("—")
        layout.addWidget(self.displaced_summary)
        self.displaced_table = QTableWidget(0, 9)
        self.displaced_table.setHorizontalHeaderLabels(
            ["Cliente", "Teléfono", "Clase original", "Bici", "Membresía", "Seguimiento",
             "Aviso", "Compensación", "Restitución"]
        )
        configure_table_widget(self.displaced_table)
        self.displaced_table.verticalHeader().setVisible(False)
        self.displaced_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.displaced_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.displaced_table, 1)
        buttons = QHBoxLayout()
        self.notice_btn = QPushButton("Registrar aviso")
        self.notice_btn.clicked.connect(self._register_notice)
        self.compensation_btn = QPushButton("Registrar compensación")
        self.compensation_btn.clicked.connect(self._register_compensation)
        self.reopen_btn = QPushButton("Reabrir")
        self.reopen_btn.clicked.connect(self._reopen_follow_up)
        for btn in (self.notice_btn, self.compensation_btn, self.reopen_btn):
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return body

    # ========================================================== controller wiring
    def _connect_controller(self) -> None:
        c = self.controller
        c.events_loaded.connect(self._render_events)
        c.detail_loaded.connect(self._render_detail)
        c.options_loaded.connect(self._apply_options)
        c.campaigns_loaded.connect(self._apply_campaigns)
        c.takeover_preview_loaded.connect(self._render_takeover_preview)
        c.restore_preview_loaded.connect(self._render_restore_preview)
        c.follow_up_saved.connect(lambda _d: self._reload_detail())
        c.operation_succeeded.connect(self._on_operation_succeeded)
        c.error_occurred.connect(lambda msg: show_error(self, msg or "Ocurrió un error.", title=_TITLE))
        c.loading_changed.connect(self._on_loading)

    def _on_loading(self, loading: bool) -> None:
        self.refresh_btn.setEnabled(not loading)
        self.save_btn.setEnabled(not loading)

    def _on_operation_succeeded(self, message: str) -> None:
        self._reload_events()
        self.controller.load_campaigns()
        show_info(self, message, title=_TITLE)

    def _refresh_all(self) -> None:
        self.controller.load_options()
        self.controller.load_campaigns()
        self._reload_events()
        self._reload_detail()

    def _reload_events(self) -> None:
        self.controller.load_events(self.past_check.isChecked())

    def _reload_detail(self) -> None:
        event_id = self._current_event_id()
        if event_id is not None:
            self.controller.load_event(event_id)

    # ================================================================ rendering
    def _render_events(self, events: List[Dict[str, Any]]) -> None:
        self._events = list(events or [])
        selected = self._current_event_id() or self._pending_select
        self.events_table.blockSignals(True)
        try:
            self.events_table.setRowCount(len(self._events))
            for row, event in enumerate(self._events):
                self.events_table.setItem(row, 0, _item(event.get("name"), user_data=event.get("id")))
                self.events_table.setItem(
                    row, 1, _item(f"{event.get('local_date')} {event.get('local_start_time')}")
                )
                status = event.get("status")
                self.events_table.setItem(row, 2, _item(EVENT_STATUS.get(status, status), status=status))
                capacity = event.get("capacity")
                sold = f"{event.get('sold', 0)}/{capacity}" if capacity else f"{event.get('sold', 0)}/—"
                self.events_table.setItem(row, 3, _item(sold))
        finally:
            self.events_table.blockSignals(False)
        self.empty_label.setVisible(not self._events)
        if selected is not None:
            self._select_event_row(selected)
        self._pending_select = None

    def _select_event_row(self, event_id: int) -> None:
        for row in range(self.events_table.rowCount()):
            item = self.events_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == event_id:
                self.events_table.blockSignals(True)
                self.events_table.selectRow(row)
                self.events_table.blockSignals(False)
                return

    def _render_detail(self, detail: Optional[Dict[str, Any]]) -> None:
        if not detail or not detail.get("event"):
            return
        self._detail = detail
        self._creating = False
        event = detail["event"]
        if self._current_list_selection() != event["id"]:
            self._pending_select = event["id"]
            self._select_event_row(event["id"])
        self._set_detail_enabled(True)
        self._fill_form(event)
        self._render_status(event)
        self._render_orders(detail.get("orders") or [], event)
        self._render_displacements(detail.get("displacements") or [])
        self._render_takeovers(detail.get("takeovers") or [])
        self._invalidate_takeover_preview()
        self._invalidate_restore_preview()
        self._render_linked_campaigns(event)
        self._update_action_buttons()

    def _render_status(self, event: Dict[str, Any]) -> None:
        status = event.get("status")
        color = _STATUS_COLORS.get(status, "#616161")
        lines = [
            f"<b style='color:{color}'>{EVENT_STATUS.get(status, status)}</b> · "
            f"{event.get('schedule_label') or ''}"
        ]
        if status == "published":
            if event.get("sales_open"):
                lines.append(f"A la venta: quedan {event.get('available')} lugar(es).")
            else:
                lines.append(f"No está a la venta: {event.get('sales_closed_reason') or '—'}")
        if status == "canceled" and event.get("cancel_reason"):
            lines.append(f"Motivo de cancelación: {event['cancel_reason']}")
        blockers = event.get("publish_blockers") or []
        if status == "draft" and blockers:
            lines.append("<b>Para publicar falta:</b><br>• " + "<br>• ".join(blockers))
        elif status == "draft":
            lines.append("Listo para publicar.")
        if event.get("payments_warning"):
            lines.append(f"<span style='color:#c62828'>⚠ {event['payments_warning']}</span>")
        if event.get("pending_follow_ups"):
            lines.append(
                f"{event['pending_follow_ups']} cliente(s) desplazado(s) con seguimiento pendiente."
            )
        self.status_label.setText("<br>".join(lines))

    def _render_orders(self, orders: List[Dict[str, Any]], event: Dict[str, Any]) -> None:
        self.orders_table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            status = order.get("status")
            when = (
                format_local_datetime(order.get("paid_at"))
                if status == "paid"
                else f"hasta {format_local_datetime(order.get('hold_expires_at'), '%H:%M')}"
                if status == "awaiting_payment"
                else format_local_datetime(order.get("refunded_at") or order.get("created_at"))
            )
            notes = order.get("review_reason") or order.get("cancel_reason") or order.get("notes") or ""
            self.orders_table.setItem(row, 0, _item(order.get("participant_name"), user_data=order.get("id")))
            self.orders_table.setItem(row, 1, _item(order.get("participant_phone") or "—"))
            self.orders_table.setItem(row, 2, _item(order.get("seat_label") or "—"))
            self.orders_table.setItem(row, 3, _item(ORDER_STATUS.get(status, status), status=status))
            self.orders_table.setItem(row, 4, _item(_money(order.get("amount"), order.get("currency") or "MXN")))
            method = order.get("payment_method")
            self.orders_table.setItem(row, 5, _item(PAYMENT_LABELS.get(method, method or "—")))
            self.orders_table.setItem(row, 6, _item(when))
            self.orders_table.setItem(row, 7, _item(notes))
        capacity = event.get("capacity")
        self.participants_summary.setText(
            f"Pagados {event.get('sold', 0)} · Apartados {event.get('held', 0)} · "
            f"Disponibles {event.get('available') if event.get('available') is not None else '—'}"
            f" de {capacity if capacity else '— (cupo pendiente)'} · "
            f"{_money(event.get('price'), event.get('currency') or 'MXN')} por participante"
        )
        seats = event.get("seats") or []
        free = [s["label"] for s in seats if s.get("status") == "free"]
        held = [s["label"] for s in seats if s.get("status") == "held"]
        sold = [s["label"] for s in seats if s.get("status") == "sold"]
        self.seats_summary.setText(
            f"Bicis libres: {', '.join(free) or '—'}\nApartadas: {', '.join(held) or '—'}\n"
            f"Vendidas: {', '.join(sold) or '—'}"
        )

    def _render_displacements(self, rows: List[Dict[str, Any]]) -> None:
        self.displaced_table.setRowCount(len(rows))
        counts = {"pending": 0, "notified": 0, "resolved": 0}
        for row, d in enumerate(rows):
            status = d.get("follow_up_status")
            counts[status] = counts.get(status, 0) + 1
            membership = d.get("plan_name") or "—"
            if d.get("membership_ends_at"):
                membership += f" · vence {format_local_datetime(d['membership_ends_at'], '%d/%m/%Y')}"
            notice = "—"
            if d.get("notified_at"):
                notice = format_local_datetime(d["notified_at"])
                if d.get("notification_channel"):
                    notice += f" · {d['notification_channel']}"
                if d.get("notified_by_name"):
                    notice += f" · {d['notified_by_name']}"
            compensation = COMPENSATION_LABELS.get(d.get("compensation_type"), d.get("compensation_type") or "—")
            if d.get("compensation_notes"):
                compensation += f" · {d['compensation_notes']}"
            restoration = RESTORATION.get(d.get("restoration_status"), "—")
            if d.get("restoration_note"):
                restoration += f" · {d['restoration_note']}"
            self.displaced_table.setItem(row, 0, _item(d.get("person_name"), user_data=d.get("id")))
            self.displaced_table.setItem(row, 1, _item(d.get("phone") or "—"))
            original = f"{d.get('session_name')} · {format_local_datetime(d.get('session_start_at'), '%d/%m %H:%M')}"
            self.displaced_table.setItem(row, 2, _item(original))
            self.displaced_table.setItem(row, 3, _item(d.get("seat_label") or "—"))
            self.displaced_table.setItem(row, 4, _item(membership))
            self.displaced_table.setItem(row, 5, _item(FOLLOW_UP_STATUS.get(status, status), status=status))
            self.displaced_table.setItem(row, 6, _item(notice))
            self.displaced_table.setItem(row, 7, _item(compensation))
            self.displaced_table.setItem(row, 8, _item(restoration))
        self.displaced_summary.setText(
            f"Pendientes {counts.get('pending', 0)} · Avisados {counts.get('notified', 0)} · "
            f"Resueltos {counts.get('resolved', 0)}"
        )

    def _render_takeovers(self, takeovers: List[Dict[str, Any]]) -> None:
        self.takeovers_table.setRowCount(len(takeovers))
        for row, t in enumerate(takeovers):
            applied = f"{format_local_datetime(t.get('applied_at'))} · {t.get('applied_by_name') or '—'}"
            restored = (
                f"{format_local_datetime(t.get('restored_at'))} · {t.get('restored_by_name') or '—'}"
                if t.get("restored_at")
                else "—"
            )
            status = "Activa" if t.get("status") == "active" else "Restituida"
            self.takeovers_table.setItem(row, 0, _item(f"{t.get('session_name')} · {t.get('session_label')}"))
            self.takeovers_table.setItem(row, 1, _item(status))
            self.takeovers_table.setItem(row, 2, _item(applied))
            self.takeovers_table.setItem(row, 3, _item(restored))

    def _render_takeover_preview(self, preview: Optional[Dict[str, Any]]) -> None:
        self._takeover_preview = preview
        self.takeover_confirm.setChecked(False)
        if not preview:
            self.preview_summary.setText("No se pudo obtener la vista previa.")
            self.preview_table.setRowCount(0)
            self._update_takeover_button()
            return
        text = preview.get("summary") or ""
        if preview.get("blockers"):
            text += "\n⚠ " + "\n⚠ ".join(preview["blockers"])
        self.preview_summary.setText(text)
        rows = []
        for session in preview.get("sessions") or []:
            label = session.get("name") or "Clase"  # the date is in the summary above
            if session.get("taken_by_this_event"):
                rows.append((label, "(ya sustituida por este evento)", "", "", "", ""))
                continue
            clients = session.get("clients") or []
            if not clients:
                rows.append((label, "Sin clientes con reserva", "", "", "", ""))
            for c in clients:
                membership = c.get("plan_name") or "—"
                if c.get("membership_ends_at"):
                    membership += f" · vence {format_local_datetime(c['membership_ends_at'], '%d/%m/%Y')}"
                origin = "Horario fijo" if c.get("source") == "standing" else "Reserva manual"
                if c.get("without_reservation"):
                    origin += " (sin reserva generada)"
                rows.append((label, c.get("person_name"), c.get("phone") or "—",
                             c.get("seat_label") or "—", membership, origin))
        self.preview_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for col, value in enumerate(values):
                self.preview_table.setItem(r, col, _item(value))
        self._update_takeover_button()

    def _render_restore_preview(self, preview: Optional[Dict[str, Any]]) -> None:
        self._restore_preview = preview
        if not preview:
            self.restore_summary.setText("No se pudo obtener la vista previa.")
            self.restore_table.setRowCount(0)
            self._update_action_buttons()
            return
        text = preview.get("summary") or ""
        if preview.get("blockers"):
            text += "\n⚠ " + "\n⚠ ".join(preview["blockers"])
        self.restore_summary.setText(text)
        decisions = preview.get("decisions") or []
        self.restore_table.setRowCount(len(decisions))
        for r, d in enumerate(decisions):
            self.restore_table.setItem(r, 0, _item(d.get("person_name")))
            self.restore_table.setItem(
                r, 1, _item("Se reactiva" if d.get("restore") else "Sigue desplazada")
            )
            self.restore_table.setItem(r, 2, _item(d.get("reason")))
        self._update_action_buttons()

    def _render_linked_campaigns(self, event: Dict[str, Any]) -> None:
        linked = event.get("linked_campaigns") or []
        self.linked_label.setText(
            ", ".join(f"«{c['name']}» ({c['status']})" for c in linked) or "Ninguna campaña vinculada."
        )

    # ================================================================ options
    def _apply_options(self, options: Optional[Dict[str, Any]]) -> None:
        if not options:
            return
        self._options = options
        self.venue_combo.blockSignals(True)
        self.venue_combo.clear()
        for venue in options.get("venues") or []:
            self.venue_combo.addItem(venue.get("name") or f"Sede {venue['id']}", venue["id"])
        self.venue_combo.blockSignals(False)
        self.instructor_combo.clear()
        self.instructor_combo.addItem("Sin instructora", None)
        for person in options.get("instructors") or []:
            self.instructor_combo.addItem(person["name"], person["id"])
        self.class_type_combo.clear()
        self.class_type_combo.addItem("—", None)
        for ctype in options.get("class_types") or []:
            self.class_type_combo.addItem(ctype["name"], ctype["id"])
        self.timezone_label.setText(options.get("default_timezone") or _DEFAULT_TZ)
        if self._detail:
            self._fill_form(self._detail["event"])
        else:
            self._on_venue_changed()

    def _apply_campaigns(self, campaigns: List[Dict[str, Any]]) -> None:
        self._campaigns = list(campaigns or [])
        self.campaign_combo.clear()
        for campaign in self._campaigns:
            label = f"{campaign['name']} ({campaign.get('status')})"
            self.campaign_combo.addItem(label, int(campaign["id"]))

    def _venue_seats(self, venue_id: Optional[int]) -> List[Dict[str, Any]]:
        for venue in (self._options or {}).get("venues") or []:
            if venue["id"] == venue_id:
                return venue.get("seats") or []
        return []

    def _on_venue_changed(self, *_args) -> None:
        checked = None
        if self._detail and not self._creating:
            event = self._detail["event"]
            if event.get("venue_id") == self.venue_combo.currentData():
                checked = {s["seat_id"] for s in event.get("seats") or []}
        self._fill_seats(self._venue_seats(self.venue_combo.currentData()), checked)

    def _fill_seats(self, seats: List[Dict[str, Any]], checked: Optional[set]) -> None:
        self.seats_list.clear()
        for seat in seats:
            item = QListWidgetItem(seat["label"])
            item.setData(Qt.ItemDataRole.UserRole, seat["seat_id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            is_checked = checked is None or seat["seat_id"] in checked
            item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.seats_list.addItem(item)

    def _check_all_seats(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.seats_list.count()):
            self.seats_list.item(i).setCheckState(state)

    def _checked_seat_ids(self) -> List[int]:
        return [
            int(self.seats_list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.seats_list.count())
            if self.seats_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    # ================================================================== form
    def _fill_form(self, event: Dict[str, Any]) -> None:
        self.name_edit.setText(event.get("name") or "")
        self.description_edit.setPlainText(event.get("description") or "")
        self.includes_edit.setPlainText(event.get("includes") or "")
        self.address_edit.setText(event.get("address") or "")
        self._set_combo(self.venue_combo, event.get("venue_id"))
        self._set_combo(self.instructor_combo, event.get("instructor_id"))
        self._set_combo(self.class_type_combo, event.get("class_type_id"))
        local_date = event.get("local_date")
        if local_date:
            self.date_edit.setDate(QDate.fromString(local_date, "yyyy-MM-dd"))
        if event.get("local_start_time"):
            self.start_edit.setTime(QTime.fromString(event["local_start_time"], "HH:mm"))
        end = event.get("local_end_time")
        self.end_unknown.setChecked(end is None)
        if end:
            self.end_edit.setTime(QTime.fromString(end, "HH:mm"))
        self.timezone_label.setText(event.get("timezone") or _DEFAULT_TZ)
        self.price_spin.setValue(float(event.get("price") or 0))
        capacity = event.get("capacity")
        self.capacity_unknown.setChecked(capacity is None)
        if capacity:
            self.capacity_spin.setValue(int(capacity))
        self.hold_spin.setValue(int(event.get("hold_minutes") or 30))
        self._fill_seats(
            self._venue_seats(event.get("venue_id")) or event.get("seats") or [],
            {s["seat_id"] for s in event.get("seats") or []},
        )

    @staticmethod
    def _set_combo(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _start_new_event(self) -> None:
        self._creating = True
        self._detail = None
        self.events_table.clearSelection()
        self._set_detail_enabled(True)
        self.detail_tabs.setCurrentIndex(0)
        self.name_edit.clear()
        self.description_edit.clear()
        self.includes_edit.clear()
        self.address_edit.clear()
        if self.venue_combo.count():
            self.venue_combo.setCurrentIndex(0)
        self.instructor_combo.setCurrentIndex(0)
        self.class_type_combo.setCurrentIndex(0)
        start_day = date.today() + timedelta(days=7)
        self.date_edit.setDate(QDate(start_day.year, start_day.month, start_day.day))
        self.start_edit.setTime(QTime(19, 0))
        self.end_edit.setTime(QTime(20, 0))
        self.end_unknown.setChecked(False)
        self.price_spin.setValue(0)
        self.capacity_unknown.setChecked(True)
        self.hold_spin.setValue(30)
        self._on_venue_changed()
        self.status_label.setText(
            "<b>Nuevo evento</b> · se guardará como borrador; el asistente no lo verá hasta "
            "que lo publiques."
        )
        for table in (self.orders_table, self.displaced_table, self.takeovers_table, self.preview_table):
            table.setRowCount(0)
        self._update_action_buttons()

    def _form_data(self) -> Dict[str, Any]:
        qdate = self.date_edit.date()
        data: Dict[str, Any] = {
            "name": self.name_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "includes": self.includes_edit.toPlainText().strip(),
            "address": self.address_edit.text().strip(),
            "venue_id": self.venue_combo.currentData(),
            "class_type_id": self.class_type_combo.currentData(),
            "instructor_id": self.instructor_combo.currentData(),
            "timezone": self.timezone_label.text() or _DEFAULT_TZ,
            "local_date": f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}",
            "start_time": self.start_edit.time().toString("HH:mm"),
            "end_time": None if self.end_unknown.isChecked() else self.end_edit.time().toString("HH:mm"),
            "price": float(self.price_spin.value()),
            "capacity": None if self.capacity_unknown.isChecked() else int(self.capacity_spin.value()),
            "seat_ids": self._checked_seat_ids(),
            "hold_minutes": int(self.hold_spin.value()),
        }
        return data

    # ================================================================ actions
    def _save_event(self) -> None:
        data = self._form_data()
        if not data["name"]:
            show_error(self, "El evento necesita un nombre.", title=_TITLE)
            return
        if data["venue_id"] is None:
            show_error(self, "Selecciona la sede.", title=_TITLE)
            return
        event_id = self._current_event_id()
        if self._creating or event_id is None:
            self.controller.create_event(data)
        else:
            self.controller.update_event(event_id, data)

    def _publish(self) -> None:
        event_id = self._current_event_id()
        if event_id is None:
            return
        if not show_confirmation(
            self,
            "Al publicar, el asistente de WhatsApp podrá vender este evento con Mercado Pago. "
            "¿Publicar?",
            title=_TITLE,
            ok_text="Publicar",
        ):
            return
        self.controller.publish_event(event_id)

    def _unpublish(self) -> None:
        event_id = self._current_event_id()
        if event_id is not None and show_confirmation(
            self, "El evento dejará de venderse y volverá a borrador. ¿Continuar?",
            title=_TITLE, ok_text="Volver a borrador",
        ):
            self.controller.unpublish_event(event_id)

    def _cancel_event(self) -> None:
        event_id = self._current_event_id()
        if event_id is None:
            return
        reason, ok = QInputDialog.getText(
            self,
            _TITLE,
            "Al cancelar: los lugares apartados se liberan, las entradas pagadas quedan «por "
            "reembolsar» (lo haces tú desde Participantes) y las clases sustituidas siguen "
            "desplazadas hasta que restituyas el horario. No se envía ningún mensaje.\n\n"
            "Motivo de la cancelación:",
        )
        if ok and reason.strip():
            self.controller.cancel_event(event_id, reason.strip())

    def _load_takeover_preview(self) -> None:
        event_id = self._current_event_id()
        if event_id is not None:
            self.controller.load_takeover_preview(event_id)

    def _apply_takeover(self) -> None:
        event_id = self._current_event_id()
        preview = self._takeover_preview or {}
        session_ids = preview.get("pending_session_ids") or []
        if event_id is None or not session_ids or not self.takeover_confirm.isChecked():
            return
        if not show_confirmation(
            self,
            f"Se sustituirán {len(session_ids)} clase(s) y {preview.get('affected_clients', 0)} "
            "cliente(s) quedarán desplazados. Sus reservas y membresías se conservan y no se les "
            "envía ningún mensaje. ¿Aplicar la sustitución?",
            title=_TITLE,
            ok_text="Aplicar sustitución",
        ):
            return
        self.controller.apply_takeover(event_id, session_ids)

    def _load_restore_preview(self) -> None:
        event_id = self._current_event_id()
        if event_id is not None:
            self.controller.load_restore_preview(event_id)

    def _restore_schedule(self) -> None:
        event_id = self._current_event_id()
        if event_id is None or not self._restore_preview or self._restore_preview.get("blockers"):
            return
        if show_confirmation(
            self,
            (self._restore_preview.get("summary") or "") + "\n\n¿Restituir el horario regular?",
            title=_TITLE,
            ok_text="Restituir",
        ):
            self.controller.restore_schedule(event_id)

    def _selected_row_id(self, table: QTableWidget) -> Optional[int]:
        rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not rows:
            return None
        item = table.item(rows[0].row(), 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return int(value) if value is not None else None

    def _add_participant(self) -> None:
        event = (self._detail or {}).get("event")
        if not event:
            return
        free = [s for s in event.get("seats") or [] if s.get("status") == "free"]
        dialog = ParticipantDialog(self, free_seats=free, price=float(event.get("price") or 0))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.data()
        data["event_id"] = event["id"]
        self.controller.add_participant(data)

    def _cancel_order(self) -> None:
        order_id = self._selected_row_id(self.orders_table)
        if order_id is None:
            show_info(self, "Selecciona una compra en la tabla.", title=_TITLE)
            return
        if show_confirmation(
            self, "Se cancela la compra no pagada y su bicicleta queda libre. ¿Continuar?",
            title=_TITLE, ok_text="Cancelar compra", cancel_text="Volver",
        ):
            self.controller.cancel_order(order_id, "Cancelado por el personal")

    def _refund_order(self) -> None:
        order_id = self._selected_row_id(self.orders_table)
        if order_id is None:
            show_info(self, "Selecciona una entrada pagada en la tabla.", title=_TITLE)
            return
        reason, ok = QInputDialog.getText(
            self, _TITLE,
            "Si se pagó con Mercado Pago se devuelve automáticamente; si fue en efectivo, "
            "tarjeta o transferencia, confirma que ya devolviste el dinero.\n\nMotivo:",
        )
        if ok:
            self.controller.refund_order(order_id, reason.strip() or "Reembolso solicitado")

    def _link_campaign(self, link: bool) -> None:
        event_id = self._current_event_id()
        campaign_id = self.campaign_combo.currentData()
        if event_id is None or campaign_id is None:
            return
        self.controller.link_campaign(int(campaign_id), event_id if link else None)

    def _register_notice(self) -> None:
        displacement_id = self._selected_row_id(self.displaced_table)
        if displacement_id is None:
            show_info(self, "Selecciona un cliente en la tabla.", title=_TITLE)
            return
        dialog = FollowUpDialog(self, mode="notice")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            payload = dialog.data()
            payload["displacement_id"] = displacement_id
            self.controller.update_follow_up(payload)

    def _register_compensation(self) -> None:
        displacement_id = self._selected_row_id(self.displaced_table)
        if displacement_id is None:
            show_info(self, "Selecciona un cliente en la tabla.", title=_TITLE)
            return
        dialog = FollowUpDialog(self, mode="compensation")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            payload = dialog.data()
            payload["displacement_id"] = displacement_id
            self.controller.update_follow_up(payload)

    def _reopen_follow_up(self) -> None:
        displacement_id = self._selected_row_id(self.displaced_table)
        if displacement_id is not None:
            self.controller.update_follow_up({"displacement_id": displacement_id, "resolved": False})

    # ================================================================ state
    def _on_event_selected(self) -> None:
        event_id = self._current_list_selection()
        if event_id is not None:
            self._creating = False
            self.controller.load_event(event_id)

    def _current_list_selection(self) -> Optional[int]:
        return self._selected_row_id(self.events_table)

    def _current_event_id(self) -> Optional[int]:
        if self._creating:
            return None
        if self._detail and self._detail.get("event"):
            return int(self._detail["event"]["id"])
        return self._current_list_selection()

    def _set_detail_enabled(self, enabled: bool) -> None:
        self.detail_tabs.setEnabled(enabled)

    def _invalidate_takeover_preview(self) -> None:
        self._takeover_preview = None
        self.takeover_confirm.setChecked(False)
        self.preview_table.setRowCount(0)
        self.preview_summary.setText("Revisa la vista previa antes de aplicar la sustitución.")
        self._update_takeover_button()

    def _invalidate_restore_preview(self) -> None:
        self._restore_preview = None
        self.restore_table.setRowCount(0)
        self.restore_summary.setText("—")

    def _update_takeover_button(self) -> None:
        preview = self._takeover_preview or {}
        ready = bool(preview.get("pending_session_ids")) and not preview.get("blockers")
        self.takeover_confirm.setEnabled(ready)
        self.apply_takeover_btn.setEnabled(ready and self.takeover_confirm.isChecked())

    def _update_action_buttons(self) -> None:
        event = (self._detail or {}).get("event") or {}
        status = event.get("status")
        existing = not self._creating and bool(event)
        open_event = status in ("draft", "published")
        self.publish_btn.setEnabled(existing and status == "draft" and not event.get("publish_blockers"))
        self.unpublish_btn.setEnabled(existing and status == "published")
        self.cancel_event_btn.setEnabled(existing and open_event)
        self.preview_btn.setEnabled(existing and open_event)
        self.restore_preview_btn.setEnabled(existing and status in ("draft", "canceled"))
        restore_ready = bool(self._restore_preview) and not (self._restore_preview or {}).get("blockers")
        self.restore_btn.setEnabled(existing and restore_ready)
        self.add_participant_btn.setEnabled(existing and open_event)
        self.cancel_order_btn.setEnabled(existing)
        self.refund_btn.setEnabled(existing)
        self.link_btn.setEnabled(existing)
        self.unlink_btn.setEnabled(existing)
        for btn in (self.notice_btn, self.compensation_btn, self.reopen_btn):
            btn.setEnabled(existing)


class ParticipantDialog(QDialog):
    """Registrar un participante que pagó en recepción o va como cortesía."""

    def __init__(self, parent: QWidget, *, free_seats: List[Dict[str, Any]], price: float) -> None:
        super().__init__(parent)
        self.setWindowTitle("Registrar participante")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        layout.addRow("Nombre completo", self.name_edit)
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("10 dígitos")
        layout.addRow("Teléfono", self.phone_edit)
        self.method_combo = QComboBox()
        for code, label in PAYMENT_METHODS:
            self.method_combo.addItem(label, code)
        layout.addRow("Pago", self.method_combo)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 100000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setPrefix("$ ")
        self.amount_spin.setValue(price)
        layout.addRow("Importe", self.amount_spin)
        self.seat_combo = QComboBox()
        self.seat_combo.addItem("Asignar automáticamente", None)
        for seat in free_seats:
            self.seat_combo.addItem(seat["label"], seat["seat_id"])
        layout.addRow("Bicicleta", self.seat_combo)
        self.notes_edit = QLineEdit()
        layout.addRow("Notas", self.notes_edit)
        note = QLabel("Se registra el pago en Finanzas; no se crea ni modifica ninguna membresía.")
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        if not self.name_edit.text().strip() or not self.phone_edit.text().strip():
            show_error(self, "Nombre y teléfono son obligatorios.", title="Registrar participante")
            return
        self.accept()

    def data(self) -> Dict[str, Any]:
        method = self.method_combo.currentData()
        return {
            "participant_name": self.name_edit.text().strip(),
            "participant_phone": self.phone_edit.text().strip(),
            "payment_method": method,
            "amount": None if method == "courtesy" else float(self.amount_spin.value()),
            "seat_id": self.seat_combo.currentData(),
            "notes": self.notes_edit.text().strip() or None,
        }


class FollowUpDialog(QDialog):
    """Registrar el aviso o la compensación de un cliente desplazado."""

    def __init__(self, parent: QWidget, *, mode: str) -> None:
        super().__init__(parent)
        self._mode = mode
        self.setWindowTitle("Registrar aviso" if mode == "notice" else "Registrar compensación")
        layout = QFormLayout(self)
        if mode == "notice":
            self.channel_combo = QComboBox()
            self.channel_combo.addItems(NOTICE_CHANNELS)
            layout.addRow("Canal", self.channel_combo)
            self.notes_edit = QLineEdit()
            layout.addRow("Notas", self.notes_edit)
            hint = QLabel("Se registra con la fecha y hora actuales y tu usuario.")
        else:
            self.type_combo = QComboBox()
            for code, label in COMPENSATIONS:
                self.type_combo.addItem(label, code)
            layout.addRow("Compensación", self.type_combo)
            self.notes_edit = QLineEdit()
            self.notes_edit.setPlaceholderText("Ej. reposición el lunes 2/11 a las 19:00")
            layout.addRow("Detalle", self.notes_edit)
            self.resolve_check = QCheckBox("Marcar como resuelto")
            self.resolve_check.setChecked(True)
            layout.addRow(self.resolve_check)
            hint = QLabel(
                "Solo se registra la decisión: aplica la extensión o reposición en la membresía "
                "o en Clases como lo harías normalmente."
            )
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def data(self) -> Dict[str, Any]:
        if self._mode == "notice":
            return {
                "notified": True,
                "notification_channel": self.channel_combo.currentText(),
                "notification_notes": self.notes_edit.text().strip() or None,
            }
        return {
            "compensation_type": self.type_combo.currentData(),
            "compensation_notes": self.notes_edit.text().strip() or None,
            "resolved": True if self.resolve_check.isChecked() else None,
        }
