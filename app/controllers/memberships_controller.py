"""Controller orchestrating the membership-plan catalog (Membresías tab)."""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.base import MembershipPlan
from .base_controller import BaseController

logger = get_logger(__name__)


class MembershipsController(BaseController):
    """Coordinates plan CRUD service calls and exposes view-friendly signals."""

    plans_loaded = Signal(object)        # List[MembershipPlan]
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    mutation_succeeded = Signal(str)     # message
    mutation_failed = Signal(str)        # message

    def __init__(self, memberships_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = memberships_service
        self._plans: List[MembershipPlan] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plans(self) -> List[MembershipPlan]:
        return self._plans

    def load_plans(self, include_inactive: bool = True) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de membresías no disponible")
            return

        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "get_plans",
            self._on_plans_loaded,
            self._on_plans_error,
            include_inactive=include_inactive,
        )

    def create_plan(self, data: dict) -> None:
        self._run_mutation("create_plan", data=data)

    def update_plan(self, plan_id: int, data: dict) -> None:
        self._run_mutation("update_plan", plan_id=int(plan_id), data=data)

    def deactivate_plan(self, plan_id: int) -> None:
        self._run_mutation("set_plan_active", plan_id=int(plan_id), is_active=False)

    def activate_plan(self, plan_id: int) -> None:
        self._run_mutation("set_plan_active", plan_id=int(plan_id), is_active=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_mutation(self, method_name: str, **kwargs: Any) -> None:
        if not self._service:
            self.mutation_failed.emit("Servicio de membresías no disponible")
            return
        self._execute_authenticated_operation(
            self._service,
            method_name,
            self._on_mutation_done,
            self._on_mutation_error,
            **kwargs,
        )

    @Slot(object)
    def _on_plans_loaded(self, result: Any) -> None:
        plans = result or []
        self._plans = list(plans)
        self.loading_changed.emit(False)
        self.plans_loaded.emit(self._plans)

    @Slot(str)
    def _on_plans_error(self, error: str) -> None:
        logger.error("Failed to load plans: %s", error)
        self.loading_changed.emit(False)
        self.error_occurred.emit(error or "No se pudieron cargar los planes.")

    @Slot(object)
    def _on_mutation_done(self, result: Any) -> None:
        success = bool(result.get("success")) if isinstance(result, dict) else False
        message = result.get("message", "") if isinstance(result, dict) else ""

        if success:
            self.mutation_succeeded.emit(message or "Operación exitosa")
            # Refresh the catalog from the backend (authoritative state).
            self.load_plans()
        else:
            self.mutation_failed.emit(message or "No se pudo completar la operación.")

    @Slot(str)
    def _on_mutation_error(self, error: str) -> None:
        logger.error("Plan mutation failed: %s", error)
        self.mutation_failed.emit(error or "Ocurrió un error en la operación.")
