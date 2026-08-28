"""Controller para la pestaña de estimaciones físicas (kcal / kg de grasa)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class FitnessEstimationController(BaseController):
    """Coordina el servicio de estimaciones y expone señales para la vista.

    Guardar y cambiar un MET devuelven el mismo payload completo (política + actividades +
    horario derivado + ejemplo recalculado), así que ambos terminan en ``settings_loaded``:
    la vista se repinta con lo que el backend acaba de calcular en vez de con lo que el
    formulario cree haber enviado.
    """

    settings_loaded = Signal(object)  # dict | None
    settings_saved = Signal(object)   # dict
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    def load_settings(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de estimaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "get_settings", self._on_loaded, self._on_error,
        )

    def save_config(self, data: Dict[str, Any]) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de estimaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "save_config",
            self._on_saved,
            self._on_error,
            reference_weight_kg=data.get("reference_weight_kg"),
            horizon_weeks=data.get("horizon_weeks"),
            default_sessions_per_week=data.get("default_sessions_per_week"),
            min_bookings_for_history=data.get("min_bookings_for_history"),
            cadence_lookback_days=data.get("cadence_lookback_days"),
            default_met=data.get("default_met"),
            default_duration_min=data.get("default_duration_min"),
            default_open_days_per_week=data.get("default_open_days_per_week"),
            net_of_resting=data.get("net_of_resting"),
            kcal_per_kg_fat=data.get("kcal_per_kg_fat"),
            metabolic_adaptation=data.get("metabolic_adaptation"),
            kg_half_life_days=data.get("kg_half_life_days"),
            kg_per_100_kcal_per_day=data.get("kg_per_100_kcal_per_day"),
            realization_factor=data.get("realization_factor"),
        )

    def set_class_type_met(self, class_type_id: int, met_value: Optional[float]) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de estimaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "set_class_type_met",
            self._on_saved,
            self._on_error,
            class_type_id=class_type_id,
            met_value=met_value,
        )

    # ------------------------------------------------------------------
    def _on_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.settings_loaded.emit(result)

    def _on_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.settings_saved.emit(result.get("settings"))
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("FitnessEstimationController error: %s", message)
        self.error_occurred.emit(message)
