"""Controller orchestrating user (login account) management — Usuarios section."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from ..core.di import container
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
    step_up_prompt = Signal(str)         # masked destination (e.g. "al***@gmail.com")

    def __init__(self, users_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = users_service
        self._users: List[AppUser] = []
        self._roles: List[AppRole] = []

        # Step-up (2FA) orchestration state. When a sensitive mutation is rejected
        # with a step-up challenge, we hold the original call here, run the 2FA
        # flow, and retry it with the resulting proof.
        try:
            self._verification = container.get("verification_service")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("verification_service unavailable: %s", exc)
            self._verification = None
        self._pending_op: Optional[Tuple[str, Dict[str, Any]]] = None
        self._pending_verification_id: Optional[str] = None
        self._awaiting_proof: bool = False

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
        # Remember this call so we can transparently retry it with a step-up
        # proof if the backend answers with a 2-step verification challenge.
        self._pending_op = (method_name, dict(kwargs))
        self._pending_verification_id = None
        self._awaiting_proof = False
        self._execute_authenticated_operation(
            self._service,
            method_name,
            self._on_mutation_done,
            self._on_mutation_error,
            **kwargs,
        )

    def _reset_step_up_state(self) -> None:
        self._pending_op = None
        self._pending_verification_id = None
        self._awaiting_proof = False

    @staticmethod
    def _is_step_up_challenge(message: str) -> bool:
        """The backend rejects with 'Se requiere verificación de 2 pasos'."""
        return "2 pasos" in (message or "").lower()

    # ------------------------------------------------------------------
    # Step-up (2FA) flow: request code -> prompt -> verify -> retry
    # ------------------------------------------------------------------
    def _begin_step_up(self) -> None:
        if not self._verification:
            self._reset_step_up_state()
            self.mutation_failed.emit("Servicio de verificación no disponible")
            return
        self._execute_authenticated_operation(
            self._verification,
            "request_step_up",
            self._on_stepup_requested,
            self._on_mutation_error,
            channel="email",
        )

    @Slot(object)
    def _on_stepup_requested(self, result: Any) -> None:
        success = bool(result.get("success")) if isinstance(result, dict) else False
        if not success:
            message = result.get("message", "") if isinstance(result, dict) else ""
            self._reset_step_up_state()
            self.mutation_failed.emit(message or "No se pudo enviar el código de verificación.")
            return
        self._pending_verification_id = result.get("verification_id")
        masked = result.get("masked_destination") or "tu correo"
        self.step_up_prompt.emit(masked)

    def submit_step_up_code(self, code: str) -> None:
        """Called by the view once the admin enters the emailed code."""
        if not self._pending_verification_id:
            self._reset_step_up_state()
            self.mutation_failed.emit("La verificación expiró. Intenta de nuevo.")
            return
        self._execute_authenticated_operation(
            self._verification,
            "verify_step_up",
            self._on_stepup_verified,
            self._on_mutation_error,
            verification_id=self._pending_verification_id,
            code=code,
        )

    @Slot(object)
    def _on_stepup_verified(self, result: Any) -> None:
        success = bool(result.get("success")) if isinstance(result, dict) else False
        proof = result.get("proof") if isinstance(result, dict) else None
        if not success or not proof:
            message = result.get("message", "") if isinstance(result, dict) else ""
            self._reset_step_up_state()
            self.mutation_failed.emit(message or "Código de verificación inválido.")
            return
        if not self._pending_op:
            self._reset_step_up_state()
            self.mutation_failed.emit("No hay operación pendiente para completar.")
            return
        method_name, kwargs = self._pending_op
        retry_kwargs = dict(kwargs)
        retry_kwargs["step_up_proof"] = proof
        # Mark the retry terminal so an invalid/expired proof (whose message also
        # contains "2 pasos") cannot re-trigger the challenge and loop.
        self._awaiting_proof = True
        self._execute_authenticated_operation(
            self._service,
            method_name,
            self._on_mutation_done,
            self._on_mutation_error,
            **retry_kwargs,
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
            self._reset_step_up_state()
            self.mutation_succeeded.emit(message or "Operación exitosa")
            # Refresh from backend (authoritative state).
            self.load_users()
            return

        # Step-up challenge on the first attempt: run the 2FA flow and retry.
        if not self._awaiting_proof and self._pending_op and self._is_step_up_challenge(message):
            self._begin_step_up()
            return

        self._reset_step_up_state()
        self.mutation_failed.emit(message or "No se pudo completar la operación.")

    @Slot(str)
    def _on_mutation_error(self, error: str) -> None:
        logger.error("User mutation failed: %s", error)
        self._reset_step_up_state()
        self.mutation_failed.emit(error or "Ocurrió un error en la operación.")
