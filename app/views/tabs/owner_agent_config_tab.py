"""Configuration tab for the owner/admin WhatsApp agent."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...controllers.owner_agent_config_controller import OwnerAgentConfigController
from ...core import container, get_logger
from ...utils.dialog_helpers import show_error, show_info
from ..screen_style import screen_qss
from .whatsapp import theme

logger = get_logger(__name__)

_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _icon(name: str, primary: bool = False):
    return qta.icon(name, color="#ffffff" if primary else theme.palette_hex())


class PhoneDialog(QDialog):
    def __init__(self, phone: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Telefono autorizado")
        self.resize(380, 180)
        phone = phone or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.label_edit = QLineEdit(phone.get("label") or "")
        self.phone_edit = QLineEdit(phone.get("phone_number") or "")
        self.phone_edit.setPlaceholderText("8719708890")
        self.enabled_check = QCheckBox("Activo")
        self.enabled_check.setChecked(bool(phone.get("enabled", True)))
        form.addRow("Etiqueta", self.label_edit)
        form.addRow("Telefono", self.phone_edit)
        form.addRow("Estado", self.enabled_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if len(_digits(self.phone_edit.text())) < 10:
            show_error(self, "Captura al menos 10 digitos.", title="Agente Admin")
            return
        self.accept()

    def data(self) -> Dict[str, Any]:
        return {
            "label": self.label_edit.text().strip() or self.phone_edit.text().strip(),
            "phone_number": self.phone_edit.text().strip(),
            "enabled": self.enabled_check.isChecked(),
        }


class OwnerAgentConfigTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        service = container.get("owner_agent_config_service")
        self.controller = OwnerAgentConfigController(service, self)
        self._phones: list[Dict[str, Any]] = []

        self._build_ui()
        self._connect_controller()
        self.controller.load_bundle()

    def _build_ui(self) -> None:
        self.setObjectName("ownerAgentTab")
        self.setStyleSheet(screen_qss("bot"))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("botHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 12)
        header_layout.setSpacing(8)

        row = QHBoxLayout()
        title = QLabel("Agente Admin")
        title.setObjectName("botTitle")
        row.addWidget(title)
        row.addStretch()

        self.refresh_btn = QPushButton("Actualizar")
        self.refresh_btn.setIcon(_icon("fa5s.sync"))
        self.refresh_btn.setIconSize(QSize(14, 14))
        self.refresh_btn.clicked.connect(self.controller.load_bundle)
        row.addWidget(self.refresh_btn)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setObjectName("botPrimaryButton")
        self.save_btn.setIcon(_icon("fa5s.save", primary=True))
        self.save_btn.setIconSize(QSize(14, 14))
        self.save_btn.clicked.connect(self._save_config)
        row.addWidget(self.save_btn)
        header_layout.addLayout(row)

        hint = QLabel(
            "Configura el agente administrativo que responde por WhatsApp solo a telefonos "
            "autorizados. El servidor debe tener OWNER_AGENT_SERVER_ENABLED=true para que responda."
        )
        hint.setObjectName("botHint")
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(12)

        automation = QGroupBox("Operacion")
        form = QFormLayout(automation)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(12)
        self.server_state_label = QLabel("Servidor: desconocido")
        form.addRow("Servidor", self.server_state_label)
        self.enabled_check = QCheckBox("Activar agente administrativo")
        form.addRow("Estado", self.enabled_check)
        self.require_confirmation_check = QCheckBox("Requerir confirmacion para acciones")
        self.require_confirmation_check.setChecked(True)
        form.addRow("Confirmacion", self.require_confirmation_check)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(_MODELS)
        form.addRow("Modelo", self.model_combo)
        self.history_spin = QSpinBox()
        self.history_spin.setRange(1, 100)
        self.history_spin.setValue(30)
        form.addRow("Historial", self.history_spin)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(256, 4096)
        self.max_tokens_spin.setSingleStep(128)
        self.max_tokens_spin.setValue(1024)
        form.addRow("Max tokens", self.max_tokens_spin)
        content.addWidget(automation)

        phones_group = QGroupBox("Telefonos autorizados")
        phones_layout = QVBoxLayout(phones_group)
        actions = QHBoxLayout()
        actions.addStretch()
        self.add_phone_btn = QPushButton("Agregar")
        self.add_phone_btn.setIcon(_icon("fa5s.plus"))
        self.add_phone_btn.clicked.connect(self._add_phone)
        actions.addWidget(self.add_phone_btn)
        phones_layout.addLayout(actions)

        self.phones_table = QTableWidget(0, 5)
        self.phones_table.setHorizontalHeaderLabels(
            ["Etiqueta", "Telefono", "WhatsApp ID", "Estado", "Acciones"]
        )
        self.phones_table.verticalHeader().setVisible(False)
        self.phones_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.phones_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.phones_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        phones_layout.addWidget(self.phones_table)
        content.addWidget(phones_group)

        prompt_group = QGroupBox("Instrucciones")
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMinimumHeight(160)
        self.prompt_edit.setPlaceholderText(
            "Reglas administrativas, estilo de respuesta y criterios de reportes..."
        )
        prompt_layout.addWidget(self.prompt_edit)
        content.addWidget(prompt_group)
        content.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _connect_controller(self) -> None:
        self.controller.bundle_loaded.connect(self._on_bundle_loaded)
        self.controller.config_saved.connect(lambda _c: show_info(self, "Configuracion guardada.", title="Agente Admin"))
        self.controller.phone_saved.connect(lambda _p: show_info(self, "Telefono guardado.", title="Agente Admin"))
        self.controller.phone_disabled.connect(lambda _p: show_info(self, "Telefono desactivado.", title="Agente Admin"))
        self.controller.error_occurred.connect(lambda msg: show_error(self, msg, title="Agente Admin"))
        self.controller.loading_changed.connect(self._on_loading)

    def _on_loading(self, loading: bool) -> None:
        self.save_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.add_phone_btn.setEnabled(not loading)

    def _on_bundle_loaded(self, bundle: Dict[str, Any]) -> None:
        config = (bundle or {}).get("config") or {}
        phones = (bundle or {}).get("phones") or []
        self._apply_config(config)
        self._phones = list(phones)
        self._render_phones()

    def _apply_config(self, config: Dict[str, Any]) -> None:
        server_enabled = bool(config.get("server_enabled"))
        self.server_state_label.setText("Activo" if server_enabled else "Apagado por .env")
        self.server_state_label.setStyleSheet(
            "color: #1f9d55;" if server_enabled else "color: #b45309;"
        )
        self.enabled_check.setChecked(bool(config.get("enabled", False)))
        self.require_confirmation_check.setChecked(bool(config.get("require_confirmation", True)))
        model = config.get("model") or "claude-sonnet-4-6"
        idx = self.model_combo.findText(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(model)
        self.history_spin.setValue(int(config.get("history_limit") or 30))
        self.max_tokens_spin.setValue(int(config.get("max_tokens") or 1024))
        self.prompt_edit.setPlainText(config.get("system_prompt") or "")

    def _render_phones(self) -> None:
        self.phones_table.setRowCount(len(self._phones))
        for row, phone in enumerate(self._phones):
            self.phones_table.setItem(row, 0, QTableWidgetItem(phone.get("label") or ""))
            self.phones_table.setItem(row, 1, QTableWidgetItem(phone.get("phone_number") or ""))
            self.phones_table.setItem(row, 2, QTableWidgetItem(phone.get("normalized_wa_id") or ""))
            status = "Activo" if phone.get("enabled") else "Inactivo"
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.phones_table.setItem(row, 3, status_item)
            self.phones_table.setCellWidget(row, 4, self._phone_actions(phone))

    def _phone_actions(self, phone: Dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit_btn = QPushButton()
        edit_btn.setToolTip("Editar telefono")
        edit_btn.setIcon(_icon("fa5s.edit"))
        edit_btn.setFixedWidth(32)
        edit_btn.clicked.connect(lambda _=False, p=phone: self._edit_phone(p))
        layout.addWidget(edit_btn)

        disable_btn = QPushButton()
        disable_btn.setToolTip("Desactivar telefono")
        disable_btn.setIcon(_icon("fa5s.ban"))
        disable_btn.setFixedWidth(32)
        disable_btn.setEnabled(bool(phone.get("enabled")))
        disable_btn.clicked.connect(lambda _=False, p=phone: self.controller.disable_phone(int(p["id"])))
        layout.addWidget(disable_btn)
        return widget

    def _save_config(self) -> None:
        self.controller.save_config(
            {
                "enabled": self.enabled_check.isChecked(),
                "require_confirmation": self.require_confirmation_check.isChecked(),
                "model": self.model_combo.currentText().strip() or "claude-sonnet-4-6",
                "system_prompt": self.prompt_edit.toPlainText().strip(),
                "history_limit": self.history_spin.value(),
                "max_tokens": self.max_tokens_spin.value(),
            }
        )

    def _add_phone(self) -> None:
        dialog = PhoneDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.data()
        self.controller.add_phone(
            data["label"], data["phone_number"], enabled=bool(data["enabled"])
        )

    def _edit_phone(self, phone: Dict[str, Any]) -> None:
        dialog = PhoneDialog(phone, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.data()
        self.controller.update_phone(
            int(phone["id"]),
            label=data["label"],
            phone_number=data["phone_number"],
            enabled=bool(data["enabled"]),
        )
