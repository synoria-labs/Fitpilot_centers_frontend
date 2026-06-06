"""
Vista de la pestaña Notificaciones - Configuración de envíos automáticos por WhatsApp.

Asocia cada evento de negocio (bienvenida de nuevo registro, recordatorio de renovación,
confirmación de renovación, membresía vencida) con una plantilla aprobada de Meta y permite
mapear cada placeholder ({{1}}, {{2}}...) a una variable del socio (nombre, plan, fecha de
vencimiento, etc.). Para el recordatorio se configuran los días de aviso antes del vencimiento.

El barrido diario de recordatorios corre en el backend (APScheduler); aquí también hay un botón
para dispararlo manualmente ("Enviar recordatorios ahora").
"""
import re
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QLineEdit, QGroupBox, QSplitter, QListWidget, QListWidgetItem, QComboBox,
    QCheckBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...controllers.whatsapp_notifications_controller import WhatsAppNotificationsController
from ...utils.dialog_helpers import show_error, show_info

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def _template_body_text(components: Optional[List[Any]]) -> str:
    for comp in components or []:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
            text = comp.get("text")
            if isinstance(text, str):
                return text
    return ""


def _placeholder_count(body_text: str) -> int:
    indices = [int(m) for m in _PLACEHOLDER_RE.findall(body_text or "")]
    return max(indices) if indices else 0


class WhatsAppNotificationsTab(QWidget):
    """Vista para configurar notificaciones automáticas de WhatsApp."""

    event_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self._settings: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._catalog: Dict[str, Dict[str, Any]] = {}
        self._templates: List[Dict[str, Any]] = []
        self._templates_by_id: Dict[int, Dict[str, Any]] = {}
        self._current_event: Optional[str] = None
        self._var_combos: List[QComboBox] = []

        try:
            service = container.get("whatsapp_notifications_service")
        except Exception as exc:  # pragma: no cover - defensivo
            logger.error("No se pudo obtener whatsapp_notifications_service: %s", exc)
            raise
        self.controller = WhatsAppNotificationsController(service, self)

        self.setup_ui()
        self._connect_controller()
        self.controller.load_all()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title = QLabel("Notificaciones automáticas de WhatsApp")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.sweep_btn = QPushButton("📤 Enviar recordatorios ahora")
        self.sweep_btn.clicked.connect(self.on_run_sweep)
        header_layout.addWidget(self.sweep_btn)
        layout.addLayout(header_layout)

        hint = QLabel(
            "Asocia cada evento con una plantilla aprobada por Meta y elige qué variable "
            "ocupa cada {{1}}, {{2}}... El recordatorio de renovación se envía los días de "
            "aviso configurados antes del vencimiento."
        )
        hint.setStyleSheet("color: #3498db; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panel izquierdo - eventos
        left_panel = QGroupBox("Eventos")
        left_layout = QVBoxLayout(left_panel)
        self.events_list = QListWidget()
        self.events_list.itemClicked.connect(self.on_event_selected)
        left_layout.addWidget(self.events_list)
        splitter.addWidget(left_panel)

        # Panel derecho - configuración
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.event_title = QLabel("Selecciona un evento")
        self.event_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        right_layout.addWidget(self.event_title)

        self.enabled_check = QCheckBox("Activar el envío automático para este evento")
        self.enabled_check.stateChanged.connect(self._update_preview)
        right_layout.addWidget(self.enabled_check)

        template_group = QGroupBox("Plantilla")
        template_form = QFormLayout(template_group)
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self.on_template_changed)
        template_form.addRow("Plantilla aprobada:", self.template_combo)
        right_layout.addWidget(template_group)

        # Variables dinámicas
        self.vars_group = QGroupBox("Variables de la plantilla")
        self.vars_layout = QFormLayout(self.vars_group)
        right_layout.addWidget(self.vars_group)

        # Offsets (solo recordatorio)
        self.offsets_group = QGroupBox("Días de aviso antes del vencimiento")
        offsets_layout = QHBoxLayout(self.offsets_group)
        offsets_layout.addWidget(QLabel("Días (separados por coma):"))
        self.offsets_input = QLineEdit()
        self.offsets_input.setPlaceholderText("Ej: 7, 1")
        offsets_layout.addWidget(self.offsets_input)
        right_layout.addWidget(self.offsets_group)

        # Vista previa
        preview_label = QLabel("Vista previa (con valores de ejemplo):")
        preview_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(preview_label)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(120)
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
        right_layout.addWidget(self.preview_text)

        actions = QHBoxLayout()
        actions.addStretch()
        self.save_btn = QPushButton("💾 Guardar configuración")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save)
        actions.addWidget(self.save_btn)
        right_layout.addLayout(actions)
        right_layout.addStretch()

        splitter.addWidget(right_panel)
        splitter.setSizes([260, 740])
        layout.addWidget(splitter)

        self._set_form_enabled(False)

    def _connect_controller(self):
        self.controller.settings_loaded.connect(self._on_settings_loaded)
        self.controller.catalog_loaded.connect(self._on_catalog_loaded)
        self.controller.templates_loaded.connect(self._on_templates_loaded)
        self.controller.setting_saved.connect(self._on_setting_saved)
        self.controller.sweep_done.connect(self._on_sweep_done)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading_changed)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set_form_enabled(self, enabled: bool) -> None:
        for w in (
            self.enabled_check, self.template_combo, self.vars_group,
            self.offsets_group, self.save_btn,
        ):
            w.setEnabled(enabled)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _current_template(self) -> Optional[Dict[str, Any]]:
        template_id = self.template_combo.currentData()
        if template_id is None:
            return None
        return self._templates_by_id.get(template_id)

    def _event_variables(self, event_type: str) -> List[Dict[str, Any]]:
        cat = self._catalog.get(event_type) or {}
        return cat.get("variables") or []

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _populate_events_list(self) -> None:
        self.events_list.clear()
        for event_type in self._order:
            setting = self._settings.get(event_type, {})
            label = setting.get("label") or event_type
            item = QListWidgetItem(("✅ " if setting.get("enabled") else "⚪ ") + label)
            item.setData(Qt.ItemDataRole.UserRole, event_type)
            self.events_list.addItem(item)
            if event_type == self._current_event:
                self.events_list.setCurrentItem(item)

    def _render_event(self, event_type: Optional[str]) -> None:
        if not event_type or event_type not in self._settings:
            self._set_form_enabled(False)
            return
        setting = self._settings[event_type]
        self._set_form_enabled(True)
        self.event_title.setText(setting.get("label") or event_type)

        self.enabled_check.blockSignals(True)
        self.enabled_check.setChecked(bool(setting.get("enabled")))
        self.enabled_check.blockSignals(False)

        # Template combo
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("(Sin plantilla)", None)
        selected_index = 0
        for i, tpl in enumerate(self._templates, start=1):
            self.template_combo.addItem(
                f"{tpl.get('template_name')} ({tpl.get('template_language')})", tpl.get("id")
            )
            if tpl.get("id") == setting.get("template_id"):
                selected_index = i
        self.template_combo.setCurrentIndex(selected_index)
        self.template_combo.blockSignals(False)

        # Offsets (solo eventos que lo soportan)
        supports_offsets = bool(setting.get("supports_offsets"))
        self.offsets_group.setVisible(supports_offsets)
        if supports_offsets:
            offsets = setting.get("offsets_days") or []
            self.offsets_input.setText(", ".join(str(o) for o in offsets))

        self._rebuild_variable_rows()

    def _rebuild_variable_rows(self) -> None:
        self._clear_layout(self.vars_layout)
        self._var_combos = []

        tpl = self._current_template()
        count = _placeholder_count(_template_body_text(tpl.get("components"))) if tpl else 0
        variables = self._event_variables(self._current_event) if self._current_event else []

        if tpl is None:
            self.vars_group.setVisible(False)
            self._update_preview()
            return
        self.vars_group.setVisible(True)

        if count == 0:
            self.vars_layout.addRow(QLabel("Esta plantilla no tiene variables en el cuerpo."))
            self._update_preview()
            return

        setting = self._settings.get(self._current_event, {})
        saved_mapping = setting.get("param_mapping") or []

        for i in range(count):
            combo = QComboBox()
            for var in variables:
                combo.addItem(var.get("label") or var.get("key"), var.get("key"))
            # Preseleccionar desde el mapeo guardado
            if i < len(saved_mapping):
                idx = combo.findData(saved_mapping[i])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(self._update_preview)
            self._var_combos.append(combo)
            self.vars_layout.addRow(f"Variable {{{{{i + 1}}}}}:", combo)

        self._update_preview()

    def _collect_param_mapping(self) -> List[str]:
        return [c.currentData() for c in self._var_combos if c.currentData()]

    def _update_preview(self) -> None:
        tpl = self._current_template()
        if tpl is None:
            self.preview_text.setPlainText("(Selecciona una plantilla aprobada)")
            return
        body = _template_body_text(tpl.get("components"))
        # Mapa key -> sample para el evento actual
        samples = {v.get("key"): v.get("sample") for v in self._event_variables(self._current_event)}
        mapping = self._collect_param_mapping()

        def repl(match: "re.Match") -> str:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(mapping):
                return str(samples.get(mapping[idx], match.group(0)))
            return match.group(0)

        self.preview_text.setPlainText(_PLACEHOLDER_RE.sub(repl, body))

    # ------------------------------------------------------------------
    # Acciones de usuario
    # ------------------------------------------------------------------
    def on_event_selected(self, item: QListWidgetItem) -> None:
        event_type = item.data(Qt.ItemDataRole.UserRole)
        self._current_event = event_type
        self._render_event(event_type)
        self.event_selected.emit(event_type or "")

    def on_template_changed(self, _index: int) -> None:
        self._rebuild_variable_rows()

    def _parse_offsets(self) -> List[int]:
        raw = self.offsets_input.text().strip()
        if not raw:
            return []
        offsets: List[int] = []
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = int(part)
            except ValueError:
                continue
            if value > 0:
                offsets.append(value)
        return sorted(set(offsets))

    def on_save(self) -> None:
        if not self._current_event:
            return
        setting = self._settings.get(self._current_event, {})
        template_id = self.template_combo.currentData()
        enabled = self.enabled_check.isChecked()

        if enabled and template_id is None:
            show_error(self, "Selecciona una plantilla aprobada antes de activar el evento.")
            return

        data = {
            "event_type": self._current_event,
            "enabled": enabled,
            "template_id": template_id,
            "param_mapping": self._collect_param_mapping(),
            "offsets_days": self._parse_offsets() if setting.get("supports_offsets") else [],
        }
        self.controller.save_setting(data)

    def on_run_sweep(self) -> None:
        self.controller.run_sweep()

    # ------------------------------------------------------------------
    # Callbacks del controller
    # ------------------------------------------------------------------
    def _on_settings_loaded(self, settings: List[Dict[str, Any]]) -> None:
        self._settings = {s["event_type"]: s for s in (settings or []) if s.get("event_type")}
        self._order = [s["event_type"] for s in (settings or []) if s.get("event_type")]
        if self._current_event is None and self._order:
            self._current_event = self._order[0]
        self._populate_events_list()
        self._render_event(self._current_event)

    def _on_catalog_loaded(self, catalog: List[Dict[str, Any]]) -> None:
        self._catalog = {c["event_type"]: c for c in (catalog or []) if c.get("event_type")}
        if self._current_event:
            self._rebuild_variable_rows()

    def _on_templates_loaded(self, templates: List[Dict[str, Any]]) -> None:
        self._templates = [t for t in (templates or []) if t]
        self._templates_by_id = {t["id"]: t for t in self._templates if t.get("id") is not None}
        if self._current_event:
            self._render_event(self._current_event)

    def _on_setting_saved(self, setting: Optional[Dict[str, Any]]) -> None:
        if setting and setting.get("event_type"):
            self._settings[setting["event_type"]] = setting
            self._populate_events_list()
            if setting["event_type"] == self._current_event:
                self._render_event(self._current_event)
        show_info(self, "Configuración guardada.")

    def _on_sweep_done(self, result: Dict[str, Any]) -> None:
        show_info(
            self,
            "Barrido completado.\n"
            f"Enviados: {result.get('sent', 0)}  |  "
            f"Omitidos: {result.get('skipped', 0)}  |  "
            f"Fallidos: {result.get('failed', 0)}",
        )

    def _on_error(self, message: str) -> None:
        show_error(self, message)

    def _on_loading_changed(self, loading: bool) -> None:
        self.sweep_btn.setEnabled(not loading)
        self.save_btn.setEnabled(not loading and self._current_event is not None)
