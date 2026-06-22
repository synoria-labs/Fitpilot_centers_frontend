"""
Sección de Configuración: Usuarios (cuentas de acceso).

CRUD de cuentas de login del staff: crear/editar/activar/desactivar y asignar
uno o varios roles. Solo los usuarios con la capacidad ``manage_users`` (admin
por defecto) pueden gestionar; el resto ve la lista en modo lectura.
"""
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QDialog,
    QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox,
    QListWidget, QListWidgetItem, QInputDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...models.base import AppUser, AppRole
from ...utils.dialog_helpers import show_confirmation, show_error, show_info
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)

MANAGE_CAPABILITY = "manage_users"


class UsersView(QWidget):
    """Vista para la gestión de cuentas de acceso (usuarios del sistema)."""

    def __init__(self):
        super().__init__()

        try:
            users_service = container.get("users_service")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve users_service: %s", exc)
            raise

        self._can_manage = self._resolve_can_manage()

        from ...controllers.users_controller import UsersController
        self.controller = UsersController(users_service, self)

        self._users: List[AppUser] = []
        self._roles: List[AppRole] = []

        self.setup_ui()
        self._connect_controller()
        self.controller.load_roles()
        self.controller.load_users()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _resolve_can_manage(self) -> bool:
        try:
            auth_service = container.get("auth_service")
            return bool(auth_service.has_capability(MANAGE_CAPABILITY))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not resolve capability, defaulting to read-only: %s", exc)
            return False

    def setup_ui(self):
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title = QLabel("Usuarios")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.new_btn = QPushButton("+ Nuevo Usuario")
        self.new_btn.setObjectName("primaryButton")
        self.new_btn.clicked.connect(self.on_new_clicked)
        header_layout.addWidget(self.new_btn)

        self.edit_btn = QPushButton("Editar")
        self.edit_btn.setObjectName("actionButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.on_edit_clicked)
        header_layout.addWidget(self.edit_btn)

        self.password_btn = QPushButton("Restablecer contraseña")
        self.password_btn.setObjectName("actionButton")
        self.password_btn.setEnabled(False)
        self.password_btn.clicked.connect(self.on_reset_password_clicked)
        header_layout.addWidget(self.password_btn)

        self.deactivate_btn = QPushButton("Desactivar")
        self.deactivate_btn.setObjectName("dangerButton")
        self.deactivate_btn.setEnabled(False)
        self.deactivate_btn.clicked.connect(self.on_deactivate_clicked)
        header_layout.addWidget(self.deactivate_btn)

        self.reactivate_btn = QPushButton("Reactivar")
        self.reactivate_btn.setObjectName("actionButton")
        self.reactivate_btn.setEnabled(False)
        self.reactivate_btn.clicked.connect(self.on_reactivate_clicked)
        header_layout.addWidget(self.reactivate_btn)

        layout.addLayout(header_layout)

        if not self._can_manage:
            hint = QLabel("Solo lectura: no tienes permiso para gestionar usuarios.")
            hint.setObjectName("hintLabel")
            layout.addWidget(hint)
            self.new_btn.setEnabled(False)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Usuario", "Nombre", "Email", "Teléfono", "Roles", "Activo",
        ])
        configure_table_widget(self.table)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        if self._can_manage:
            self.table.cellDoubleClicked.connect(lambda *_: self.on_edit_clicked())
        layout.addWidget(self.table)

        summary_layout = QHBoxLayout()
        self.summary_label = QLabel("0 usuarios")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()
        layout.addLayout(summary_layout)

    def _connect_controller(self):
        self.controller.users_loaded.connect(self._on_users_loaded)
        self.controller.roles_loaded.connect(self._on_roles_loaded)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.mutation_succeeded.connect(self._on_mutation_succeeded)
        self.controller.mutation_failed.connect(self._on_error)

    # ------------------------------------------------------------------
    # Controller callbacks
    # ------------------------------------------------------------------
    def _on_roles_loaded(self, roles: List[AppRole]):
        self._roles = list(roles)

    def _on_users_loaded(self, users: List[AppUser]):
        self._users = list(users)
        self.table.setRowCount(len(self._users))

        for row, user in enumerate(self._users):
            self._set_cell(row, 0, str(user.account_id))
            self._set_cell(row, 1, user.username)
            self._set_cell(row, 2, user.full_name or "")
            self._set_cell(row, 3, user.email or "")
            self._set_cell(row, 4, user.phone_number or "")
            self._set_cell(row, 5, user.roles_display())
            self._set_cell(row, 6, "Sí" if user.is_active else "No")

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.on_selection_changed()
        self._update_summary()

    def _on_mutation_succeeded(self, message: str):
        show_info(self, message or "Operación exitosa", title="Usuarios")

    def _on_error(self, message: str):
        show_error(self, message or "Ocurrió un error.", title="Usuarios")

    def _set_cell(self, row: int, col: int, text: str):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Selection / actions
    # ------------------------------------------------------------------
    def _selected_user(self) -> Optional[AppUser]:
        row = self.table.currentRow()
        if 0 <= row < len(self._users):
            return self._users[row]
        return None

    def on_selection_changed(self):
        user = self._selected_user()
        has_selection = user is not None and self._can_manage
        self.edit_btn.setEnabled(has_selection)
        self.password_btn.setEnabled(has_selection)
        self.deactivate_btn.setEnabled(has_selection and bool(user and user.is_active))
        self.reactivate_btn.setEnabled(has_selection and bool(user and not user.is_active))

    def on_new_clicked(self):
        if not self._can_manage:
            return
        if not self._roles:
            show_error(self, "No hay roles disponibles para asignar.", title="Usuarios")
            return
        dialog = UserDialog(self, roles=self._roles)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.create_user(dialog.get_data())

    def on_edit_clicked(self):
        if not self._can_manage:
            return
        user = self._selected_user()
        if not user:
            return
        dialog = UserDialog(self, roles=self._roles, user=user)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.update_user(user.account_id, dialog.get_data())

    def on_reset_password_clicked(self):
        if not self._can_manage:
            return
        user = self._selected_user()
        if not user:
            return
        password, ok = QInputDialog.getText(
            self,
            "Restablecer contraseña",
            f"Nueva contraseña para «{user.username}»:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if not (password or "").strip():
            show_error(self, "La contraseña no puede estar vacía.", title="Usuarios")
            return
        self.controller.reset_password(user.account_id, password)

    def on_deactivate_clicked(self):
        if not self._can_manage:
            return
        user = self._selected_user()
        if not user:
            return
        if show_confirmation(
            self,
            f"¿Desactivar al usuario '{user.username}'? No podrá iniciar sesión, "
            f"pero se conservará su historial. Podrás reactivarlo luego.",
            title="Desactivar usuario",
            ok_text="Desactivar",
            cancel_text="Cancelar",
        ):
            self.controller.deactivate_user(user.account_id)

    def on_reactivate_clicked(self):
        if not self._can_manage:
            return
        user = self._selected_user()
        if not user:
            return
        self.controller.activate_user(user.account_id)

    def _update_summary(self):
        active = sum(1 for u in self._users if u.is_active)
        total = len(self._users)
        self.summary_label.setText(f"{total} usuarios ({active} activos)")


class UserDialog(QDialog):
    """Diálogo para crear/editar una cuenta de acceso."""

    def __init__(self, parent=None, roles: Optional[List[AppRole]] = None, user: Optional[AppUser] = None):
        super().__init__(parent)
        self.user = user
        self._roles = roles or []
        self.setup_ui()
        if user:
            self.load_user(user)

    def setup_ui(self):
        self.setWindowTitle("Editar Usuario" if self.user else "Nuevo Usuario")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._form = form

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("Ej: Juan Pérez")
        form.addRow("Nombre:", self.full_name_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Ej: jperez")
        form.addRow("Usuario:", self.username_input)

        # Password only on creation; edits use "Restablecer contraseña".
        if not self.user:
            self.password_input = QLineEdit()
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.password_input.setPlaceholderText("Contraseña inicial")
            form.addRow("Contraseña:", self.password_input)
        else:
            self.password_input = None

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("opcional")
        form.addRow("Email:", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("opcional")
        form.addRow("Teléfono:", self.phone_input)

        # Multi-select de roles.
        self.roles_list = QListWidget()
        self.roles_list.setMaximumHeight(140)
        for role in self._roles:
            item = QListWidgetItem(role.display())
            item.setData(Qt.ItemDataRole.UserRole, role.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.roles_list.addItem(item)
        form.addRow("Roles:", self.roles_list)

        # Activo (solo en edición).
        self.active_input = QCheckBox("Usuario activo (puede iniciar sesión)")
        self.active_input.setChecked(True)
        if self.user:
            form.addRow("Estado:", self.active_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_user(self, user: AppUser):
        self.full_name_input.setText(user.full_name or "")
        self.username_input.setText(user.username or "")
        self.email_input.setText(user.email or "")
        self.phone_input.setText(user.phone_number or "")
        self.active_input.setChecked(bool(user.is_active))
        assigned = set(user.role_ids())
        for i in range(self.roles_list.count()):
            item = self.roles_list.item(i)
            role_id = int(item.data(Qt.ItemDataRole.UserRole))
            item.setCheckState(
                Qt.CheckState.Checked if role_id in assigned else Qt.CheckState.Unchecked
            )

    def _selected_role_ids(self) -> List[int]:
        ids: List[int] = []
        for i in range(self.roles_list.count()):
            item = self.roles_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _on_accept(self):
        if not self.full_name_input.text().strip():
            show_error(self, "El nombre es obligatorio.", title="Datos incompletos")
            return
        if not self.username_input.text().strip():
            show_error(self, "El usuario es obligatorio.", title="Datos incompletos")
            return
        if self.password_input is not None and not self.password_input.text().strip():
            show_error(self, "La contraseña es obligatoria.", title="Datos incompletos")
            return
        if not self._selected_role_ids():
            show_error(self, "Debes asignar al menos un rol.", title="Datos incompletos")
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "full_name": self.full_name_input.text().strip(),
            "username": self.username_input.text().strip(),
            "email": self.email_input.text().strip() or None,
            "phone_number": self.phone_input.text().strip() or None,
            "role_ids": self._selected_role_ids(),
            "is_active": self.active_input.isChecked(),
        }
        if self.password_input is not None:
            data["password"] = self.password_input.text()
        return data
