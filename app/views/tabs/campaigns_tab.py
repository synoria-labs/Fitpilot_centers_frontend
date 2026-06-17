"""Vista de la pestaña Campañas — difusión de marketing por WhatsApp con seguimiento.

Permite crear campañas de recaptura (socios vencidos / por vencer / activos), segmentar la
audiencia con un constructor de predicados, elegir una plantilla aprobada de Meta y mapear sus
variables, previsualizar el tamaño de la audiencia, enviar (con prueba en seco) o programar, y
ver un panel de resultados (entregados / leídos / conversiones / ingreso recuperado).
Todo vía el módulo GraphQL ``campaigns`` del backend, reutilizando la infraestructura de WhatsApp.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, QDateTime, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox, QTextEdit,
    QFormLayout, QGroupBox, QScrollArea, QFrame, QRadioButton, QButtonGroup,
    QDateTimeEdit, QHeaderView,
)

from ...core import container, get_logger
from ...controllers.campaigns_controller import CampaignsController
from ...utils.dialog_helpers import show_error, show_info, show_confirmation
from ..screen_style import screen_qss
from ..table_widget_helpers import configure_table_widget
from .whatsapp import theme

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

_STATUS_LABELS = {
    "draft": "Borrador", "scheduled": "Programada", "sending": "Enviando",
    "paused": "Pausada", "completed": "Completada", "canceled": "Cancelada",
}
_MEMBERSHIP_STATES = [("expired", "Vencidos"), ("active", "Activos"), ("pending", "Pendientes")]


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


def _body_placeholder_count(components: Optional[List[Any]]) -> int:
    for comp in components or []:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
            indices = [int(m) for m in _PLACEHOLDER_RE.findall(str(comp.get("text") or ""))]
            return max(indices) if indices else 0
    return 0


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

        self._catalog: Dict[str, Any] = {"objectives": [], "predicates": [], "variables": []}
        self._templates: List[Dict[str, Any]] = []
        self._variables: List[Dict[str, Any]] = []
        self._campaigns_by_id: Dict[int, Dict[str, Any]] = {}
        self._editing_id: Optional[int] = None
        self._param_combos: List[QComboBox] = []

        self._build_ui()
        self._connect_controller()
        self.controller.load_catalog()
        self.controller.load_templates()
        self.controller.load_campaigns()

    # ================================================================== UI
    def _build_ui(self) -> None:
        self.setObjectName("campTab")
        self.setStyleSheet(screen_qss("camp"))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("campHeader")
        h = QVBoxLayout(header)
        h.setContentsMargins(20, 16, 14, 12)
        h.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        title = QLabel("Campañas")
        title.setObjectName("campTitle")
        header_row.addWidget(title)
        header_row.addStretch()

        self.new_btn = QPushButton("Nueva campaña")
        _style_action_button(self.new_btn, "fa5s.plus")
        self.new_btn.clicked.connect(self._on_new_clicked)
        header_row.addWidget(self.new_btn)

        self.refresh_btn = QPushButton("Actualizar")
        _style_action_button(self.refresh_btn, "fa5s.sync")
        self.refresh_btn.clicked.connect(lambda: self.controller.load_campaigns())
        header_row.addWidget(self.refresh_btn)
        h.addLayout(header_row)
        hint = QLabel(
            "Crea campañas de difusión por WhatsApp para recapturar socios (vencidos, por vencer) "
            "y mide entregas, lecturas y conversiones (pagos en la ventana). Reutiliza tus "
            "plantillas aprobadas de Meta."
        )
        hint.setObjectName("campHint")
        hint.setWordWrap(True)
        h.addWidget(hint)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("campSplitter")
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("campListPane")
        v = QVBoxLayout(panel)
        v.setContentsMargins(20, 16, 12, 14)
        v.setSpacing(10)

        list_title = QLabel("Campañas")
        list_title.setObjectName("campPanelTitle")
        v.addWidget(list_title)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("campTable")
        self.table.setHorizontalHeaderLabels(["Nombre", "Objetivo", "Estado", "Enviados", "Conv."])
        configure_table_widget(self.table)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        v.addWidget(self.table, 1)
        return panel

    def _build_editor_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("campConfigScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("campConfigPane")
        v = QVBoxLayout(body)
        v.setContentsMargins(14, 16, 20, 14)
        v.setSpacing(12)

        # --- Datos básicos
        basics = QGroupBox("Objetivo y nombre")
        basics.setObjectName("campGroup")
        bf = QFormLayout(basics)
        bf.setContentsMargins(10, 10, 10, 10)
        bf.setHorizontalSpacing(10)
        bf.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        bf.addRow("Nombre", self.name_edit)
        self.objective_combo = QComboBox()
        bf.addRow("Objetivo", self.objective_combo)
        self.description_edit = QLineEdit()
        bf.addRow("Descripción", self.description_edit)
        v.addWidget(basics)

        # --- Audiencia
        aud = QGroupBox("Audiencia (socios)")
        aud.setObjectName("campGroup")
        af = QVBoxLayout(aud)
        af.setContentsMargins(10, 10, 10, 10)
        af.setSpacing(8)
        states = QHBoxLayout()
        states.addWidget(QLabel("Estado:"))
        self.state_checks: Dict[str, QCheckBox] = {}
        for key, label in _MEMBERSHIP_STATES:
            cb = QCheckBox(label)
            if key == "expired":
                cb.setChecked(True)
            self.state_checks[key] = cb
            states.addWidget(cb)
        states.addStretch()
        af.addLayout(states)

        end_row = QHBoxLayout()
        self.end_range_check = QCheckBox("Vencimiento entre")
        self.end_range_check.setChecked(True)
        self.end_min_spin = QSpinBox()
        self.end_min_spin.setRange(-3650, 3650)
        self.end_min_spin.setValue(-90)
        self.end_max_spin = QSpinBox()
        self.end_max_spin.setRange(-3650, 3650)
        self.end_max_spin.setValue(-7)
        end_row.addWidget(self.end_range_check)
        end_row.addWidget(self.end_min_spin)
        end_row.addWidget(QLabel("y"))
        end_row.addWidget(self.end_max_spin)
        end_row.addWidget(QLabel("días desde hoy (negativo = pasado)"))
        end_row.addStretch()
        af.addLayout(end_row)

        plan_row = QHBoxLayout()
        plan_row.addWidget(QLabel("Planes (IDs, opc.):"))
        self.plan_edit = QLineEdit()
        self.plan_edit.setPlaceholderText("ej. 3,4")
        plan_row.addWidget(self.plan_edit)
        af.addLayout(plan_row)

        inact_row = QHBoxLayout()
        self.inactive_check = QCheckBox("Inactivo desde hace")
        self.inactive_spin = QSpinBox()
        self.inactive_spin.setRange(1, 3650)
        self.inactive_spin.setValue(30)
        inact_row.addWidget(self.inactive_check)
        inact_row.addWidget(self.inactive_spin)
        inact_row.addWidget(QLabel("días (sin reservas)"))
        inact_row.addStretch()
        af.addLayout(inact_row)

        prev_row = QHBoxLayout()
        self.preview_btn = QPushButton("Vista previa de audiencia")
        _style_action_button(self.preview_btn, "fa5s.eye")
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        self.preview_label = QLabel("—")
        prev_row.addWidget(self.preview_btn)
        prev_row.addWidget(self.preview_label)
        prev_row.addStretch()
        af.addLayout(prev_row)
        v.addWidget(aud)

        # --- Mensaje
        msg = QGroupBox("Mensaje")
        msg.setObjectName("campGroup")
        mf = QFormLayout(msg)
        mf.setContentsMargins(10, 10, 10, 10)
        mf.setHorizontalSpacing(10)
        mf.setVerticalSpacing(8)
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self._rebuild_param_mapping)
        mf.addRow("Plantilla", self.template_combo)
        self.mapping_container = QWidget()
        self.mapping_layout = QFormLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        mf.addRow("Variables", self.mapping_container)
        v.addWidget(msg)

        # --- Programación
        sched = QGroupBox("Programación")
        sched.setObjectName("campGroup")
        sf = QVBoxLayout(sched)
        sf.setContentsMargins(10, 10, 10, 10)
        sf.setSpacing(8)
        self.send_now_radio = QRadioButton("Enviar ahora (al pulsar Enviar)")
        self.send_now_radio.setChecked(True)
        self.schedule_radio = QRadioButton("Programar")
        group = QButtonGroup(self)
        group.addButton(self.send_now_radio)
        group.addButton(self.schedule_radio)
        sf.addWidget(self.send_now_radio)
        srow = QHBoxLayout()
        srow.addWidget(self.schedule_radio)
        self.schedule_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_dt.setCalendarPopup(True)
        srow.addWidget(self.schedule_dt)
        self.schedule_btn = QPushButton("Programar")
        _style_action_button(self.schedule_btn, "fa5s.clock")
        self.schedule_btn.clicked.connect(self._on_schedule_clicked)
        srow.addWidget(self.schedule_btn)
        srow.addStretch()
        sf.addLayout(srow)
        v.addWidget(sched)

        # --- Acciones
        actions = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        _style_primary_button(self.save_btn, "fa5s.save")
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.build_btn = QPushButton("Construir audiencia")
        _style_action_button(self.build_btn, "fa5s.users")
        self.build_btn.clicked.connect(self._on_build_clicked)
        self.dryrun_btn = QPushButton("Prueba (dry run)")
        _style_action_button(self.dryrun_btn, "fa5s.vial")
        self.dryrun_btn.clicked.connect(self._on_dryrun_clicked)
        self.send_btn = QPushButton("Enviar")
        _style_action_button(self.send_btn, "fa5s.paper-plane")
        self.send_btn.clicked.connect(self._on_send_clicked)
        for b in (self.save_btn, self.build_btn, self.dryrun_btn, self.send_btn):
            actions.addWidget(b)
        actions.addStretch()
        v.addLayout(actions)

        actions2 = QHBoxLayout()
        self.pause_btn = QPushButton("Pausar")
        _style_action_button(self.pause_btn, "fa5s.pause")
        self.pause_btn.clicked.connect(lambda: self._status_action("pause"))
        self.resume_btn = QPushButton("Reanudar")
        _style_action_button(self.resume_btn, "fa5s.play")
        self.resume_btn.clicked.connect(lambda: self._status_action("resume"))
        self.cancel_btn = QPushButton("Cancelar campaña")
        _style_action_button(self.cancel_btn, "fa5s.ban")
        self.cancel_btn.clicked.connect(lambda: self._status_action("cancel"))
        self.retry_btn = QPushButton("Reintentar fallidos")
        _style_action_button(self.retry_btn, "fa5s.redo")
        self.retry_btn.clicked.connect(lambda: self._status_action("retry"))
        for b in (self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn):
            actions2.addWidget(b)
        actions2.addStretch()
        v.addLayout(actions2)

        # --- Resultados
        results = QGroupBox("Resultados")
        results.setObjectName("campGroup")
        rf = QVBoxLayout(results)
        rf.setContentsMargins(10, 10, 10, 10)
        rf.setSpacing(8)
        self.metrics_label = QLabel("Selecciona o guarda una campaña para ver métricas.")
        self.metrics_label.setWordWrap(True)
        rf.addWidget(self.metrics_label)
        self.refresh_metrics_btn = QPushButton("Actualizar métricas")
        _style_action_button(self.refresh_metrics_btn, "fa5s.sync")
        self.refresh_metrics_btn.clicked.connect(self._on_refresh_metrics)
        rf.addWidget(self.refresh_metrics_btn, 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(results)

        v.addStretch()
        scroll.setWidget(body)
        return scroll

    def _connect_controller(self) -> None:
        c = self.controller
        c.campaigns_loaded.connect(self._on_campaigns)
        c.catalog_loaded.connect(self._on_catalog)
        c.templates_loaded.connect(self._on_templates)
        c.campaign_saved.connect(self._on_campaign_saved)
        c.action_result.connect(self._on_action)
        c.audience_previewed.connect(self._on_audience_previewed)
        c.metrics_loaded.connect(self._on_metrics)
        c.error_occurred.connect(self._on_error)
        c.loading_changed.connect(self._on_loading)

    # ============================================================== handlers
    def _on_loading(self, loading: bool) -> None:
        for b in (self.save_btn, self.send_btn, self.build_btn, self.dryrun_btn):
            b.setEnabled(not loading)

    def _on_catalog(self, catalog: Dict[str, Any]) -> None:
        self._catalog = catalog or {}
        self._variables = self._catalog.get("variables") or []
        self.objective_combo.clear()
        for obj in self._catalog.get("objectives") or []:
            self.objective_combo.addItem(obj.get("label", obj.get("key")), obj.get("key"))

    def _on_templates(self, templates: List[Dict[str, Any]]) -> None:
        self._templates = templates or []
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("— Selecciona —", None)
        for t in self._templates:
            self.template_combo.addItem(t.get("template_name", "?"), t.get("id"))
        self.template_combo.blockSignals(False)
        self._rebuild_param_mapping()

    def _on_campaigns(self, campaigns: List[Dict[str, Any]]) -> None:
        self._campaigns_by_id = {c["id"]: c for c in campaigns if c.get("id") is not None}
        self.table.setRowCount(0)
        obj_labels = {o.get("key"): o.get("label") for o in (self._catalog.get("objectives") or [])}
        for c in campaigns:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(c.get("name") or "")
            name_item.setData(Qt.ItemDataRole.UserRole, c.get("id"))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(obj_labels.get(c.get("objective"), c.get("objective") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(_STATUS_LABELS.get(c.get("status"), c.get("status") or "")))
            self.table.setItem(row, 3, QTableWidgetItem("—"))
            self.table.setItem(row, 4, QTableWidgetItem("—"))

    def _on_row_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        campaign_id = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        campaign = self._campaigns_by_id.get(campaign_id)
        if campaign:
            self._populate_editor(campaign)
            self.controller.load_metrics(campaign_id)

    def _on_campaign_saved(self, result: Dict[str, Any]) -> None:
        campaign = result.get("campaign")
        if campaign:
            self._editing_id = campaign.get("id")
            self._campaigns_by_id[campaign["id"]] = campaign
        show_info(self, "Campaña guardada.", title="Campañas")
        self.controller.load_campaigns()

    def _on_action(self, result: Dict[str, Any]) -> None:
        if result.get("dry_run"):
            preview = result.get("rendered_preview") or "(sin contenido)"
            show_info(
                self,
                f"Vista previa del mensaje:\n\n{preview}\n\n"
                f"Pendientes: {result.get('pending', 0)} · Omitidos: {result.get('skipped', 0)}",
                title="Prueba (dry run)",
            )
            return
        if "targeted" in result and result.get("targeted") is not None and not result.get("sent"):
            show_info(
                self,
                f"Audiencia construida.\nObjetivo: {result.get('targeted', 0)} · "
                f"Pendientes: {result.get('pending', 0)} · Omitidos: {result.get('skipped', 0)}",
                title="Audiencia",
            )
        else:
            show_info(self, "Acción ejecutada. El envío corre en segundo plano.", title="Campañas")
        self.controller.load_campaigns()
        if self._editing_id:
            self.controller.load_metrics(self._editing_id)

    def _on_audience_previewed(self, result: Dict[str, Any]) -> None:
        count = result.get("count", 0)
        sample = ", ".join(result.get("sample") or [])
        text = f"{count} socio(s)"
        if sample:
            text += f" — ej.: {sample}"
        self.preview_label.setText(text)

    def _on_metrics(self, m: Dict[str, Any]) -> None:
        self.metrics_label.setText(
            f"Objetivo: {m.get('targeted', 0)} · Pendientes: {m.get('pending', 0)} · "
            f"Enviados: {m.get('sent', 0)} · Entregados: {m.get('delivered', 0)} · "
            f"Leídos: {m.get('read', 0)} · Respuestas: {m.get('replied', 0)} · "
            f"Fallidos: {m.get('failed', 0)} · Omitidos: {m.get('skipped', 0)}\n"
            f"Conversiones: {m.get('converted', 0)} "
            f"(tasa {round(float(m.get('conversion_rate', 0)) * 100, 1)}%) · "
            f"Ingreso recuperado: ${m.get('revenue_recovered', 0):,.2f}"
        )

    def _on_error(self, message: str) -> None:
        show_error(self, message or "Ocurrió un error.", title="Campañas")

    # ============================================================== editor IO
    def _on_new_clicked(self) -> None:
        self.table.clearSelection()
        self._editing_id = None
        self.name_edit.clear()
        self.description_edit.clear()
        if self.objective_combo.count():
            self.objective_combo.setCurrentIndex(0)
        for key, cb in self.state_checks.items():
            cb.setChecked(key == "expired")
        self.end_range_check.setChecked(True)
        self.end_min_spin.setValue(-90)
        self.end_max_spin.setValue(-7)
        self.plan_edit.clear()
        self.inactive_check.setChecked(False)
        self.template_combo.setCurrentIndex(0)
        self.preview_label.setText("—")
        self.metrics_label.setText("Guarda la campaña para enviar y ver métricas.")

    def _populate_editor(self, campaign: Dict[str, Any]) -> None:
        self._editing_id = campaign.get("id")
        self.name_edit.setText(campaign.get("name") or "")
        self.description_edit.setText(campaign.get("description") or "")
        idx = self.objective_combo.findData(campaign.get("objective"))
        if idx >= 0:
            self.objective_combo.setCurrentIndex(idx)
        # Template
        tidx = self.template_combo.findData(campaign.get("template_id"))
        self.template_combo.setCurrentIndex(tidx if tidx >= 0 else 0)
        self._rebuild_param_mapping(saved_mapping=campaign.get("param_mapping") or [])
        # Audience
        self._apply_audience_spec(campaign.get("audience_spec") or {})

    def _apply_audience_spec(self, spec: Dict[str, Any]) -> None:
        predicates = spec.get("predicates") or []
        states = set()
        self.end_range_check.setChecked(False)
        self.inactive_check.setChecked(False)
        self.plan_edit.clear()
        for p in predicates:
            ptype = p.get("type")
            if ptype == "membership_status":
                states = set(p.get("in") or [])
            elif ptype == "membership_end_at" and p.get("days_from_now"):
                lo, hi = sorted(p["days_from_now"])
                self.end_range_check.setChecked(True)
                self.end_min_spin.setValue(int(lo))
                self.end_max_spin.setValue(int(hi))
            elif ptype == "plan_id" and p.get("in"):
                self.plan_edit.setText(",".join(str(x) for x in p["in"]))
            elif ptype == "last_activity" and p.get("op") == "older_than_days":
                self.inactive_check.setChecked(True)
                self.inactive_spin.setValue(int(p.get("value", 30)))
        for key, cb in self.state_checks.items():
            cb.setChecked(key in states)

    def _rebuild_param_mapping(self, *args, saved_mapping: Optional[List[str]] = None) -> None:
        # Clear existing combos
        while self.mapping_layout.rowCount():
            self.mapping_layout.removeRow(0)
        self._param_combos = []
        template_id = self.template_combo.currentData()
        template = next((t for t in self._templates if t.get("id") == template_id), None)
        count = _body_placeholder_count(template.get("components")) if template else 0
        for i in range(count):
            combo = QComboBox()
            for var in self._variables:
                combo.addItem(var.get("label", var.get("key")), var.get("key"))
            if saved_mapping and i < len(saved_mapping):
                vidx = combo.findData(saved_mapping[i])
                if vidx >= 0:
                    combo.setCurrentIndex(vidx)
            self._param_combos.append(combo)
            self.mapping_layout.addRow(f"{{{{{i + 1}}}}}", combo)

    def _collect_audience_spec(self) -> Dict[str, Any]:
        predicates: List[Dict[str, Any]] = []
        states = [k for k, cb in self.state_checks.items() if cb.isChecked()]
        if states:
            predicates.append({"type": "membership_status", "in": states})
        if self.end_range_check.isChecked():
            predicates.append({
                "type": "membership_end_at", "op": "between",
                "days_from_now": [self.end_min_spin.value(), self.end_max_spin.value()],
            })
        plan_text = self.plan_edit.text().strip()
        if plan_text:
            try:
                plan_ids = [int(x) for x in plan_text.replace(" ", "").split(",") if x]
                if plan_ids:
                    predicates.append({"type": "plan_id", "in": plan_ids})
            except ValueError:
                pass
        if self.inactive_check.isChecked():
            predicates.append({
                "type": "last_activity", "op": "older_than_days", "value": self.inactive_spin.value(),
            })
        return {"base": "members", "predicates": predicates}

    def _collect_payload(self) -> Dict[str, Any]:
        mapping = [c.currentData() for c in self._param_combos]
        return {
            "name": self.name_edit.text().strip(),
            "objective": self.objective_combo.currentData() or "win_back",
            "description": self.description_edit.text().strip() or None,
            "audienceSpec": self._collect_audience_spec(),
            "templateId": self.template_combo.currentData(),
            "paramMapping": mapping,
        }

    # ============================================================== actions
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

    def _on_build_clicked(self) -> None:
        cid = self._require_saved()
        if cid:
            self.controller.build_audience(cid)

    def _on_dryrun_clicked(self) -> None:
        cid = self._require_saved()
        if cid:
            self.controller.trigger_campaign(cid, dry_run=True)

    def _on_send_clicked(self) -> None:
        cid = self._require_saved()
        if not cid:
            return
        if show_confirmation(
            self, "¿Enviar esta campaña ahora a toda la audiencia?",
            title="Enviar campaña", ok_text="Enviar", cancel_text="Cancelar",
        ):
            self.controller.trigger_campaign(cid, dry_run=False)

    def _on_schedule_clicked(self) -> None:
        cid = self._require_saved()
        if not cid:
            return
        dt = self.schedule_dt.dateTime().toPython().astimezone()
        self.controller.schedule_campaign(cid, dt.isoformat(), self.schedule_radio.isChecked())

    def _on_preview_clicked(self) -> None:
        self.preview_label.setText("Calculando…")
        self.controller.preview_audience(self._collect_audience_spec())

    def _on_refresh_metrics(self) -> None:
        if self._editing_id:
            self.controller.load_metrics(self._editing_id)

    def _status_action(self, action: str) -> None:
        cid = self._require_saved()
        if not cid:
            return
        if action == "pause":
            self.controller.pause_campaign(cid)
        elif action == "resume":
            self.controller.resume_campaign(cid)
        elif action == "retry":
            self.controller.retry_failures(cid)
        elif action == "cancel":
            if show_confirmation(
                self, "¿Cancelar esta campaña?", title="Cancelar campaña",
                ok_text="Sí", cancel_text="No",
            ):
                self.controller.cancel_campaign(cid)
