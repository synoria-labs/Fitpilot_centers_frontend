"""Controller orchestrating WhatsApp template management for the WhatsApp tab."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class WhatsAppController(BaseController):
    """Coordina las llamadas al servicio de plantillas y expone señales para la vista."""

    templates_loaded = Signal(object)        # List[dict]
    synced = Signal(object)                   # List[dict]
    template_saved = Signal(object, str)      # template dict, mensaje
    template_deleted = Signal(int)            # template_id
    test_sent = Signal(str)                   # mensaje informativo
    media_assets_loaded = Signal(str, object) # kind, List[dict]
    media_asset_uploaded = Signal(str, object) # kind, asset dict
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, whatsapp_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = whatsapp_service

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    def load_templates(self, search: Optional[str] = None) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "get_templates",
            self._on_templates_loaded,
            self._on_error,
            search=search,
        )

    def sync_templates(self) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "sync_templates",
            self._on_synced,
            self._on_error,
        )

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    def save_template(self, template_id: Optional[int], data: Dict[str, Any]) -> None:
        """Crea (template_id None) o actualiza una plantilla."""
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)
        if template_id is None:
            self._execute_authenticated_operation(
                self._service,
                "create_template",
                self._on_saved,
                self._on_error,
                name=data.get("name"),
                language=data.get("language"),
                category=data.get("category"),
                body_text=data.get("body_text"),
                body_examples=data.get("body_examples"),
                footer_text=data.get("footer_text"),
                header_format=data.get("header_format"),
                header_media_asset_id=data.get("header_media_asset_id"),
            )
        else:
            self._execute_authenticated_operation(
                self._service,
                "update_template",
                self._on_saved,
                self._on_error,
                template_id=template_id,
                body_text=data.get("body_text"),
                body_examples=data.get("body_examples"),
                footer_text=data.get("footer_text"),
                header_media_asset_id=data.get("header_media_asset_id"),
            )

    def delete_template(self, template_id: int) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)

        def _on_deleted(result: Dict[str, Any]) -> None:
            self.loading_changed.emit(False)
            if result and result.get("success"):
                self.template_deleted.emit(template_id)
            else:
                self.error_occurred.emit((result or {}).get("error") or "No se pudo eliminar")

        self._execute_authenticated_operation(
            self._service,
            "delete_template",
            _on_deleted,
            self._on_error,
            template_id=template_id,
        )

    def send_test(
        self,
        phone: str,
        template_id: int,
        body_params: List[str],
        header_media_url: Optional[str] = None,
        header_media_asset_id: Optional[int] = None,
    ) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "send_template_test",
            self._on_test_sent,
            self._on_error,
            phone=phone,
            template_id=template_id,
            body_params=body_params,
            header_media_url=header_media_url,
            header_media_asset_id=header_media_asset_id,
        )

    def load_media_assets(self, kind: Optional[str]) -> None:
        if not self._service or not kind:
            return
        self._execute_authenticated_operation(
            self._service,
            "get_media_assets",
            lambda result, media_kind=kind: self.media_assets_loaded.emit(media_kind, result or []),
            self._on_error,
            kind=kind,
        )

    def upload_media_asset(self, file_path: str, kind: str, display_name: Optional[str] = None) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de WhatsApp no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service,
            "upload_media_asset",
            lambda result, media_kind=kind: self._on_media_uploaded(media_kind, result),
            self._on_error,
            file_path=file_path,
            kind=kind,
            display_name=display_name,
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_templates_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.templates_loaded.emit(result or [])

    def _on_synced(self, result: Any) -> None:
        self.loading_changed.emit(False)
        self.synced.emit(result or [])

    def _on_saved(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.template_saved.emit(result.get("template"), "Plantilla guardada")
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo guardar")

    def _on_test_sent(self, result: Dict[str, Any]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.test_sent.emit("Plantilla enviada correctamente")
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo enviar")

    def _on_media_uploaded(self, kind: str, result: Optional[Dict[str, Any]]) -> None:
        self.loading_changed.emit(False)
        if result and result.get("id"):
            self.media_asset_uploaded.emit(kind, result)
        else:
            self.error_occurred.emit(
                (result or {}).get("error") or "No se pudo subir el archivo multimedia"
            )

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("WhatsAppController error: %s", message)
        self.error_occurred.emit(message)
