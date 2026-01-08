"""
Dialog utilities for FitPilot frontend.

Provides standardized dialog functions for:
- Error messages
- Success messages
- Information messages
- Confirmation dialogs
"""

from typing import Optional
from PySide6.QtWidgets import QMessageBox, QWidget
from PySide6.QtCore import Qt


def show_error(
    parent: Optional[QWidget],
    message: str,
    title: str = "Error",
    detailed_text: Optional[str] = None,
) -> None:
    """
    Show a standardized error message dialog.

    Args:
        parent: Parent widget (can be None)
        message: Error message to display
        title: Dialog title (default: "Error")
        detailed_text: Optional detailed error information

    Examples:
        >>> show_error(self, "No se pudo conectar al servidor")
        >>> show_error(self, "Error en el formulario", detailed_text="Campo 'email' inválido")
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    if detailed_text:
        msg_box.setDetailedText(detailed_text)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_success(
    parent: Optional[QWidget],
    message: str,
    title: str = "Éxito",
) -> None:
    """
    Show a standardized success message dialog.

    Args:
        parent: Parent widget (can be None)
        message: Success message to display
        title: Dialog title (default: "Éxito")

    Examples:
        >>> show_success(self, "Suscripción renovada correctamente")
        >>> show_success(self, "Datos guardados", title="Operación exitosa")
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_info(
    parent: Optional[QWidget],
    message: str,
    title: str = "Información",
    detailed_text: Optional[str] = None,
) -> None:
    """
    Show a standardized information message dialog.

    Args:
        parent: Parent widget (can be None)
        message: Information message to display
        title: Dialog title (default: "Información")
        detailed_text: Optional detailed information

    Examples:
        >>> show_info(self, "No hay miembros activos actualmente")
        >>> show_info(self, "Sistema actualizado", detailed_text="Versión 2.0")
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    if detailed_text:
        msg_box.setDetailedText(detailed_text)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_warning(
    parent: Optional[QWidget],
    message: str,
    title: str = "Advertencia",
    detailed_text: Optional[str] = None,
) -> None:
    """
    Show a standardized warning message dialog.

    Args:
        parent: Parent widget (can be None)
        message: Warning message to display
        title: Dialog title (default: "Advertencia")
        detailed_text: Optional detailed warning information

    Examples:
        >>> show_warning(self, "La suscripción expira pronto")
        >>> show_warning(self, "Datos incompletos", detailed_text="Falta el email")
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    if detailed_text:
        msg_box.setDetailedText(detailed_text)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_confirmation(
    parent: Optional[QWidget],
    message: str,
    title: str = "Confirmar",
    ok_text: str = "Aceptar",
    cancel_text: str = "Cancelar",
) -> bool:
    """
    Show a confirmation dialog with Yes/No buttons.

    Args:
        parent: Parent widget (can be None)
        message: Confirmation message to display
        title: Dialog title (default: "Confirmar")
        ok_text: Text for OK button (default: "Aceptar")
        cancel_text: Text for Cancel button (default: "Cancelar")

    Returns:
        True if user clicked OK, False if cancelled

    Examples:
        >>> if show_confirmation(self, "¿Desea eliminar este registro?"):
        ...     delete_record()
        >>> if show_confirmation(self, "¿Guardar cambios?", ok_text="Sí", cancel_text="No"):
        ...     save_changes()
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    ok_button = msg_box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    msg_box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)

    msg_box.exec()

    return msg_box.clickedButton() == ok_button


def show_yes_no_cancel(
    parent: Optional[QWidget],
    message: str,
    title: str = "Confirmar",
) -> str:
    """
    Show a dialog with Yes/No/Cancel options.

    Args:
        parent: Parent widget (can be None)
        message: Message to display
        title: Dialog title (default: "Confirmar")

    Returns:
        "yes", "no", or "cancel" based on user selection

    Examples:
        >>> result = show_yes_no_cancel(self, "¿Desea guardar los cambios?")
        >>> if result == "yes":
        ...     save()
        >>> elif result == "no":
        ...     discard()
        >>> else:
        ...     # User cancelled
        ...     pass
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    yes_button = msg_box.addButton("Sí", QMessageBox.ButtonRole.YesRole)
    no_button = msg_box.addButton("No", QMessageBox.ButtonRole.NoRole)
    msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

    msg_box.exec()

    clicked = msg_box.clickedButton()
    if clicked == yes_button:
        return "yes"
    elif clicked == no_button:
        return "no"
    else:
        return "cancel"


def show_input_error(
    parent: Optional[QWidget],
    field_name: str,
    error_message: str,
) -> None:
    """
    Show a standardized input validation error.

    Args:
        parent: Parent widget (can be None)
        field_name: Name of the field with error
        error_message: Description of the error

    Examples:
        >>> show_input_error(self, "Email", "Formato inválido")
        >>> show_input_error(self, "Monto", "Debe ser mayor a cero")
    """
    message = f"Error en el campo '{field_name}':\n{error_message}"
    show_error(parent, message, title="Error de Validación")


def show_service_unavailable(
    parent: Optional[QWidget],
    service_name: str = "el servicio",
) -> None:
    """
    Show a standardized "service unavailable" error.

    Args:
        parent: Parent widget (can be None)
        service_name: Name of the unavailable service

    Examples:
        >>> show_service_unavailable(self, "servidor de autenticación")
        >>> show_service_unavailable(self)
    """
    message = (
        f"No se pudo conectar con {service_name}.\n\n"
        "Por favor, verifica tu conexión e intenta nuevamente."
    )
    show_error(parent, message, title="Servicio No Disponible")


def show_operation_success(
    parent: Optional[QWidget],
    operation: str,
) -> None:
    """
    Show a standardized operation success message.

    Args:
        parent: Parent widget (can be None)
        operation: Description of the operation

    Examples:
        >>> show_operation_success(self, "Suscripción renovada")
        >>> show_operation_success(self, "Miembro registrado")
    """
    message = f"{operation} correctamente."
    show_success(parent, message)


def show_delete_confirmation(
    parent: Optional[QWidget],
    item_name: str,
) -> bool:
    """
    Show a standardized delete confirmation dialog.

    Args:
        parent: Parent widget (can be None)
        item_name: Name of the item to delete

    Returns:
        True if user confirmed deletion

    Examples:
        >>> if show_delete_confirmation(self, "este miembro"):
        ...     delete_member()
    """
    message = (
        f"¿Está seguro que desea eliminar {item_name}?\n\n"
        "Esta acción no se puede deshacer."
    )
    return show_confirmation(
        parent,
        message,
        title="Confirmar Eliminación",
        ok_text="Eliminar",
        cancel_text="Cancelar",
    )
