"""Controller for the owner/admin WhatsApp agent configuration tab."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class OwnerAgentConfigController(BaseController):
    bundle_loaded = Signal(object)
    config_saved = Signal(object)
    phone_saved = Signal(object)
    phone_disabled = Signal(object)
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    def load_bundle(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio del agente admin no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "get_config_bundle",
            self._on_bundle_loaded,
            self._on_error,
        )

    def save_config(self, data: Dict[str, Any]) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio del agente admin no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "save_config",
            self._on_config_saved,
            self._on_error,
            enabled=bool(data.get("enabled", False)),
            require_confirmation=bool(data.get("require_confirmation", True)),
            model=data.get("model"),
            system_prompt=data.get("system_prompt"),
            history_limit=int(data.get("history_limit") or 30),
            max_tokens=int(data.get("max_tokens") or 1024),
        )

    def add_phone(self, label: str, phone_number: str, enabled: bool = True) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "add_phone",
            self._on_phone_saved,
            self._on_error,
            label=label,
            phone_number=phone_number,
            enabled=enabled,
        )

    def update_phone(
        self,
        phone_id: int,
        *,
        label: Optional[str] = None,
        phone_number: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "update_phone",
            self._on_phone_saved,
            self._on_error,
            phone_id=phone_id,
            label=label,
            phone_number=phone_number,
            enabled=enabled,
        )

    def disable_phone(self, phone_id: int) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "disable_phone",
            self._on_phone_disabled,
            self._on_error,
            phone_id=phone_id,
        )

    def _on_bundle_loaded(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        self.bundle_loaded.emit(result or {"config": None, "phones": []})

    def _on_config_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.config_saved.emit(result.get("config"))
            self.load_bundle()
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar")

    def _on_phone_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.phone_saved.emit(result.get("phone"))
            self.load_bundle()
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar el telefono")

    def _on_phone_disabled(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.phone_disabled.emit(result.get("phone"))
            self.load_bundle()
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo desactivar")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("OwnerAgentConfigController error: %s", message)
        self.error_occurred.emit(message)
