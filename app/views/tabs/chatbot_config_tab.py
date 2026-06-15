"""Vista de la pestaña Chatbot - Configuración del agente de WhatsApp (LangChain/Anthropic).

Permite editar, en tiempo real desde el frontend, el system prompt configurable, la información
de negocio (horarios, dirección, teléfono, políticas, tono) y los toggles del agente
(activado, requerir confirmación) y el modelo de Claude. Se guarda en la tabla
``app.chatbot_config`` del backend vía GraphQL.
"""
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QLineEdit, QComboBox, QCheckBox, QFormLayout, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...controllers.chatbot_config_controller import ChatbotConfigController
from ...utils.dialog_helpers import show_error, show_info

logger = get_logger(__name__)

_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]


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

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setObjectName("chatbotConfigTab")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 12)
        header_layout.setSpacing(4)
        title = QLabel("Chatbot de WhatsApp")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        hint = QLabel(
            "Configura el asistente que responde automáticamente a los clientes por WhatsApp: "
            "su comportamiento (system prompt) y si debe pedir confirmación antes de reservar o "
            "cobrar. El horario de clases, los precios, las sedes/dirección y los instructores se "
            "toman automáticamente de la base de datos; los campos de abajo son overrides/extras "
            "(nombre, políticas, tono, teléfono) y respaldo."
        )
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(20, 8, 20, 8)
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.enabled_check = QCheckBox("Activar el chatbot (responde automáticamente a clientes)")
        form.addRow("Estado", self.enabled_check)

        self.require_confirmation_check = QCheckBox(
            "Pedir confirmación antes de reservar, cobrar o renovar"
        )
        form.addRow("Confirmación", self.require_confirmation_check)

        self.require_mp_payment_check = QCheckBox(
            "Solicitar pago por MercadoPago antes de inscribir / renovar / reservar"
        )
        form.addRow("MercadoPago", self.require_mp_payment_check)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(_MODELS)
        form.addRow("Modelo", self.model_combo)

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setMinimumHeight(140)
        self.system_prompt_edit.setPlaceholderText(
            "Instrucciones de comportamiento del asistente (contexto del negocio, tono, reglas)..."
        )
        form.addRow("System prompt", self.system_prompt_edit)

        self.business_name_edit = QLineEdit()
        form.addRow("Nombre del negocio", self.business_name_edit)

        self.address_edit = QLineEdit()
        form.addRow("Dirección", self.address_edit)

        self.operating_hours_edit = QTextEdit()
        self.operating_hours_edit.setMaximumHeight(80)
        self.operating_hours_edit.setPlaceholderText("Ej. Lun-Vie 6:00-22:00, Sáb 8:00-14:00")
        form.addRow("Horarios", self.operating_hours_edit)

        self.phone_edit = QLineEdit()
        form.addRow("Teléfono", self.phone_edit)

        self.policies_edit = QTextEdit()
        self.policies_edit.setMaximumHeight(80)
        self.policies_edit.setPlaceholderText("Políticas de cancelación, reglas, etc.")
        form.addRow("Políticas", self.policies_edit)

        self.tone_edit = QLineEdit()
        self.tone_edit.setPlaceholderText("Ej. Cálido, breve y profesional")
        form.addRow("Tono", self.tone_edit)

        self.extra_info_edit = QTextEdit()
        self.extra_info_edit.setMaximumHeight(80)
        self.extra_info_edit.setPlaceholderText("Información adicional para el asistente")
        form.addRow("Información extra", self.extra_info_edit)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(20, 8, 20, 16)
        footer.addStretch()
        self.save_btn = QPushButton("Guardar")
        self.save_btn.clicked.connect(self._on_save_clicked)
        footer.addWidget(self.save_btn)
        root.addLayout(footer)

    def _connect_controller(self) -> None:
        self.controller.config_loaded.connect(self._on_config_loaded)
        self.controller.config_saved.connect(self._on_config_saved)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading)

    # ------------------------------------------------------------------
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
