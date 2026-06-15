"""Controller para la pestaña de configuración del chatbot de WhatsApp."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class ChatbotConfigController(BaseController):
    """Coordina el servicio de configuración del chatbot y expone señales para la vista."""

    config_loaded = Signal(object)   # dict | None
    config_saved = Signal(object)    # config dict
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    def load_config(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio del chatbot no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "get_config", self._on_loaded, self._on_error,
        )

    def save_config(self, data: Dict[str, Any]) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio del chatbot no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "save_config",
            self._on_saved,
            self._on_error,
            enabled=bool(data.get("enabled", False)),
            require_confirmation=bool(data.get("require_confirmation", True)),
            require_mp_payment=bool(data.get("require_mp_payment", False)),
            model=data.get("model"),
            system_prompt=data.get("system_prompt"),
            business_name=data.get("business_name"),
            address=data.get("address"),
            operating_hours=data.get("operating_hours"),
            phone=data.get("phone"),
            policies=data.get("policies"),
            tone=data.get("tone"),
            extra_info=data.get("extra_info"),
        )

    # ------------------------------------------------------------------
    def _on_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.config_loaded.emit(result)

    def _on_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.config_saved.emit(result.get("config"))
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("ChatbotConfigController error: %s", message)
        self.error_occurred.emit(message)
