"""Controller for the role-capability settings section."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class PermissionsController(BaseController):
    """Loads the role/capability matrix and applies grant/revoke changes."""

    matrix_loaded = Signal(object)       # {"roles": [...], "capabilities": [...]}
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    mutation_succeeded = Signal(str)
    mutation_failed = Signal(str)

    def __init__(self, permissions_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = permissions_service

    def load_matrix(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de permisos no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "get_role_capabilities",
            self._on_loaded,
            self._on_error,
        )

    def set_grant(self, role_code: str, capability: str, granted: bool) -> None:
        method = "grant" if granted else "revoke"
        self._execute_authenticated_operation(
            self._service,
            method,
            self._on_mutation_done,
            self._on_mutation_error,
            role_code=role_code,
            capability=capability,
        )

    @Slot(object)
    def _on_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.matrix_loaded.emit(result or {"roles": [], "capabilities": []})

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self.loading_changed.emit(False)
        self.error_occurred.emit(error or "No se pudieron cargar los permisos.")

    @Slot(object)
    def _on_mutation_done(self, result: Any) -> None:
        success = bool(result.get("success")) if isinstance(result, dict) else False
        message = result.get("message", "") if isinstance(result, dict) else ""
        if success:
            self.mutation_succeeded.emit(message or "Permiso actualizado")
            self.load_matrix()
        else:
            self.mutation_failed.emit(message or "No se pudo actualizar el permiso.")

    @Slot(str)
    def _on_mutation_error(self, error: str) -> None:
        logger.error("Permission mutation failed: %s", error)
        self.mutation_failed.emit(error or "Ocurrió un error.")
