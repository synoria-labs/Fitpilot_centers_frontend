"""Vista de la pestaña Chatbot - configuración del agente de WhatsApp."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
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


# Heurística local (sin IA) para avisar al guardar: detecta datos que el agente ya inyecta en
# vivo desde la DB/herramientas y que NO deberían ir escritos a mano en el system prompt.
_DB_LIKE_PATTERNS = (
    ("precios", re.compile(r"\$\s*\d|\b\d+\s*(?:pesos|mxn)\b", re.IGNORECASE)),
    ("horarios", re.compile(r"\b\d{1,2}:\d{2}\b", re.IGNORECASE)),
    (
        "días de la semana",
        re.compile(
            r"\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
            re.IGNORECASE,
        ),
    ),
    ("precios/planes", re.compile(r"\b(?:precio|costo|tarifa|cuesta)\w*", re.IGNORECASE)),
    ("horarios", re.compile(r"\bhorario\w*", re.IGNORECASE)),
    ("dirección/sedes", re.compile(r"\b(?:direcci[oó]n|sede|sucursal)\w*", re.IGNORECASE)),
    ("teléfono", re.compile(r"\btel[eé]fono\w*", re.IGNORECASE)),
    ("instructores", re.compile(r"\binstructor\w*", re.IGNORECASE)),
    ("cupo/disponibilidad", re.compile(r"\b(?:cupo|disponib)\w*", re.IGNORECASE)),
)


def _detect_db_like_content(text: str) -> List[str]:
    """Return the (deduped) categories of DB-injected data found in the prompt text."""
    if not text or not text.strip():
        return []
    found: List[str] = []
    for label, pattern in _DB_LIKE_PATTERNS:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


class PromptOptimizeSuggestionDialog(QDialog):
    """Vista previa del system prompt optimizado por la IA."""

    def __init__(self, suggestion: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._suggestion = suggestion or {}
        self.setWindowTitle("System prompt optimizado")
        self.resize(560, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        prompt_label = QLabel("System prompt optimizado")
        prompt_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(prompt_label)
        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setPlainText(self._suggestion.get("optimized_prompt") or "")
        self.prompt_preview.setMinimumHeight(220)
        layout.addWidget(self.prompt_preview)

        meta_lines: List[str] = []
        for item in self._suggestion.get("removed") or []:
            meta_lines.append(f"Eliminado: {item}")
        for note in self._suggestion.get("notes") or []:
            meta_lines.append(f"Nota: {note}")
        for warning in self._suggestion.get("warnings") or []:
            meta_lines.append(f"Advertencia: {warning}")
        if meta_lines:
            meta = QLabel("\n".join(meta_lines))
            meta.setWordWrap(True)
            meta.setStyleSheet("color: #5d6d7e;")
            layout.addWidget(meta)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def suggestion(self) -> Dict[str, Any]:
        return self._suggestion


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

        prompt_actions = QHBoxLayout()
        prompt_actions.setContentsMargins(0, 0, 0, 0)
        prompt_actions.addStretch()
        self.optimize_btn = QPushButton("Optimizar")
        self.optimize_btn.setObjectName("botActionButton")
        self.optimize_btn.setToolTip(
            "Reescribe el prompt con IA y quita lo que ya se toma de la base de datos "
            "(precios, horarios, sedes, etc.)."
        )
        _set_button_icon(self.optimize_btn, "fa5s.magic")
        self.optimize_btn.clicked.connect(self._on_optimize_clicked)
        prompt_actions.addWidget(self.optimize_btn)
        instructions_form.addRow("", prompt_actions)
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
        self.controller.prompt_optimized.connect(self._on_prompt_optimized)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading)

    def _on_loading(self, loading: bool) -> None:
        self.save_btn.setEnabled(not loading)
        self.optimize_btn.setEnabled(not loading)

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

    def _on_optimize_clicked(self) -> None:
        prompt = self.system_prompt_edit.toPlainText().strip()
        if not prompt:
            show_error(self, "Escribe un system prompt antes de optimizarlo.", title="Chatbot")
            return
        instruction, ok = QInputDialog.getMultiLineText(
            self,
            "Optimizar system prompt",
            "Indicación opcional para la optimización (deja vacío para una limpieza estándar):",
            "",
        )
        if not ok:
            return
        self.controller.optimize_prompt(
            prompt,
            tone=self.tone_edit.text().strip() or None,
            instruction=(instruction or "").strip() or None,
        )

    def _on_prompt_optimized(self, suggestion: Optional[Dict[str, Any]]) -> None:
        if not suggestion:
            return
        dialog = PromptOptimizeSuggestionDialog(suggestion, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.system_prompt_edit.setPlainText(dialog.suggestion().get("optimized_prompt") or "")
        # No se auto-guarda: el usuario revisa y pulsa "Guardar".

    def _on_save_clicked(self) -> None:
        detected = _detect_db_like_content(self.system_prompt_edit.toPlainText())
        if detected and not self._confirm_db_like_save(detected):
            return
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

    def _confirm_db_like_save(self, detected: List[str]) -> bool:
        """Aviso no bloqueante al guardar. Devuelve True si debe continuar el guardado."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Chatbot")
        box.setText(
            "Tu system prompt parece incluir datos que el asistente ya toma automáticamente "
            "de la base de datos ("
            + ", ".join(detected)
            + "). Escribirlos a mano puede contradecir la información en vivo. ¿Qué deseas hacer?"
        )
        save_btn = box.addButton("Guardar de todas formas", QMessageBox.ButtonRole.AcceptRole)
        optimize_btn = box.addButton("Optimizar primero", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(optimize_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            return True
        if clicked is optimize_btn:
            self._on_optimize_clicked()
        return False
