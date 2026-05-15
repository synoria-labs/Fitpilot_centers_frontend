"""Controller for the Dashboard tab.

State:
  - period: the currently selected FilterPreset
  - start_date / end_date: resolved window in local TZ
  - metrics: dict from get_dashboard_metrics (or None while loading)
  - loading: in-flight request indicator

The controller accepts the same FilterPreset enum used by the Finanzas tab
(``app.models.payment_filters``) so the period picker semantics stay
consistent across the app.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.payment_filters import FilterPreset, compute_preset_range
from .base_controller import BaseController

logger = get_logger(__name__)


_DEFAULT_PRESET = FilterPreset.THIS_MONTH


@dataclass
class DashboardState:
    period: FilterPreset = _DEFAULT_PRESET
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    loading: bool = False


class DashboardController(BaseController):
    state_changed = Signal(object)
    metrics_changed = Signal(object)
    loading_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(
        self, dashboard_service: Any, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._service = dashboard_service
        start, end = compute_preset_range(_DEFAULT_PRESET)
        self._state = DashboardState(
            period=_DEFAULT_PRESET, start_date=start, end_date=end
        )

    # ------------------------------------------------------------------ state

    def state(self) -> DashboardState:
        return self._state

    # ------------------------------------------------------------------ filters

    def set_period(self, preset: FilterPreset) -> None:
        """Switch the active period preset and reload metrics."""
        start, end = compute_preset_range(preset)
        self._state = replace(
            self._state, period=preset, start_date=start, end_date=end
        )
        self.state_changed.emit(self._state)
        self.load_metrics()

    # ------------------------------------------------------------------ load

    def load_metrics(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio no disponible")
            return

        self._state = replace(self._state, loading=True)
        self.loading_changed.emit(True)
        self.state_changed.emit(self._state)

        kwargs: Dict[str, Any] = {}
        if self._state.start_date is not None:
            kwargs["start_date"] = self._state.start_date.isoformat()
        if self._state.end_date is not None:
            kwargs["end_date"] = self._state.end_date.isoformat()

        self._execute_authenticated_operation(
            self._service,
            "get_dashboard_metrics",
            self._on_metrics_loaded,
            self._on_error,
            **kwargs,
        )

    # ------------------------------------------------------------------ slots

    @Slot(object)
    def _on_metrics_loaded(self, result: Any) -> None:
        metrics = result if isinstance(result, dict) else None
        self._state = replace(self._state, metrics=metrics, loading=False)
        self.loading_changed.emit(False)
        self.metrics_changed.emit(metrics)
        self.state_changed.emit(self._state)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self._state = replace(self._state, loading=False)
        self.loading_changed.emit(False)
        self.state_changed.emit(self._state)
        logger.warning("Dashboard metrics load failed: %s", error)
        self.error_occurred.emit(error)
