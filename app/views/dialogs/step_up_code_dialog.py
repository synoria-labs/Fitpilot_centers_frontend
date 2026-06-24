"""Modal dialog to collect the 6-digit email OTP for step-up verification.

Used by any sensitive action (password reset, self-update) when the gym backend
requires a single-use proof. The dialog only submits the code to the caller
once the user clicks "Verificar"; the caller is responsible for sending the
code via :class:`VerificationService.verify_step_up_code`.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class StepUpCodeDialog(QDialog):
    """Prompt the user for the 6-digit code sent to their email."""

    def __init__(
        self,
        parent=None,
        *,
        masked_destination: Optional[str] = None,
        title: str = "Verificación por correo",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        if masked_destination:
            intro = QLabel(
                f"Enviamos un código de 6 dígitos a {masked_destination}. "
                f"Ingrésalo para continuar."
            )
        else:
            intro = QLabel(
                "Enviamos un código de 6 dígitos a tu correo. "
                "Ingrésalo para continuar."
            )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self._code_input = QLineEdit()
        self._code_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self._code_input.setMaxLength(6)
        self._code_input.setPlaceholderText("000000")
        form.addRow("Código:", self._code_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Verificar")
        buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Cancelar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        code = self._code_input.text().strip()
        if not code or not code.isdigit() or len(code) != 6:
            self._code_input.setFocus()
            return
        self.accept()

    def code(self) -> str:
        return self._code_input.text().strip()
