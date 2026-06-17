"""Vista de la pestaña Chatbot - configuración del agente de WhatsApp."""
from __future__ import annotations

from typing import Any, Dict, Optional

import qtawesome as qta
from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...controllers.chatbot_config_controller import ChatbotConfigController
from ...core import container, get_logger
from ...utils.dialog_helpers import show_error, show_info
from ..screen_style import screen_qss
from .whatsapp import theme

logger = get_logger(__name__)

_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]


def _set_button_icon(button: QPushButton, icon_name: str, *, primary: bool = False) -> None:
    color = "#ffffff" if primary else theme.palette_hex()
    button.setIcon(qta.icon(icon_name, color=color))
    button.setIconSize(QSize(14, 14))


def _new_form(parent: QWidget) -> QFormLayout:
    form = QFormLayout(parent)
    form.setContentsMargins(10, 10, 10, 10)
    form.setSpacing(12)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


class ChatbotConfigTab(QWidget):
    """Configuración del chatbot de WhatsApp."""

    def __init__(self):
        super().__init__()
        try:
            service = container.get("chatbot_config_service")
        except Exception as exc:  # pragma: no cover - defensivo
            logger.error("No se pudo obtener chatbot_config_service: %s", exc)
            raise
        self.controller = ChatbotConfigController(service, self)

        self._build_ui()
        self._connect_controller()
        self.controller.load_config()

    def _build_ui(self) -> None:
        self.setObjectName("botTab")
        self.setStyleSheet(screen_qss("bot"))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("botHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 12)
        header_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        title = QLabel("Chatbot de WhatsApp")
        title.setObjectName("botTitle")
        header_row.addWidget(title)
        header_row.addStretch()

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setObjectName("botPrimaryButton")
        _set_button_icon(self.save_btn, "fa5s.save", primary=True)
        self.save_btn.clicked.connect(self._on_save_clicked)
        header_row.addWidget(self.save_btn)
        header_layout.addLayout(header_row)

        hint = QLabel(
            "Configura el asistente que responde automáticamente a los clientes por WhatsApp: "
            "su comportamiento (system prompt) y si debe pedir confirmación antes de reservar o "
            "cobrar. El horario de clases, los precios, las sedes/dirección y los instructores se "
            "toman automáticamente de la base de datos; los campos de abajo son overrides/extras "
            "(nombre, políticas, tono, teléfono) y respaldo."
        )
        hint.setObjectName("botHint")
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("botConfigScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setObjectName("botConfigPane")
        content = QVBoxLayout(body)
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(12)

        automation_group = QGroupBox("Automatización")
        automation_group.setObjectName("botGroup")
        automation_form = _new_form(automation_group)
        self.enabled_check = QCheckBox("Activar el chatbot (responde automáticamente a clientes)")
        automation_form.addRow("Estado", self.enabled_check)
        self.require_confirmation_check = QCheckBox(
            "Pedir confirmación antes de reservar, cobrar o renovar"
        )
        automation_form.addRow("Confirmación", self.require_confirmation_check)
        self.require_mp_payment_check = QCheckBox(
            "Solicitar pago por MercadoPago antes de inscribir / renovar / reservar"
        )
        automation_form.addRow("MercadoPago", self.require_mp_payment_check)
        content.addWidget(automation_group)

        instructions_group = QGroupBox("Modelo e instrucciones")
        instructions_group.setObjectName("botGroup")
        instructions_form = _new_form(instructions_group)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(_MODELS)
        instructions_form.addRow("Modelo", self.model_combo)
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setObjectName("botBodyEditor")
        self.system_prompt_edit.setMinimumHeight(140)
        self.system_prompt_edit.setPlaceholderText(
            "Instrucciones de comportamiento del asistente (contexto del negocio, tono, reglas)..."
        )
        instructions_form.addRow("System prompt", self.system_prompt_edit)
        content.addWidget(instructions_group)

        business_group = QGroupBox("Datos del negocio")
        business_group.setObjectName("botGroup")
        business_form = _new_form(business_group)
        self.business_name_edit = QLineEdit()
        business_form.addRow("Nombre del negocio", self.business_name_edit)
        self.address_edit = QLineEdit()
        business_form.addRow("Dirección", self.address_edit)
        self.operating_hours_edit = QTextEdit()
        self.operating_hours_edit.setObjectName("botBodyEditor")
        self.operating_hours_edit.setMaximumHeight(80)
        self.operating_hours_edit.setPlaceholderText("Ej. Lun-Vie 6:00-22:00, Sáb 8:00-14:00")
        business_form.addRow("Horarios", self.operating_hours_edit)
        self.phone_edit = QLineEdit()
        business_form.addRow("Teléfono", self.phone_edit)
        self.policies_edit = QTextEdit()
        self.policies_edit.setObjectName("botBodyEditor")
        self.policies_edit.setMaximumHeight(80)
        self.policies_edit.setPlaceholderText("Políticas de cancelación, reglas, etc.")
        business_form.addRow("Políticas", self.policies_edit)
        self.tone_edit = QLineEdit()
        self.tone_edit.setPlaceholderText("Ej. Cálido, breve y profesional")
        business_form.addRow("Tono", self.tone_edit)
        self.extra_info_edit = QTextEdit()
        self.extra_info_edit.setObjectName("botBodyEditor")
        self.extra_info_edit.setMaximumHeight(80)
        self.extra_info_edit.setPlaceholderText("Información adicional para el asistente")
        business_form.addRow("Información extra", self.extra_info_edit)
        content.addWidget(business_group)
        content.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _connect_controller(self) -> None:
        self.controller.config_loaded.connect(self._on_config_loaded)
        self.controller.config_saved.connect(self._on_config_saved)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading)

    def _on_loading(self, loading: bool) -> None:
        self.save_btn.setEnabled(not loading)

    def _on_config_loaded(self, config: Optional[Dict[str, Any]]) -> None:
        if not config:
            return
        self.enabled_check.setChecked(bool(config.get("enabled")))
        self.require_confirmation_check.setChecked(bool(config.get("require_confirmation", True)))
        self.require_mp_payment_check.setChecked(bool(config.get("require_mp_payment", False)))
        model = config.get("model") or "claude-sonnet-4-6"
        idx = self.model_combo.findText(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(model)
        self.system_prompt_edit.setPlainText(config.get("system_prompt") or "")
        self.business_name_edit.setText(config.get("business_name") or "")
        self.address_edit.setText(config.get("address") or "")
        self.operating_hours_edit.setPlainText(config.get("operating_hours") or "")
        self.phone_edit.setText(config.get("phone") or "")
        self.policies_edit.setPlainText(config.get("policies") or "")
        self.tone_edit.setText(config.get("tone") or "")
        self.extra_info_edit.setPlainText(config.get("extra_info") or "")

    def _on_config_saved(self, config: Optional[Dict[str, Any]]) -> None:
        show_info(self, "Configuración guardada correctamente.", title="Chatbot")
        if config:
            self._on_config_loaded(config)

    def _on_error(self, message: str) -> None:
        show_error(self, message or "Ocurrió un error.", title="Chatbot")

    def _on_save_clicked(self) -> None:
        data = {
            "enabled": self.enabled_check.isChecked(),
            "require_confirmation": self.require_confirmation_check.isChecked(),
            "require_mp_payment": self.require_mp_payment_check.isChecked(),
            "model": self.model_combo.currentText().strip() or "claude-sonnet-4-6",
            "system_prompt": self.system_prompt_edit.toPlainText().strip(),
            "business_name": self.business_name_edit.text().strip(),
            "address": self.address_edit.text().strip(),
            "operating_hours": self.operating_hours_edit.toPlainText().strip(),
            "phone": self.phone_edit.text().strip(),
            "policies": self.policies_edit.toPlainText().strip(),
            "tone": self.tone_edit.text().strip(),
            "extra_info": self.extra_info_edit.toPlainText().strip(),
        }
        self.controller.save_config(data)
