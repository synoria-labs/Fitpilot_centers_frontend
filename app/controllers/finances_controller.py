"""Controller for the Finances Tab (Payments CRUD + metrics panel)."""
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.payment_filters import FilterPreset, PaymentFilters
from .base_controller import BaseController

logger = get_logger(__name__)


@dataclass
class FinancesState:
    payments: List[dict] = field(default_factory=list)
    total: int = 0
    metrics: Optional[Dict[str, Any]] = None
    filters: PaymentFilters = field(
        default_factory=lambda: PaymentFilters.from_preset(FilterPreset.THIS_MONTH)
    )
    loading_payments: bool = False
    loading_metrics: bool = False

    @property
    def loading(self) -> bool:
        # Backwards-compat alias used by older view code.
        return self.loading_payments or self.loading_metrics

    @property
    def search(self) -> Optional[str]:
        return self.filters.search


class FinancesController(BaseController):
    loading_changed = Signal(bool)
    state_changed = Signal(object)
    metrics_changed = Signal(object)
    error_occurred = Signal(str)
    action_completed = Signal(str, str)  # title, message

    def __init__(self, finances_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = finances_service
        self._state = FinancesState()
        self._page_limit = 100
        self._page_offset = 0

    # ------------------------------------------------------------------ state

    def state(self) -> FinancesState:
        return self._state

    def filters(self) -> PaymentFilters:
        return self._state.filters

    # ------------------------------------------------------------------ filters

    def apply_filters(self, filters: PaymentFilters, *, reset_page: bool = True) -> None:
        """Replace the active filter set and reload both payments and metrics."""
        self._state = replace(self._state, filters=filters)
        if reset_page:
            self._page_offset = 0
        self._refresh_all()

    def set_search(self, search: Optional[str]) -> None:
        self.apply_filters(self._state.filters.with_search(search))

    def set_preset(self, preset: FilterPreset) -> None:
        self.apply_filters(self._state.filters.with_preset(preset))

    def set_custom_range(self, start, end) -> None:
        self.apply_filters(self._state.filters.with_custom_range(start, end))

    def set_status(self, status: Optional[str]) -> None:
        self.apply_filters(self._state.filters.with_status(status))

    def set_method(self, method: Optional[str]) -> None:
        self.apply_filters(self._state.filters.with_method(method))

    # ------------------------------------------------------------------ loads

    def load_payments(
        self,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> None:
        """Load payments using the current filters.

        Accepts a few legacy kwargs (``search``, ``limit``, ``offset``) to keep
        existing call sites working without churn.
        """
        if not self._service:
            self.error_occurred.emit("Servicio no disponible")
            return

        if search is not None:
            # Legacy path: caller passed a fresh search string.
            self._state = replace(
                self._state, filters=self._state.filters.with_search(search)
            )

        if limit is not None:
            self._page_limit = limit
        if offset is not None:
            self._page_offset = offset

        self._state = replace(self._state, loading_payments=True)
        self.loading_changed.emit(True)
        self.state_changed.emit(self._state)

        self._execute_authenticated_operation(
            self._service,
            "get_payments",
            self._on_payments_loaded,
            self._on_error,
            limit=self._page_limit,
            offset=self._page_offset,
            **self._state.filters.to_graphql_kwargs(),
        )

    def load_metrics(self) -> None:
        """Load aggregated metrics for the current filters."""
        if not self._service:
            return

        self._state = replace(self._state, loading_metrics=True)
        self._execute_authenticated_operation(
            self._service,
            "get_payment_metrics",
            self._on_metrics_loaded,
            self._on_metrics_error,
            **{
                k: v
                for k, v in self._state.filters.to_graphql_kwargs().items()
                if k != "search"  # backend metrics query does not accept search
            },
        )

    def _refresh_all(self) -> None:
        self.load_payments()
        self.load_metrics()

    # ------------------------------------------------------------------ mutations

    def update_payment(self, payment_id: int, payload: dict) -> None:
        if not self._service:
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "update_payment",
            self._on_action_success,
            self._on_error,
            payment_id=payment_id,
            **payload,
        )

    def delete_payment(self, payment_id: int) -> None:
        if not self._service:
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "delete_payment",
            self._on_action_success,
            self._on_error,
            payment_id=payment_id,
        )

    # ------------------------------------------------------------------ callbacks

    @Slot(object)
    def _on_payments_loaded(self, result: Any) -> None:
        items: List[dict] = []
        total = 0
        if isinstance(result, dict):
            items = result.get("items") or []
            total = int(result.get("total") or 0)

        self._state = replace(
            self._state, payments=items, total=total, loading_payments=False
        )
        self.loading_changed.emit(self._state.loading)
        self.state_changed.emit(self._state)

    @Slot(object)
    def _on_metrics_loaded(self, result: Any) -> None:
        metrics = result if isinstance(result, dict) else None
        self._state = replace(self._state, metrics=metrics, loading_metrics=False)
        self.loading_changed.emit(self._state.loading)
        self.metrics_changed.emit(metrics)
        self.state_changed.emit(self._state)

    @Slot(str)
    def _on_metrics_error(self, error: str) -> None:
        self._state = replace(self._state, loading_metrics=False)
        self.loading_changed.emit(self._state.loading)
        # Surface the failure but don't drown the UI: log + emit, no popup.
        logger.warning("Metrics load failed: %s", error)
        self.error_occurred.emit(error)

    @Slot(object)
    def _on_action_success(self, result: Any) -> None:
        self.loading_changed.emit(False)
        success = False
        message = "Operación completada"

        if isinstance(result, dict):
            payload = result.get("updatePayment") or result.get("deletePayment") or {}
            success = bool(payload.get("success", False))
            message = payload.get("message", message)

        if success:
            self.action_completed.emit("Éxito", message)
            self._refresh_all()
        else:
            self.error_occurred.emit(message)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self._state = replace(self._state, loading_payments=False)
        self.loading_changed.emit(self._state.loading)
        self.state_changed.emit(self._state)
        self.error_occurred.emit(error)
