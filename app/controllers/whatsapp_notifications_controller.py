"""Controller para la pestaña de configuración de notificaciones automáticas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class WhatsAppNotificationsController(BaseController):
    """Coordina el servicio de notificaciones y expone señales para la vista."""

    settings_loaded = Signal(object)    # List[dict]
    catalog_loaded = Signal(object)     # List[dict]
    templates_loaded = Signal(object)   # List[dict] (aprobadas)
    setting_saved = Signal(object)      # setting dict
    sweep_done = Signal(object)         # {sent, skipped, failed}
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    def load_all(self) -> None:
        """Carga catálogo, plantillas aprobadas y configuración actual."""
        self.load_catalog()
        self.load_templates()
        self.load_settings()

    def load_settings(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de notificaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "get_settings", self._on_settings_loaded, self._on_error,
        )

    def load_catalog(self) -> None:
        if not self._service:
            return
        self._execute_authenticated_operation(
            self._service, "get_catalog", self._on_catalog_loaded, self._on_error,
        )

    def load_templates(self) -> None:
        if not self._service:
            return
        self._execute_authenticated_operation(
            self._service, "get_approved_templates", self._on_templates_loaded, self._on_error,
        )

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    def save_setting(self, data: Dict[str, Any]) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de notificaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "save_setting",
            self._on_saved,
            self._on_error,
            event_type=data.get("event_type"),
            enabled=data.get("enabled", False),
            template_id=data.get("template_id"),
            param_mapping=data.get("param_mapping") or [],
            offsets_days=data.get("offsets_days") or [],
        )

    def run_sweep(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de notificaciones no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "run_sweep", self._on_sweep_done, self._on_error,
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_settings_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.settings_loaded.emit(result or [])

    def _on_catalog_loaded(self, result: Any) -> None:
        self.catalog_loaded.emit(result or [])

    def _on_templates_loaded(self, result: Any) -> None:
        self.templates_loaded.emit(result or [])

    def _on_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.setting_saved.emit(result.get("setting"))
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar")

    def _on_sweep_done(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.sweep_done.emit(result)
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo ejecutar el barrido")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("WhatsAppNotificationsController error: %s", message)
        self.error_occurred.emit(message)
