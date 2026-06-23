"""Controller for the Productos catalog tab + POS product picker."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class ProductsController(BaseController):
    products_loaded = Signal(list)
    action_completed = Signal(str, str)
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, products_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._svc = products_service

    def load_products(self, include_inactive: bool = True, search: Optional[str] = None) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._svc, "get_products", self._on_loaded, self._on_error,
            include_inactive=include_inactive, search=search,
        )

    def create_product(self, data: Dict[str, Any]) -> None:
        self._execute_authenticated_operation(
            self._svc, "create_product", self._on_action, self._on_error, data=data,
        )

    def update_product(self, product_id: int, data: Dict[str, Any]) -> None:
        self._execute_authenticated_operation(
            self._svc, "update_product", self._on_action, self._on_error,
            product_id=product_id, data=data,
        )

    def set_product_active(self, product_id: int, is_active: bool) -> None:
        self._execute_authenticated_operation(
            self._svc, "set_product_active", self._on_action, self._on_error,
            product_id=product_id, is_active=is_active,
        )

    @Slot(object)
    def _on_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.products_loaded.emit(list(result or []))

    @Slot(object)
    def _on_action(self, result: Any) -> None:
        if isinstance(result, dict) and result.get("success"):
            self.action_completed.emit("Productos", result.get("message") or "Operación completada")
            self.load_products()
        else:
            msg = result.get("message") if isinstance(result, dict) else "Error en la operación"
            self.error_occurred.emit(msg or "Error en la operación")

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self.loading_changed.emit(False)
        self.error_occurred.emit(error)
