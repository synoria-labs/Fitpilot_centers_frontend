"""Vista de la pestaña Campañas — difusión por WhatsApp con seguimiento.

Estructura: lista de campañas a la izquierda, asistente de tres pasos a la derecha
(audiencia → mensaje → revisar y enviar) y, cuando la campaña ya se envió, resultados con
desglose por destinatario.

Dos decisiones que cambian el uso diario respecto a la versión anterior:

* **Las acciones dependen del estado.** Antes los ocho botones estaban siempre visibles y
  habilitados, incluso en un borrador recién creado, y el usuario descubría qué se podía
  hacer por mensajes de error. Ahora un borrador ofrece guardar/probar/enviar y una campaña
  enviando ofrece pausar; nada más.
* **La audiencia se dice completa.** El conteo del segmento no es la audiencia: el envío aún
  descarta a quien no tiene WhatsApp, revocó el consentimiento o fue contactado hace poco.
  El paso 1 muestra ese desglose antes de enviar, no después.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ....controllers.campaigns_controller import CampaignsController
from ....core import container, get_logger
from ....utils.dialog_helpers import show_confirmation, show_error, show_info
from ...screen_style import screen_qss
from ...table_widget_helpers import configure_table_widget
from ...widgets.empty_state import EmptyStateWidget
from ..whatsapp import theme
from .panels import MetricsPanel, RecipientsTable
from .steps import AudienceStep, MessageStep, ReviewStep

logger = get_logger(__name__)

_STATUS_LABELS = {
    "draft": "Borrador",
    "scheduled": "Programada",
    "sending": "Enviando",
    "paused": "Pausada",
    "completed": "Completada",
    "canceled": "Cancelada",
}
_STATUS_COLORS = {
    "draft": "#95a5a6",
    "scheduled": "#3498db",
    "sending": "#f39c12",
    "paused": "#e67e22",
    "completed": "#2ecc71",
    "canceled": "#e74c3c",
}

# While a campaign is sending, refresh its metrics on this cadence instead of making the
# user press "Actualizar métricas" to find out whether anything is happening.
_LIVE_REFRESH_MS = 5000

_STEPS = ("Audiencia", "Mensaje", "Revisar y enviar")


def _set_button_icon(button: QPushButton, icon_name: str, *, primary: bool = False) -> None:
    color = "#ffffff" if primary else theme.palette_hex()
    button.setIcon(qta.icon(icon_name, color=color))
    button.setIconSize(QSize(14, 14))


def _style_action_button(button: QPushButton, icon_name: str) -> None:
    button.setObjectName("campActionButton")
    _set_button_icon(button, icon_name)


def _style_primary_button(button: QPushButton, icon_name: str) -> None:
    button.setObjectName("campPrimaryButton")
    _set_button_icon(button, icon_name, primary=True)


class CampaignsTab(QWidget):
    """Pestaña de campañas de marketing por WhatsApp."""

    def __init__(self):
        super().__init__()
        try:
            service = container.get("campaigns_service")
        except Exception as exc:  # pragma: no cover - defensivo
            logger.error("No se pudo obtener campaigns_service: %s", exc)
            raise
        self.controller = CampaignsController(service, self)

        self._catalog: Dict[str, Any] = {}
        self._campaigns_by_id: Dict[int, Dict[str, Any]] = {}
        self._metrics_by_id: Dict[int, Dict[str, Any]] = {}
        self._class_names: Dict[int, str] = {}
        self._editing_id: Optional[int] = None
        self._status: str = "draft"
        # Gate write actions on the capability rather than letting the server reject them
        # after the fact (same pattern as members_tab).
        try:
            self._can_send = bool(
                container.get("auth_service").has_capability("send_campaigns")
            )
        except Exception:  # noqa: BLE001 - defensivo: sin auth_service, no bloquear la vista
            self._can_send = True

        self._live_timer = QTimer(self)
        self._live_timer.setInterval(_LIVE_REFRESH_MS)
        self._live_timer.timeout.connect(self._refresh_live_metrics)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)  # debounce: one query per pause, not per click
        self._preview_timer.timeout.connect(self._request_preview)

        self._build_ui()
        self._connect_controller()
        self.controller.load_catalog()
        self.controller.load_templates()
        self.controller.load_classes()
        self.controller.load_plans()
        self.controller.load_campaigns()

    # ================================================================== UI
    def _build_ui(self) -> None:
        self.setObjectName("campTab")
        self.setStyleSheet(screen_qss("camp"))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("campSplitter")
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("campHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(20, 16, 14, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        title = QLabel("Campañas")
        title.setObjectName("campTitle")
        row.addWidget(title)
        row.addStretch()

        self.new_btn = QPushButton("Nueva campaña")
        _style_action_button(self.new_btn, "fa5s.plus")
        self.new_btn.clicked.connect(self._on_new_clicked)
        row.addWidget(self.new_btn)

        self.refresh_btn = QPushButton("Actualizar")
        _style_action_button(self.refresh_btn, "fa5s.sync")
        self.refresh_btn.clicked.connect(lambda: self.controller.load_campaigns())
        row.addWidget(self.refresh_btn)
        layout.addLayout(row)

        hint = QLabel(
            "Recaptura socios por WhatsApp segmentando por membresía y por las clases que "
            "más reservan. Mide entregas, lecturas y conversiones."
        )
        hint.setObjectName("campHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return header

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("campListPane")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 12, 14)
        layout.setSpacing(10)

        filters = QHBoxLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar campaña…")
        self.search_edit.textChanged.connect(self._apply_list_filters)
        filters.addWidget(self.search_edit, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos los estados", None)
        for key, label in _STATUS_LABELS.items():
            self.status_filter.addItem(label, key)
        self.status_filter.currentIndexChanged.connect(self._apply_list_filters)
        filters.addWidget(self.status_filter)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("campTable")
        self.table.setHorizontalHeaderLabels(
            ["Nombre", "Estado", "Enviados", "Conv.", "Ingreso"]
        )
        configure_table_widget(self.table)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyStateWidget(
            icon="📣",
            message="Aún no hay campañas",
            submessage="Crea una para recuperar socios vencidos por WhatsApp.",
            action_text="Nueva campaña",
            action_callback=self._on_new_clicked,
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)
        return panel

    def _build_editor_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("campConfigScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setObjectName("campConfigPane")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 16, 20, 14)
        layout.setSpacing(12)

        self.step_label = QLabel("")
        self.step_label.setObjectName("campPanelTitle")
        layout.addWidget(self.step_label)

        self.audience_step = AudienceStep()
        self.audience_step.spec_changed.connect(self._preview_timer.start)
        self.message_step = MessageStep()
        self.review_step = ReviewStep()

        self.steps = QStackedWidget()
        self.steps.addWidget(self.audience_step)
        self.steps.addWidget(self.message_step)
        self.steps.addWidget(self.review_step)
        layout.addWidget(self.steps)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Atrás")
        _style_action_button(self.back_btn, "fa5s.arrow-left")
        self.back_btn.clicked.connect(lambda: self._go_to_step(self.steps.currentIndex() - 1))
        self.next_btn = QPushButton("Siguiente")
        _style_action_button(self.next_btn, "fa5s.arrow-right")
        self.next_btn.clicked.connect(lambda: self._go_to_step(self.steps.currentIndex() + 1))
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch()

        self.save_btn = QPushButton("Guardar")
        _style_primary_button(self.save_btn, "fa5s.save")
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.dryrun_btn = QPushButton("Probar")
        _style_action_button(self.dryrun_btn, "fa5s.vial")
        self.dryrun_btn.clicked.connect(self._on_dryrun_clicked)
        self.schedule_btn = QPushButton("Programar")
        _style_action_button(self.schedule_btn, "fa5s.clock")
        self.schedule_btn.clicked.connect(self._on_schedule_clicked)
        self.send_btn = QPushButton("Enviar")
        _style_primary_button(self.send_btn, "fa5s.paper-plane")
        self.send_btn.clicked.connect(self._on_send_clicked)
        self.pause_btn = QPushButton("Pausar")
        _style_action_button(self.pause_btn, "fa5s.pause")
        self.pause_btn.clicked.connect(lambda: self.controller.pause_campaign(self._editing_id))
        self.resume_btn = QPushButton("Reanudar")
        _style_action_button(self.resume_btn, "fa5s.play")
        self.resume_btn.clicked.connect(lambda: self.controller.resume_campaign(self._editing_id))
        self.cancel_btn = QPushButton("Cancelar campaña")
        _style_action_button(self.cancel_btn, "fa5s.ban")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.retry_btn = QPushButton("Reintentar fallidos")
        _style_action_button(self.retry_btn, "fa5s.redo")
        self.retry_btn.clicked.connect(lambda: self.controller.retry_failures(self._editing_id))
        self.duplicate_btn = QPushButton("Duplicar")
        _style_action_button(self.duplicate_btn, "fa5s.copy")
        self.duplicate_btn.clicked.connect(self._on_duplicate_clicked)

        self._action_buttons = (
            self.save_btn, self.dryrun_btn, self.schedule_btn, self.send_btn,
            self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn,
            self.duplicate_btn,
        )
        for button in self._action_buttons:
            nav.addWidget(button)
        layout.addLayout(nav)

        self.metrics_panel = MetricsPanel()
        layout.addWidget(self.metrics_panel)
        self.recipients_table = RecipientsTable()
        self.recipients_table.status_filter.currentIndexChanged.connect(
            self._reload_recipients
        )
        layout.addWidget(self.recipients_table, 1)

        scroll.setWidget(body)
        self._go_to_step(0)
        return scroll

    def _connect_controller(self) -> None:
        c = self.controller
        c.campaigns_loaded.connect(self._on_campaigns)
        c.catalog_loaded.connect(self._on_catalog)
        c.templates_loaded.connect(self._on_templates)
        c.classes_loaded.connect(self._on_classes)
        c.plans_loaded.connect(self._on_plans)
        c.campaign_saved.connect(self._on_campaign_saved)
        c.action_result.connect(self._on_action)
        c.audience_previewed.connect(self._on_audience_previewed)
        c.metrics_loaded.connect(self._on_metrics)
        c.metrics_batch_loaded.connect(self._on_metrics_batch)
        c.recipients_loaded.connect(self._on_recipients)
        c.error_occurred.connect(self._on_error)
        c.loading_changed.connect(self._on_loading)

    # ============================================================== navigation
    def _go_to_step(self, index: int) -> None:
        index = max(0, min(index, self.steps.count() - 1))
        self.steps.setCurrentIndex(index)
        self.step_label.setText(f"Paso {index + 1} de {len(_STEPS)} · {_STEPS[index]}")
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < self.steps.count() - 1)
        if index == 2:
            self._refresh_summary()
        self._apply_state()

    def _refresh_summary(self) -> None:
        template = self.message_step.current_template()
        lines = [
            f"Audiencia: {self.audience_step.preview_label.text()}",
            f"Plantilla: {template.get('template_name') if template else '— sin elegir —'}",
        ]
        campaign = self._campaigns_by_id.get(self._editing_id) if self._editing_id else None
        if campaign:
            lines.append(
                f"Ventana de conversión: {campaign.get('conversion_window_days', 14)} días"
            )
        self.review_step.set_summary(lines)

    # ============================================================== state
    def _apply_state(self) -> None:
        """Show only the actions that make sense for the campaign's current status.

        The old tab showed all eight regardless, so "Pausar" sat enabled on a draft that had
        never been sent and the only feedback was a server error after clicking.
        """
        status = self._status if self._editing_id else "draft"
        saved = self._editing_id is not None
        on_review = self.steps.currentIndex() == 2

        visible = {
            "draft": {"save", "dryrun", "schedule", "send"},
            "scheduled": {"schedule", "cancel"},
            "sending": {"pause"},
            "paused": {"resume", "cancel"},
            "completed": {"duplicate", "retry"},
            "canceled": {"duplicate"},
        }.get(status, {"save"})

        if status == "draft" and not on_review:
            # Sending is a review-step decision; on the earlier steps only saving applies.
            visible = {"save"}

        mapping = {
            "save": self.save_btn,
            "dryrun": self.dryrun_btn,
            "schedule": self.schedule_btn,
            "send": self.send_btn,
            "pause": self.pause_btn,
            "resume": self.resume_btn,
            "cancel": self.cancel_btn,
            "retry": self.retry_btn,
            "duplicate": self.duplicate_btn,
        }
        for key, button in mapping.items():
            shown = key in visible
            button.setVisible(shown)
            needs_saved = key not in ("save",)
            button.setEnabled(self._can_send and (saved or not needs_saved))

        self.metrics_panel.setVisible(saved)
        self.recipients_table.setVisible(saved and status != "draft")

        if status == "sending":
            if not self._live_timer.isActive():
                self._live_timer.start()
        elif self._live_timer.isActive():
            self._live_timer.stop()

    def _refresh_live_metrics(self) -> None:
        if self._editing_id:
            self.controller.load_metrics(self._editing_id)
            self.controller.load_campaigns()

    # ============================================================== handlers
    def _on_loading(self, loading: bool) -> None:
        if loading:
            for button in self._action_buttons:
                button.setEnabled(False)
        else:
            self._apply_state()

    def _on_catalog(self, catalog: Dict[str, Any]) -> None:
        self._catalog = catalog or {}
        self.audience_step.set_objectives(self._catalog.get("objectives") or [])
        self.message_step.set_variables(self._catalog.get("variables") or [])

    def _on_templates(self, templates: List[Dict[str, Any]]) -> None:
        self.message_step.set_templates(templates or [])

    def _on_plans(self, plans: List[Dict[str, Any]]) -> None:
        self.audience_step.set_plans(plans or [])
        self._reapply_editing_spec()

    def _on_classes(self, payload: Dict[str, Any]) -> None:
        payload = payload or {}
        class_types = payload.get("class_types") or []
        self._class_names = {c.get("id"): c.get("name") or "" for c in class_types}
        self.recipients_table.set_class_names(self._class_names)
        self.audience_step.set_classes(class_types, payload.get("class_templates") or [])
        self._reapply_editing_spec()

    def _reapply_editing_spec(self) -> None:
        """Catalogs load asynchronously and can land after a campaign was selected."""
        if not self._editing_id:
            return
        campaign = self._campaigns_by_id.get(self._editing_id)
        if campaign:
            self.audience_step.apply_audience_spec(campaign.get("audience_spec") or {})

    def _on_campaigns(self, campaigns: List[Dict[str, Any]]) -> None:
        self._campaigns_by_id = {c["id"]: c for c in campaigns if c.get("id") is not None}
        self._rebuild_table()
        if self._campaigns_by_id:
            self.controller.load_metrics_batch(list(self._campaigns_by_id))
        if self._editing_id in self._campaigns_by_id:
            self._status = self._campaigns_by_id[self._editing_id].get("status") or "draft"
            self._apply_state()

    def _rebuild_table(self) -> None:
        self.table.setRowCount(0)
        campaigns = list(self._campaigns_by_id.values())
        self.empty_state.setVisible(not campaigns)
        self.table.setVisible(bool(campaigns))
        for campaign in campaigns:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(campaign.get("name") or "")
            name_item.setData(Qt.ItemDataRole.UserRole, campaign.get("id"))
            self.table.setItem(row, 0, name_item)

            status = campaign.get("status") or ""
            status_item = QTableWidgetItem(_STATUS_LABELS.get(status, status))
            color = _STATUS_COLORS.get(status)
            if color:
                status_item.setForeground(QColor(color))
            self.table.setItem(row, 1, status_item)

            metrics = self._metrics_by_id.get(campaign.get("id"))
            self.table.setItem(
                row, 2, QTableWidgetItem(str(metrics.get("sent", 0)) if metrics else "…")
            )
            self.table.setItem(
                row, 3, QTableWidgetItem(str(metrics.get("converted", 0)) if metrics else "…")
            )
            revenue = (
                f"${float(metrics.get('revenue_recovered', 0) or 0):,.0f}" if metrics else "…"
            )
            self.table.setItem(row, 4, QTableWidgetItem(revenue))
        self._restore_selection()
        self._apply_list_filters()

    def _restore_selection(self) -> None:
        """Keep the open campaign selected across a rebuild.

        The list refreshes every few seconds while a campaign sends; without this the row
        would deselect under the user's cursor mid-send."""
        if self._editing_id is None:
            return
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == self._editing_id:
                self.table.selectRow(row)
                break
        self.table.blockSignals(False)

    def _apply_list_filters(self, *_args) -> None:
        needle = (self.search_edit.text() or "").strip().lower()
        wanted_status = self.status_filter.currentData()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            campaign = self._campaigns_by_id.get(
                name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            )
            matches_text = not needle or needle in (campaign or {}).get("name", "").lower()
            matches_status = not wanted_status or (campaign or {}).get("status") == wanted_status
            self.table.setRowHidden(row, not (matches_text and matches_status))

    def _on_metrics_batch(self, batch: Dict[int, Dict[str, Any]]) -> None:
        self._metrics_by_id = batch or {}
        self._rebuild_table()

    def _on_row_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        campaign_id = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        campaign = self._campaigns_by_id.get(campaign_id)
        if not campaign:
            return
        self._populate_editor(campaign)
        self.controller.load_metrics(campaign_id)
        self._reload_recipients()

    def _populate_editor(self, campaign: Dict[str, Any]) -> None:
        self._editing_id = campaign.get("id")
        self._status = campaign.get("status") or "draft"
        self.audience_step.name_edit.setText(campaign.get("name") or "")
        self.audience_step.description_edit.setText(campaign.get("description") or "")
        index = self.audience_step.objective_combo.findData(campaign.get("objective"))
        if index >= 0:
            self.audience_step.objective_combo.setCurrentIndex(index)
        self.audience_step.apply_audience_spec(campaign.get("audience_spec") or {})
        self.message_step.select_template(
            campaign.get("template_id"), campaign.get("param_mapping") or []
        )
        self._apply_state()

    def _on_campaign_saved(self, result: Dict[str, Any]) -> None:
        campaign = result.get("campaign")
        if campaign:
            self._editing_id = campaign.get("id")
            self._status = campaign.get("status") or "draft"
            self._campaigns_by_id[campaign["id"]] = campaign
        show_info(self, "Campaña guardada.", title="Campañas")
        self.controller.load_campaigns()
        self._apply_state()

    def _on_action(self, result: Dict[str, Any]) -> None:
        if result.get("dry_run"):
            preview = result.get("rendered_preview") or "(sin contenido)"
            show_info(
                self,
                f"Vista previa del mensaje:\n\n{preview}\n\n"
                f"Pendientes: {result.get('pending', 0)} · Omitidos: {result.get('skipped', 0)}",
                title="Prueba",
            )
            return
        if result.get("deferred"):
            show_info(
                self,
                "La campaña quedó programada: hay destinatarios en horario de silencio y se "
                "enviarán en cuanto vuelva a estar permitido.",
                title="Campañas",
            )
        else:
            show_info(self, "Listo. El envío corre en segundo plano.", title="Campañas")
        self.controller.load_campaigns()
        if self._editing_id:
            self.controller.load_metrics(self._editing_id)

    def _on_audience_previewed(self, result: Dict[str, Any]) -> None:
        count = result.get("count", 0)
        reachable = result.get("reachable", count)
        skipped = result.get("skipped") or {}
        parts = [f"{reachable} recibirán"]
        for key, label in (
            ("no_phone", "sin WhatsApp"),
            ("no_consent", "sin consentimiento"),
            ("recency_block", "contactados hace poco"),
        ):
            if skipped.get(key):
                parts.append(f"{skipped[key]} {label}")
        text = " · ".join(parts)
        if reachable != count:
            text += f"  (segmento: {count})"
        sample = ", ".join(result.get("sample") or [])
        if sample:
            text += f" — ej.: {sample}"
        self.audience_step.set_preview_text(text)

    def _on_metrics(self, metrics: Dict[str, Any]) -> None:
        self.metrics_panel.set_metrics(metrics, sending=self._status == "sending")

    def _on_recipients(self, recipients: List[Dict[str, Any]]) -> None:
        self.recipients_table.set_recipients(recipients or [])

    def _on_error(self, message: str) -> None:
        show_error(self, message or "Ocurrió un error.", title="Campañas")

    # ============================================================== actions
    def _request_preview(self) -> None:
        self.audience_step.set_preview_text("Calculando…")
        self.controller.preview_audience(self.audience_step.audience_spec())

    def _reload_recipients(self, *_args) -> None:
        if self._editing_id:
            self.controller.load_recipients(
                self._editing_id, self.recipients_table.selected_status()
            )

    def _collect_payload(self) -> Dict[str, Any]:
        return {
            "name": self.audience_step.name_edit.text().strip(),
            "objective": self.audience_step.objective_combo.currentData() or "win_back",
            "description": self.audience_step.description_edit.text().strip() or None,
            "audienceSpec": self.audience_step.audience_spec(),
            "templateId": self.message_step.template_id(),
            "paramMapping": self.message_step.param_mapping(),
        }

    def _on_new_clicked(self) -> None:
        self.table.clearSelection()
        self._editing_id = None
        self._status = "draft"
        self.audience_step.name_edit.clear()
        self.audience_step.description_edit.clear()
        if self.audience_step.objective_combo.count():
            self.audience_step.objective_combo.setCurrentIndex(0)
        self.audience_step.apply_audience_spec({})
        for key, check in self.audience_step.state_checks.items():
            check.setChecked(key == "expired")
        self.audience_step.end_range_check.setChecked(True)
        self.message_step.select_template(None, [])
        self.metrics_panel.clear()
        self._go_to_step(0)

    def _on_save_clicked(self) -> None:
        payload = self._collect_payload()
        if not payload["name"]:
            show_error(self, "La campaña necesita un nombre.", title="Campañas")
            return
        if self._editing_id:
            self.controller.update_campaign(self._editing_id, payload)
        else:
            self.controller.create_campaign(payload)

    def _require_saved(self) -> Optional[int]:
        if not self._editing_id:
            show_error(self, "Guarda la campaña antes de continuar.", title="Campañas")
            return None
        return self._editing_id

    def _on_dryrun_clicked(self) -> None:
        campaign_id = self._require_saved()
        if campaign_id:
            self.controller.trigger_campaign(campaign_id, dry_run=True)

    def _on_send_clicked(self) -> None:
        campaign_id = self._require_saved()
        if not campaign_id:
            return
        audience = self.audience_step.preview_label.text()
        if show_confirmation(
            self,
            f"Se enviará a: {audience}\n\n¿Confirmas el envío?",
            title="Enviar campaña",
            ok_text="Enviar",
            cancel_text="Cancelar",
        ):
            self.controller.trigger_campaign(campaign_id, dry_run=False)

    def _on_schedule_clicked(self) -> None:
        campaign_id = self._require_saved()
        if not campaign_id:
            return
        if not self.review_step.is_scheduled():
            show_error(
                self, "Selecciona «Programar» para elegir fecha y hora.", title="Campañas"
            )
            return
        when = self.review_step.scheduled_at()
        # send_local_time is a send option, not the state of the schedule radio.
        self.controller.schedule_campaign(campaign_id, when.isoformat(), False)

    def _on_cancel_clicked(self) -> None:
        campaign_id = self._require_saved()
        if campaign_id and show_confirmation(
            self, "¿Cancelar esta campaña?", title="Cancelar campaña",
            ok_text="Sí", cancel_text="No",
        ):
            self.controller.cancel_campaign(campaign_id)

    def _on_duplicate_clicked(self) -> None:
        """Copy the current campaign into a fresh draft, ready to adjust and send again."""
        campaign = self._campaigns_by_id.get(self._editing_id) if self._editing_id else None
        if not campaign:
            return
        self._editing_id = None
        self._status = "draft"
        self.audience_step.name_edit.setText(f"{campaign.get('name') or 'Campaña'} (copia)")
        self.metrics_panel.clear()
        self._go_to_step(0)
        self._apply_state()

    def _on_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if item is None:
            return
        campaign_id = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        campaign = self._campaigns_by_id.get(campaign_id)
        if not campaign:
            return
        menu = QMenu(self)
        duplicate_action = menu.addAction("Duplicar")
        delete_action = None
        # The backend only allows deleting drafts and canceled campaigns; do not offer an
        # action that can only fail.
        if campaign.get("status") in ("draft", "canceled"):
            delete_action = menu.addAction("Eliminar")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen is None:
            return
        if chosen is duplicate_action:
            self._populate_editor(campaign)
            self._on_duplicate_clicked()
        elif delete_action is not None and chosen is delete_action:
            if show_confirmation(
                self,
                f"¿Eliminar «{campaign.get('name')}»?",
                title="Eliminar campaña",
                ok_text="Eliminar",
                cancel_text="Cancelar",
            ):
                self.controller.delete_campaign(campaign_id)
