"""Controller for the POS (Punto de Venta) tab."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class PosController(BaseController):
    plans_loaded = Signal(list)
    members_loaded = Signal(list)
    sale_completed = Signal(object)      # sale dict
    loading_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(
        self,
        pos_service: Any,
        members_service: Any,
        memberships_service: Any,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._pos = pos_service
        self._members = members_service
        self._memberships = memberships_service

    # ------------------------------------------------------------------ loads
    def load_plans(self) -> None:
        self._execute_authenticated_operation(
            self._memberships, "get_plans", self._on_plans_loaded, self._on_error,
            include_inactive=False,
        )

    def search_members(self, query: str) -> None:
        self._execute_authenticated_operation(
            self._members, "get_members", self._on_members_loaded, self._on_error,
            search=query or None, limit=20, offset=0,
        )

    # ------------------------------------------------------------------ sale
    def finalize_sale(
        self,
        line_items: List[Dict[str, Any]],
        payments: List[Dict[str, Any]],
        person_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._pos, "create_sale", self._on_sale_done, self._on_error,
            line_items=line_items, payments=payments, person_id=person_id, note=note,
        )

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_plans_loaded(self, result: Any) -> None:
        self.plans_loaded.emit(list(result or []))

    @Slot(object)
    def _on_members_loaded(self, result: Any) -> None:
        items = result.get("items") if isinstance(result, dict) else (result or [])
        self.members_loaded.emit(list(items or []))

    @Slot(object)
    def _on_sale_done(self, result: Any) -> None:
        self.loading_changed.emit(False)
        if isinstance(result, dict) and result.get("success"):
            self.sale_completed.emit(result.get("sale"))
        else:
            message = result.get("message") if isinstance(result, dict) else "Error al registrar la venta"
            self.error_occurred.emit(message or "Error al registrar la venta")

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self.loading_changed.emit(False)
        self.error_occurred.emit(error)
