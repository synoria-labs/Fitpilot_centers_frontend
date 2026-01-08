"""Base controller with common functionality for all controllers."""

from typing import Any, Callable, Optional, Set
from PySide6.QtCore import QObject

from ..threads.authenticated_operations import AuthenticatedOperation
from ..core.logging import get_logger

logger = get_logger(__name__)


class BaseController(QObject):
    """
    Base controller providing common functionality for all controllers.

    Features:
    - Simplified authenticated operation execution
    - Operation tracking and cleanup
    - Consistent error handling patterns
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pending_operations: Set[AuthenticatedOperation] = set()

    def _execute_authenticated_operation(
        self,
        service: Any,
        method_name: str,
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
        track: bool = True,
        **kwargs: Any,
    ) -> AuthenticatedOperation:
        """
        Execute an authenticated operation with automatic signal connection.

        This helper method eliminates the boilerplate code of creating operations,
        connecting signals, and tracking operations.

        Args:
            service: Service instance to call the method on
            method_name: Name of the service method to call
            on_success: Callback for successful operation (receives result)
            on_error: Callback for error (receives error message)
            track: Whether to track this operation (default: True)
            **kwargs: Arguments to pass to the service method

        Returns:
            The created AuthenticatedOperation instance

        Examples:
            >>> # Simple usage
            >>> self._execute_authenticated_operation(
            ...     self._members_service,
            ...     "get_members",
            ...     self._on_members_loaded,
            ...     self._on_members_error,
            ...     limit=100,
            ...     search="John"
            ... )

            >>> # Without tracking (for lightweight operations)
            >>> self._execute_authenticated_operation(
            ...     self._service,
            ...     "quick_check",
            ...     self._on_check_done,
            ...     self._on_check_error,
            ...     track=False
            ... )
        """
        operation = AuthenticatedOperation(
            service,
            method_name,
            self,
            **kwargs,
        )

        operation.success.connect(on_success)
        operation.error.connect(on_error)

        if track:
            self._track_operation(operation)

        operation.execute()

        return operation

    def _track_operation(self, operation: AuthenticatedOperation) -> None:
        """
        Track an operation and ensure it's cleaned up on completion.

        Args:
            operation: Operation to track
        """
        self._pending_operations.add(operation)

        def _cleanup(*_: Any) -> None:
            if operation in self._pending_operations:
                self._pending_operations.discard(operation)

        operation.success.connect(_cleanup)
        operation.error.connect(_cleanup)

    def _cancel_pending_operations(self) -> None:
        """
        Cancel all pending operations.

        Useful during cleanup or when switching contexts.
        """
        operations = list(self._pending_operations)
        for operation in operations:
            try:
                # AuthenticatedOperation doesn't have a cancel method,
                # but we can disconnect signals to prevent callbacks
                operation.success.disconnect()
                operation.error.disconnect()
            except RuntimeError:
                # Signals already disconnected
                pass
            finally:
                self._pending_operations.discard(operation)

        logger.debug(
            "Cancelled %d pending operations in %s",
            len(operations),
            self.__class__.__name__,
        )

    def _get_pending_operation_count(self) -> int:
        """
        Get the number of pending operations.

        Returns:
            Number of operations currently being tracked
        """
        return len(self._pending_operations)

    def _has_pending_operations(self) -> bool:
        """
        Check if there are any pending operations.

        Returns:
            True if operations are pending
        """
        return len(self._pending_operations) > 0
