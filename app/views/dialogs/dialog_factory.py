"""
Factory for creating dialog instances.

Provides centralized dialog creation with consistent configuration
and dependency injection.
"""

from typing import Any, Optional
from PySide6.QtWidgets import QDialog, QWidget

from ...core.logging import get_logger

logger = get_logger(__name__)


class DialogFactory:
    """
    Factory class for creating application dialogs.

    Centralizes dialog instantiation to ensure consistent configuration
    and proper dependency injection.
    """

    @staticmethod
    def create_subscription_dialog(
        dialog_type: str,
        controller: Any,
        member_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> Optional[QDialog]:
        """
        Create a subscription-related dialog.

        Args:
            dialog_type: Type of dialog ("new" or "renew")
            controller: Controller instance for the dialog
            member_id: Optional member ID (for renewals)
            parent: Parent widget

        Returns:
            Dialog instance or None if type is invalid

        Examples:
            >>> # Create new subscription dialog
            >>> dialog = DialogFactory.create_subscription_dialog(
            ...     "new", controller, parent=main_window
            ... )

            >>> # Create renewal dialog
            >>> dialog = DialogFactory.create_subscription_dialog(
            ...     "renew", controller, member_id=123, parent=main_window
            ... )
        """
        if dialog_type == "new":
            from .new_subscription_dialog import NewSubscriptionDialog

            logger.info("Creating new subscription dialog")
            return NewSubscriptionDialog(controller=controller, parent=parent)

        elif dialog_type == "renew":
            from .renew_subscription_dialog import RenewSubscriptionDialog

            if member_id is None:
                logger.error("member_id is required for renew subscription dialog")
                return None

            logger.info(f"Creating renew subscription dialog for member {member_id}")
            return RenewSubscriptionDialog(
                controller=controller, member_id=member_id, parent=parent
            )

        else:
            logger.error(f"Unknown subscription dialog type: {dialog_type}")
            return None

    @staticmethod
    def create_admin_password_dialog(
        parent: Optional[QWidget] = None,
    ) -> Optional[QDialog]:
        """
        Create an admin password confirmation dialog.

        Args:
            parent: Parent widget

        Returns:
            Dialog instance

        Example:
            >>> dialog = DialogFactory.create_admin_password_dialog(parent=main_window)
            >>> if dialog.exec() == QDialog.DialogCode.Accepted:
            ...     password = dialog.get_password()
        """
        from .admin_password_dialog import AdminPasswordDialog

        logger.info("Creating admin password dialog")
        return AdminPasswordDialog(parent=parent)

    @staticmethod
    def create_sessions_dialog(
        parent: Optional[QWidget] = None,
    ) -> Optional[QDialog]:
        """
        Create a sessions management dialog.

        Args:
            parent: Parent widget

        Returns:
            Dialog instance

        Example:
            >>> dialog = DialogFactory.create_sessions_dialog(parent=main_window)
            >>> dialog.exec()
        """
        from .sessions_dialog import SessionsDialog

        logger.info("Creating sessions dialog")
        return SessionsDialog(parent=parent)

    @staticmethod
    def create_dialog(
        dialog_name: str,
        parent: Optional[QWidget] = None,
        **kwargs: Any,
    ) -> Optional[QDialog]:
        """
        Generic dialog factory method.

        Creates any dialog by name with arbitrary keyword arguments.

        Args:
            dialog_name: Name of the dialog to create
            parent: Parent widget
            **kwargs: Additional arguments for the dialog constructor

        Returns:
            Dialog instance or None if not found

        Example:
            >>> dialog = DialogFactory.create_dialog(
            ...     "admin_password",
            ...     parent=main_window
            ... )
        """
        dialog_map = {
            "admin_password": DialogFactory.create_admin_password_dialog,
            "sessions": DialogFactory.create_sessions_dialog,
        }

        factory_func = dialog_map.get(dialog_name)
        if factory_func:
            return factory_func(parent=parent, **kwargs)

        logger.warning(f"Unknown dialog name: {dialog_name}")
        return None


# Convenience functions
def show_subscription_dialog(
    dialog_type: str,
    controller: Any,
    member_id: Optional[int] = None,
    parent: Optional[QWidget] = None,
) -> bool:
    """
    Create and show a subscription dialog.

    Args:
        dialog_type: "new" or "renew"
        controller: Controller instance
        member_id: Optional member ID for renewals
        parent: Parent widget

    Returns:
        True if dialog was accepted, False otherwise

    Example:
        >>> if show_subscription_dialog("new", controller, parent=main_window):
        ...     print("Subscription created successfully")
    """
    dialog = DialogFactory.create_subscription_dialog(
        dialog_type, controller, member_id, parent
    )

    if dialog:
        result = dialog.exec()
        return result == QDialog.DialogCode.Accepted

    return False


def show_admin_password_dialog(parent: Optional[QWidget] = None) -> Optional[str]:
    """
    Show admin password dialog and return the password if accepted.

    Args:
        parent: Parent widget

    Returns:
        Password string if accepted, None if cancelled

    Example:
        >>> password = show_admin_password_dialog(parent=main_window)
        >>> if password:
        ...     # Proceed with admin operation
        ...     delete_member(password)
    """
    dialog = DialogFactory.create_admin_password_dialog(parent)

    if dialog and dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_password()

    return None
