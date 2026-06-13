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

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QLineEdit, QGroupBox, QSplitter, QListWidget, QListWidgetItem, QComboBox,
    QCheckBox, QFormLayout, QFileDialog, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor

from ...core import container, get_logger
from ...controllers.whatsapp_notifications_controller import WhatsAppNotificationsController
from ...utils.dialog_helpers import show_error, show_info
from .whatsapp import theme
from .whatsapp.template_preview_widget import TemplatePreviewWidget

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_HEADER_FORMAT_KIND = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}


def _template_body_text(components: Optional[List[Any]]) -> str:
    for comp in components or []:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
            text = comp.get("text")
            if isinstance(text, str):
                return text
    return ""


def _template_footer_text(components: Optional[List[Any]]) -> str:
    for comp in components or []:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "FOOTER":
            text = comp.get("text")
            if isinstance(text, str):
                return text
    return ""


def _placeholder_count(body_text: str) -> int:
    indices = [int(m) for m in _PLACEHOLDER_RE.findall(body_text or "")]
    return max(indices) if indices else 0


def _required_header_media_format(components: Optional[List[Any]]) -> Optional[str]:
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "HEADER":
            continue
        header_format = str(comp.get("format") or "").upper()
        if header_format in {"IMAGE", "VIDEO", "DOCUMENT"}:
            return header_format
    return None


def _style() -> str:
    secondary = theme.secondary_text_hex()
    return f"""
#notificationsTab {{ background-color: palette(window); }}
#notificationsTab QSplitter::handle {{ background-color: palette(mid); width: 1px; }}
#notifHeader {{
    background-color: palette(window);
    border-bottom: 1px solid palette(mid);
}}
QLabel#notifTitle {{
    color: palette(text);
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}}
QLabel#notifHint {{
    color: {secondary};
    font-size: 12px;
    background: transparent;
}}
QWidget#notifEventsPane, QWidget#notifConfigPane {{
    background-color: palette(window);
}}
QScrollArea#notifConfigScroll {{
    background-color: palette(window);
    border: none;
}}
QScrollArea#notifConfigScroll > QWidget > QWidget {{
    background-color: palette(window);
}}
QFrame#notifPreviewRail {{
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 6px;
}}
QLabel#notifPreviewRailTitle {{
    color: palette(text);
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}}
QLabel#notifPanelTitle {{
    color: palette(text);
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}}
QLabel#notifEventTitle {{
    color: palette(text);
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}}
QListWidget#notifEventsList {{
    background-color: palette(window);
    border: none;
    outline: 0;
}}
QListWidget#notifEventsList::item {{
    min-height: 34px;
    padding: 7px 12px;
    border-bottom: 1px solid palette(mid);
    color: palette(text);
}}
QListWidget#notifEventsList::item:hover {{
    background-color: palette(alternate-base);
}}
QListWidget#notifEventsList::item:selected {{
    background-color: palette(highlight);
    color: palette(highlighted-text);
}}
QGroupBox#notifGroup {{
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px;
    color: palette(text);
    font-weight: 600;
}}
QGroupBox#notifGroup::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {secondary};
}}
QComboBox, QLineEdit {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    min-height: 34px;
    padding: 0 10px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}}
QComboBox:focus, QLineEdit:focus {{
    border: 1px solid {theme.ACCENT};
}}
QComboBox:disabled, QLineEdit:disabled {{
    background-color: palette(window);
    color: palette(mid);
    border: 1px solid palette(mid);
}}
QComboBox QAbstractItemView {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    outline: 0;
}}
QCheckBox {{
    color: palette(text);
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background-color: palette(base);
}}
QCheckBox::indicator:checked {{
    background-color: {theme.ACCENT};
    border-color: {theme.ACCENT};
}}
QCheckBox:disabled {{
    color: palette(mid);
}}
QPushButton#notifActionButton {{
    background-color: transparent;
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton#notifActionButton:hover {{
    background-color: palette(alternate-base);
}}
QPushButton#notifActionButton:disabled {{
    color: palette(mid);
}}
QPushButton#notifPrimaryButton {{
    background-color: {theme.ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
}}
QPushButton#notifPrimaryButton:hover {{
    background-color: #06c191;
}}
QPushButton#notifPrimaryButton:disabled {{
    background-color: palette(mid);
    color: palette(window);
}}
"""


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
        self._media_assets_by_kind: Dict[str, List[Dict[str, Any]]] = {}
        self._media_assets_by_id: Dict[int, Dict[str, Any]] = {}
        self._pending_header_asset_id: Optional[int] = None

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
        self.setObjectName("notificationsTab")
        self.setStyleSheet(_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("notifHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 12)
        header_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        title = QLabel("Notificaciones automáticas de WhatsApp")
        title.setObjectName("notifTitle")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_row.addWidget(title)
        header_row.addStretch()
        self.sweep_btn = QPushButton("Enviar recordatorios ahora")
        self.sweep_btn.setObjectName("notifActionButton")
        self.sweep_btn.setIcon(qta.icon("fa5s.paper-plane", color=theme.palette_hex()))
        self.sweep_btn.setIconSize(QSize(14, 14))
        self.sweep_btn.clicked.connect(self.on_run_sweep)
        header_row.addWidget(self.sweep_btn)
        header_layout.addLayout(header_row)

        hint = QLabel(
            "Asocia cada evento con una plantilla aprobada por Meta y elige qué variable "
            "ocupa cada {{1}}, {{2}}... El recordatorio de renovación se envía los días de "
            "aviso configurados antes del vencimiento."
        )
        hint.setObjectName("notifHint")
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_panel.setObjectName("notifEventsPane")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 16, 12, 14)
        left_layout.setSpacing(10)
        events_title = QLabel("Eventos")
        events_title.setObjectName("notifPanelTitle")
        left_layout.addWidget(events_title)
        self.events_list = QListWidget()
        self.events_list.setObjectName("notifEventsList")
        self.events_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.events_list.setUniformItemSizes(True)
        self.events_list.itemClicked.connect(self.on_event_selected)
        left_layout.addWidget(self.events_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_panel.setObjectName("notifConfigPane")
        right_layout = QHBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 16, 20, 14)
        right_layout.setSpacing(12)

        config_scroll = QScrollArea()
        config_scroll.setObjectName("notifConfigScroll")
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QFrame.Shape.NoFrame)
        config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_container = QWidget()
        config_layout = QVBoxLayout(config_container)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(10)

        self.event_title = QLabel("Selecciona un evento")
        self.event_title.setObjectName("notifEventTitle")
        self.event_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        config_layout.addWidget(self.event_title)

        self.enabled_check = QCheckBox("Activar el envío automático para este evento")
        self.enabled_check.stateChanged.connect(self._update_preview)
        config_layout.addWidget(self.enabled_check)

        template_group = QGroupBox("Plantilla")
        template_group.setObjectName("notifGroup")
        template_form = QFormLayout(template_group)
        template_form.setContentsMargins(10, 10, 10, 10)
        template_form.setHorizontalSpacing(10)
        template_form.setVerticalSpacing(8)
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self.on_template_changed)
        template_form.addRow("Plantilla aprobada:", self.template_combo)
        config_layout.addWidget(template_group)

        self.vars_group = QGroupBox("Variables de la plantilla")
        self.vars_group.setObjectName("notifGroup")
        self.vars_layout = QFormLayout(self.vars_group)
        self.vars_layout.setContentsMargins(10, 10, 10, 10)
        self.vars_layout.setHorizontalSpacing(10)
        self.vars_layout.setVerticalSpacing(8)
        config_layout.addWidget(self.vars_group)

        self.header_media_group = QGroupBox("Media del encabezado")
        self.header_media_group.setObjectName("notifGroup")
        header_media_layout = QFormLayout(self.header_media_group)
        header_media_layout.setContentsMargins(10, 10, 10, 10)
        header_media_layout.setHorizontalSpacing(10)
        header_media_layout.setVerticalSpacing(8)
        self.default_header_media_label = QLabel("Sin media por defecto")
        self.default_header_media_label.setWordWrap(True)
        header_media_layout.addRow("Media por defecto:", self.default_header_media_label)
        self.use_header_override_check = QCheckBox("Usar media diferente para este evento")
        self.use_header_override_check.stateChanged.connect(self._on_header_override_toggled)
        header_media_layout.addRow("", self.use_header_override_check)
        asset_row = QWidget()
        asset_row_layout = QHBoxLayout(asset_row)
        asset_row_layout.setContentsMargins(0, 0, 0, 0)
        asset_row_layout.setSpacing(8)
        self.header_asset_combo = QComboBox()
        self.header_asset_combo.currentIndexChanged.connect(self._update_preview)
        asset_row_layout.addWidget(self.header_asset_combo, 1)
        self.upload_asset_btn = QPushButton("Subir media")
        self.upload_asset_btn.setObjectName("notifActionButton")
        self.upload_asset_btn.clicked.connect(self.on_upload_header_asset)
        asset_row_layout.addWidget(self.upload_asset_btn)
        header_media_layout.addRow("Asset:", asset_row)
        self.header_media_input = QLineEdit()
        self.header_media_input.setPlaceholderText("https://...")
        self.header_media_input.textChanged.connect(self._update_preview)
        header_media_layout.addRow("URL legacy HTTPS:", self.header_media_input)
        self.header_media_group.setVisible(False)
        config_layout.addWidget(self.header_media_group)

        self.offsets_group = QGroupBox("Días de aviso antes del vencimiento")
        self.offsets_group.setObjectName("notifGroup")
        offsets_layout = QHBoxLayout(self.offsets_group)
        offsets_layout.setContentsMargins(10, 10, 10, 10)
        offsets_layout.setSpacing(10)
        offsets_layout.addWidget(QLabel("Días (separados por coma):"))
        self.offsets_input = QLineEdit()
        self.offsets_input.setPlaceholderText("Ej: 7, 1")
        offsets_layout.addWidget(self.offsets_input)
        config_layout.addWidget(self.offsets_group)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()
        self.save_btn = QPushButton("Guardar configuración")
        self.save_btn.setObjectName("notifPrimaryButton")
        self.save_btn.setIcon(qta.icon("fa5s.save", color="#ffffff"))
        self.save_btn.setIconSize(QSize(14, 14))
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save)
        actions.addWidget(self.save_btn)
        config_layout.addStretch(1)
        config_layout.addLayout(actions)

        config_scroll.setWidget(config_container)

        preview_panel = QFrame()
        preview_panel.setObjectName("notifPreviewRail")
        preview_panel.setMinimumWidth(320)
        preview_panel.setMaximumWidth(380)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)
        preview_title = QLabel("Vista previa de la plantilla")
        preview_title.setObjectName("notifPreviewRailTitle")
        preview_layout.addWidget(preview_title)
        self.preview_widget = TemplatePreviewWidget()
        self.preview_widget.setMinimumHeight(420)
        preview_layout.addWidget(self.preview_widget, 1)

        right_layout.addWidget(config_scroll, 1)
        right_layout.addWidget(preview_panel)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 900])
        layout.addWidget(splitter, 1)

        self._set_form_enabled(False)

    def _connect_controller(self):
        self.controller.settings_loaded.connect(self._on_settings_loaded)
        self.controller.catalog_loaded.connect(self._on_catalog_loaded)
        self.controller.templates_loaded.connect(self._on_templates_loaded)
        self.controller.media_assets_loaded.connect(self._on_media_assets_loaded)
        self.controller.media_asset_uploaded.connect(self._on_media_asset_uploaded)
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
            self.header_media_group, self.offsets_group, self.save_btn,
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

    def _media_kind_for_format(self, media_format: Optional[str]) -> Optional[str]:
        return _HEADER_FORMAT_KIND.get((media_format or "").upper())

    def _selected_header_asset_id(self) -> Optional[int]:
        value = self.header_asset_combo.currentData()
        return int(value) if value is not None else None

    def _selected_header_asset(self) -> Optional[Dict[str, Any]]:
        asset_id = self._selected_header_asset_id()
        if asset_id is None:
            return None
        return self._media_assets_by_id.get(asset_id)

    def _default_header_asset_id(self, tpl: Optional[Dict[str, Any]] = None) -> Optional[int]:
        tpl = tpl if tpl is not None else self._current_template()
        if not tpl:
            return None
        value = tpl.get("default_header_media_asset_id")
        return int(value) if value is not None else None

    def _default_header_asset(self, tpl: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        asset_id = self._default_header_asset_id(tpl)
        if asset_id is None:
            return None
        return self._media_assets_by_id.get(asset_id)

    @staticmethod
    def _asset_label(asset: Dict[str, Any]) -> str:
        return asset.get("display_name") or asset.get("original_filename") or f"Asset {asset.get('id')}"

    def _refresh_default_header_media_label(self) -> None:
        default_id = self._default_header_asset_id()
        if default_id is None:
            self.default_header_media_label.setText("Esta plantilla no tiene media por defecto.")
            return
        asset = self._default_header_asset()
        if asset:
            self.default_header_media_label.setText(f"Esta plantilla tiene media por defecto: {self._asset_label(asset)}")
        else:
            self.default_header_media_label.setText(f"Esta plantilla tiene media por defecto: asset #{default_id}")

    def _set_override_controls_enabled(self, enabled: bool, *, clear_when_disabled: bool = True) -> None:
        self.header_asset_combo.setEnabled(enabled)
        self.upload_asset_btn.setEnabled(enabled)
        self.header_media_input.setEnabled(enabled)
        if not enabled and clear_when_disabled:
            self.header_asset_combo.blockSignals(True)
            self.header_asset_combo.setCurrentIndex(0 if self.header_asset_combo.count() else -1)
            self.header_asset_combo.blockSignals(False)
            self.header_media_input.blockSignals(True)
            self.header_media_input.clear()
            self.header_media_input.blockSignals(False)
        self._update_preview()

    def _on_header_override_toggled(self, _state: int) -> None:
        self._set_override_controls_enabled(self.use_header_override_check.isChecked())

    def _populate_asset_combo(self, kind: str, selected_id: Optional[int] = None) -> None:
        self.header_asset_combo.blockSignals(True)
        self.header_asset_combo.clear()
        self.header_asset_combo.addItem("(Selecciona media)", None)
        selected_index = 0
        for i, asset in enumerate(self._media_assets_by_kind.get(kind, []), start=1):
            self.header_asset_combo.addItem(self._asset_label(asset), asset.get("id"))
            if selected_id is not None and asset.get("id") == selected_id:
                selected_index = i
        self.header_asset_combo.setCurrentIndex(selected_index)
        self.header_asset_combo.blockSignals(False)
        self._refresh_default_header_media_label()
        self._update_preview()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _populate_events_list(self) -> None:
        self.events_list.clear()
        for event_type in self._order:
            setting = self._settings.get(event_type, {})
            label = setting.get("label") or event_type
            enabled = bool(setting.get("enabled"))
            status = "Activo" if enabled else "Inactivo"
            item = QListWidgetItem(f"{status}  {label}")
            item.setForeground(QColor(theme.ACCENT if enabled else theme.TEXT_SECONDARY))
            item.setToolTip(label)
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

        self._pending_header_asset_id = setting.get("header_media_asset_id")
        self.header_media_input.setText(setting.get("header_media_url") or "")
        self.use_header_override_check.blockSignals(True)
        self.use_header_override_check.setChecked(
            bool(setting.get("header_media_asset_id") or setting.get("header_media_url"))
        )
        self.use_header_override_check.blockSignals(False)

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
        media_format = _required_header_media_format(tpl.get("components")) if tpl else None
        self.header_media_group.setVisible(bool(media_format))
        if media_format:
            self.header_media_group.setTitle(f"Media del encabezado ({media_format})")
            self._refresh_default_header_media_label()
            kind = self._media_kind_for_format(media_format)
            if kind:
                self._populate_asset_combo(kind, self._pending_header_asset_id)
                self.controller.load_media_assets(kind)
            self._set_override_controls_enabled(
                self.use_header_override_check.isChecked(),
                clear_when_disabled=False,
            )
        else:
            self._pending_header_asset_id = None
            self.use_header_override_check.blockSignals(True)
            self.use_header_override_check.setChecked(False)
            self.use_header_override_check.blockSignals(False)

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
            self.preview_widget.set_preview(body="(Selecciona una plantilla aprobada)")
            return
        body = _template_body_text(tpl.get("components"))
        footer = _template_footer_text(tpl.get("components"))
        # Mapa key -> sample para el evento actual
        samples = {v.get("key"): v.get("sample") for v in self._event_variables(self._current_event)}
        mapping = self._collect_param_mapping()

        def repl(match: "re.Match") -> str:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(mapping):
                return str(samples.get(mapping[idx], match.group(0)))
            return match.group(0)

        media_format = _required_header_media_format(tpl.get("components"))
        asset = None
        media_url = None
        media_name = None
        if media_format:
            if self.use_header_override_check.isChecked():
                asset = self._selected_header_asset()
                media_url = (asset or {}).get("public_url") or self.header_media_input.text().strip()
                media_name = (asset or {}).get("display_name") or (asset or {}).get("original_filename")
            else:
                asset = self._default_header_asset(tpl)
                media_url = (asset or {}).get("public_url")
                media_name = (
                    (asset or {}).get("display_name")
                    or (asset or {}).get("original_filename")
                    or (
                        f"Asset default #{self._default_header_asset_id(tpl)}"
                        if self._default_header_asset_id(tpl) is not None
                        else None
                    )
                )
        self.preview_widget.set_preview(
            body=_PLACEHOLDER_RE.sub(repl, body),
            footer=footer,
            media_format=media_format,
            media_url=media_url,
            media_name=media_name,
        )

    # ------------------------------------------------------------------
    # Acciones de usuario
    # ------------------------------------------------------------------
    def on_event_selected(self, item: QListWidgetItem) -> None:
        event_type = item.data(Qt.ItemDataRole.UserRole)
        self._current_event = event_type
        self._render_event(event_type)
        self.event_selected.emit(event_type or "")

    def on_template_changed(self, _index: int) -> None:
        setting = self._settings.get(self._current_event, {})
        self._pending_header_asset_id = setting.get("header_media_asset_id")
        self._rebuild_variable_rows()

    def on_upload_header_asset(self) -> None:
        tpl = self._current_template()
        media_format = _required_header_media_format(tpl.get("components")) if tpl else None
        kind = self._media_kind_for_format(media_format)
        if not kind:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo multimedia")
        if not path:
            return
        self.controller.upload_media_asset(path, kind)

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

        tpl = self._current_template()
        media_format = _required_header_media_format(tpl.get("components")) if tpl else None
        header_media_asset_id = None
        header_media_url = None
        if media_format and self.use_header_override_check.isChecked():
            header_media_asset_id = self._selected_header_asset_id()
            header_media_url = self.header_media_input.text().strip()
            if enabled and not header_media_asset_id and not header_media_url:
                show_error(self, f"Selecciona un asset override o una URL HTTPS para {media_format}.")
                return
        elif enabled and media_format and self._default_header_asset_id(tpl) is None:
            show_error(
                self,
                f"La plantilla requiere media de encabezado ({media_format}) y no tiene default; "
                "activa un override para este evento.",
            )
            return
        if header_media_url and not header_media_url.startswith("https://"):
            show_error(self, "La URL de media debe ser pública y empezar con https://.")
            return

        data = {
            "event_type": self._current_event,
            "enabled": enabled,
            "template_id": template_id,
            "param_mapping": self._collect_param_mapping(),
            "header_media_url": header_media_url,
            "header_media_asset_id": header_media_asset_id,
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

    def _on_media_assets_loaded(self, kind: str, assets: List[Dict[str, Any]]) -> None:
        self._media_assets_by_kind[kind] = assets or []
        for asset in assets or []:
            if asset.get("id") is not None:
                self._media_assets_by_id[asset["id"]] = asset
        tpl = self._current_template()
        media_format = _required_header_media_format(tpl.get("components")) if tpl else None
        if kind == self._media_kind_for_format(media_format):
            self._populate_asset_combo(kind, self._pending_header_asset_id)
            self._refresh_default_header_media_label()

    def _on_media_asset_uploaded(self, kind: str, asset: Dict[str, Any]) -> None:
        if not asset:
            return
        assets = [a for a in self._media_assets_by_kind.get(kind, []) if a.get("id") != asset.get("id")]
        assets.insert(0, asset)
        self._media_assets_by_kind[kind] = assets
        if asset.get("id") is not None:
            self._media_assets_by_id[asset["id"]] = asset
            self._pending_header_asset_id = asset["id"]
        self._populate_asset_combo(kind, self._pending_header_asset_id)
        self._refresh_default_header_media_label()
        show_info(self, "Media subida correctamente.")

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
