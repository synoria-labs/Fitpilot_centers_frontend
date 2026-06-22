"""Controller orchestrating user (login account) management — Usuarios section."""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.base import AppUser, AppRole
from .base_controller import BaseController

logger = get_logger(__name__)


class UsersController(BaseController):
    """Coordinates user CRUD service calls and exposes view-friendly signals."""

    users_loaded = Signal(object)        # List[AppUser]
    roles_loaded = Signal(object)        # List[AppRole]
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    mutation_succeeded = Signal(str)     # message
    mutation_failed = Signal(str)        # message

    def __init__(self, users_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = users_service
        self._users: List[AppUser] = []
        self._roles: List[AppRole] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def users(self) -> List[AppUser]:
        return self._users

    def roles(self) -> List[AppRole]:
        return self._roles

    def load_users(self, include_inactive: bool = True) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de usuarios no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "get_users",
            self._on_users_loaded,
            self._on_users_error,
            include_inactive=include_inactive,
        )

    def load_roles(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de usuarios no disponible")
            return
        self._execute_authenticated_operation(
            self._service,
            "get_roles",
            self._on_roles_loaded,
            self._on_roles_error,
        )

    def create_user(self, data: dict) -> None:
        self._run_mutation("create_user", data=data)

    def update_user(self, account_id: int, data: dict) -> None:
        self._run_mutation("update_user", account_id=int(account_id), data=data)

    def deactivate_user(self, account_id: int) -> None:
        self._run_mutation("set_user_active", account_id=int(account_id), is_active=False)

    def activate_user(self, account_id: int) -> None:
        self._run_mutation("set_user_active", account_id=int(account_id), is_active=True)

    def reset_password(self, account_id: int, password: str) -> None:
        self._run_mutation("reset_password", account_id=int(account_id), password=password)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_mutation(self, method_name: str, **kwargs: Any) -> None:
        if not self._service:
            self.mutation_failed.emit("Servicio de usuarios no disponible")
            return
        self._execute_authenticated_operation(
            self._service,
            method_name,
            self._on_mutation_done,
            self._on_mutation_error,
            **kwargs,
        )

    @Slot(object)
    def _on_users_loaded(self, result: Any) -> None:
        self._users = list(result or [])
        self.loading_changed.emit(False)
        self.users_loaded.emit(self._users)

    @Slot(str)
    def _on_users_error(self, error: str) -> None:
        logger.error("Failed to load users: %s", error)
        self.loading_changed.emit(False)
        self.error_occurred.emit(error or "No se pudieron cargar los usuarios.")

    @Slot(object)
    def _on_roles_loaded(self, result: Any) -> None:
        self._roles = list(result or [])
        self.roles_loaded.emit(self._roles)

    @Slot(str)
    def _on_roles_error(self, error: str) -> None:
        logger.error("Failed to load roles: %s", error)
        self.error_occurred.emit(error or "No se pudieron cargar los roles.")

    @Slot(object)
    def _on_mutation_done(self, result: Any) -> None:
        success = bool(result.get("success")) if isinstance(result, dict) else False
        message = result.get("message", "") if isinstance(result, dict) else ""

        if success:
            self.mutation_succeeded.emit(message or "Operación exitosa")
            # Refresh from backend (authoritative state).
            self.load_users()
        else:
            self.mutation_failed.emit(message or "No se pudo completar la operación.")

    @Slot(str)
    def _on_mutation_error(self, error: str) -> None:
        logger.error("User mutation failed: %s", error)
        self.mutation_failed.emit(error or "Ocurrió un error en la operación.")
