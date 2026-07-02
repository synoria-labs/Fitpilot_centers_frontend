"""
Sección de Configuración: Permisos por rol.

Muestra una matriz Roles x Capacidades con casillas para conceder/revocar.
El rol ``admin`` aparece marcado y bloqueado (super-usuario implícito).
Solo accesible desde el menú Configuración (admin-only).
"""
from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...utils.dialog_helpers import show_error, show_info
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)

# Friendly labels for known capabilities.
CAPABILITY_LABELS = {
    "manage_membership_plans": "Gestionar planes",
    "manage_owner_agent": "Gestionar agente admin",
    "manage_users": "Gestionar usuarios",
    "operate_pos": "Operar POS",
    "manage_cash_session": "Gestionar caja",
    "view_pos_reports": "Ver reportes POS",
    "manage_products": "Gestionar productos",
    "manage_payments": "Gestionar pagos",
    "manage_subscriptions": "Gestionar suscripciones",
    "send_campaigns": "Enviar campañas",
    "view_members": "Ver socios",
    "view_finances": "Ver finanzas",
    "view_chats": "Ver chats",
}


def _capability_label(code: str) -> str:
    return CAPABILITY_LABELS.get(code, code)


class RolePermissionsView(QWidget):
    """Matriz de roles y capacidades con conceder/revocar."""

    def __init__(self):
        super().__init__()

        try:
            permissions_service = container.get("permissions_service")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve permissions_service: %s", exc)
            raise

        from ...controllers.permissions_controller import PermissionsController
        self.controller = PermissionsController(permissions_service, self)

        self._capabilities: List[str] = []
        self._building = False

        self.setup_ui()
        self._connect_controller()
        self.controller.load_matrix()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Permisos por rol")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        info = QLabel(
            "Concede o revoca capacidades a cada rol. El rol «admin» tiene todas las "
            "capacidades de forma permanente. Los cambios aplican al próximo inicio de "
            "sesión del usuario afectado."
        )
        info.setWordWrap(True)
        info.setObjectName("hintLabel")
        layout.addWidget(info)

        self.table = QTableWidget()
        configure_table_widget(self.table)
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table)

    def _connect_controller(self):
        self.controller.matrix_loaded.connect(self._on_matrix_loaded)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.mutation_succeeded.connect(self._on_mutation_succeeded)
        self.controller.mutation_failed.connect(self._on_error)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_matrix_loaded(self, data: Dict[str, Any]):
        self._building = True
        try:
            roles = data.get("roles", []) or []
            self._capabilities = list(data.get("capabilities", []) or [])

            columns = ["Rol"] + [_capability_label(c) for c in self._capabilities]
            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels(columns)
            self.table.setRowCount(len(roles))

            for row, role in enumerate(roles):
                role_code = role.get("role_code", "")
                description = role.get("role_description") or role_code
                granted = set(role.get("capabilities") or [])
                locked = bool(role.get("locked"))

                name_item = QTableWidgetItem(f"{role_code}  ·  {description}" if description else role_code)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, name_item)

                for col, cap in enumerate(self._capabilities, start=1):
                    cell = self._make_checkbox_cell(role_code, cap, cap in granted, locked)
                    self.table.setCellWidget(row, col, cell)

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for col in range(1, self.table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        finally:
            self._building = False

    def _make_checkbox_cell(self, role_code: str, capability: str, checked: bool, locked: bool) -> QWidget:
        container_widget = QWidget()
        row = QHBoxLayout(container_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setEnabled(not locked)
        checkbox.toggled.connect(
            lambda state, rc=role_code, cap=capability: self._on_toggle(rc, cap, state)
        )
        row.addWidget(checkbox)
        return container_widget

    def _on_toggle(self, role_code: str, capability: str, granted: bool):
        if self._building:
            return
        self.controller.set_grant(role_code, capability, granted)

    def _on_mutation_succeeded(self, message: str):
        show_info(self, message or "Permiso actualizado", title="Permisos")

    def _on_error(self, message: str):
        show_error(self, message or "Ocurrió un error.", title="Permisos")
