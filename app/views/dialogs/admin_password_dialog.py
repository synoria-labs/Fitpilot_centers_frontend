"""Dialog to confirm destructive actions requesting the admin password."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
)
from PySide6.QtCore import Qt


class AdminPasswordDialog(QDialog):
    """Simple dialog that prompts for the administrator password."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._password = ""
        self.setWindowTitle("Confirmar eliminacion")
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        message = QLabel(
            "Ingresa la contrasena de administrador para eliminar al socio seleccionado."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #d32f2f; font-size: 12px;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Contrasena de administrador")
        layout.addWidget(self.password_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        confirm_button.setText("Eliminar")
        confirm_button.setDefault(True)
        confirm_button.setStyleSheet(
            "QPushButton {background-color: #d32f2f; color: white; padding: 6px 16px; border-radius: 6px;}"
            "QPushButton:hover {background-color: #b71c1c;}"
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.password_input.returnPressed.connect(confirm_button.click)
        self.password_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    @property
    def password(self) -> str:
        """Return the password entered by the user."""
        return self._password

    def accept(self) -> None:  # type: ignore[override]
        password = self.password_input.text().strip()
        if not password:
            self.error_label.setText("La contrasena es obligatoria.")
            self.error_label.setVisible(True)
            self.password_input.setFocus()
            return

        self._password = password
        self.error_label.setVisible(False)
        super().accept()

