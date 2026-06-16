"""Controller para la pestaña de Campañas de marketing por WhatsApp.

Coordina ``CampaignsService`` y expone señales para la vista, reutilizando el patrón
``_execute_authenticated_operation`` de ``BaseController`` (operaciones async no bloqueantes
vía el AsyncioExecutor).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class CampaignsController(BaseController):
    """Coordina el servicio de campañas y expone señales para la vista."""

    campaigns_loaded = Signal(object)     # List[dict]
    catalog_loaded = Signal(object)       # dict {objectives, predicates, variables}
    templates_loaded = Signal(object)     # List[dict]
    campaign_loaded = Signal(object)      # dict | None
    audience_previewed = Signal(object)   # {count, sample}
    campaign_saved = Signal(object)       # {success, error, campaign}
    action_result = Signal(object)        # generic run/status dict
    metrics_loaded = Signal(object)       # dict
    recipients_loaded = Signal(object)    # List[dict]
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    # ------------------------------------------------------------------ reads
    def load_campaigns(self, status: Optional[str] = None) -> None:
        if not self._service:
            self.error_occurred.emit("Servicio de campañas no disponible")
            return
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "list_campaigns",
            self._on_campaigns, self._on_error, status=status,
        )

    def load_catalog(self) -> None:
        self._execute_authenticated_operation(
            self._service, "get_catalog",
            self.catalog_loaded.emit, self._on_error,
        )

    def load_templates(self) -> None:
        self._execute_authenticated_operation(
            self._service, "get_approved_templates",
            self.templates_loaded.emit, self._on_error,
        )

    def load_campaign(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "get_campaign",
            self.campaign_loaded.emit, self._on_error, campaign_id=campaign_id,
        )

    def preview_audience(self, audience_spec: Dict[str, Any]) -> None:
        self._execute_authenticated_operation(
            self._service, "preview_audience",
            self.audience_previewed.emit, self._on_error, audience_spec=audience_spec,
        )

    def load_metrics(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "get_metrics",
            self.metrics_loaded.emit, self._on_error, campaign_id=campaign_id,
        )

    def load_recipients(self, campaign_id: int, status: Optional[str] = None) -> None:
        self._execute_authenticated_operation(
            self._service, "list_recipients",
            self.recipients_loaded.emit, self._on_error,
            campaign_id=campaign_id, status=status,
        )

    # -------------------------------------------------------------- mutations
    def create_campaign(self, payload: Dict[str, Any]) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "create_campaign",
            self._on_saved, self._on_error, payload=payload,
        )

    def update_campaign(self, campaign_id: int, payload: Dict[str, Any]) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "update_campaign",
            self._on_saved, self._on_error, campaign_id=campaign_id, payload=payload,
        )

    def delete_campaign(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "delete_campaign",
            self._on_action, self._on_error, campaign_id=campaign_id,
        )

    def build_audience(self, campaign_id: int) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "build_audience",
            self._on_action, self._on_error, campaign_id=campaign_id,
        )

    def schedule_campaign(self, campaign_id: int, scheduled_at: str, send_local_time: bool) -> None:
        self._execute_authenticated_operation(
            self._service, "schedule_campaign",
            self._on_saved, self._on_error,
            campaign_id=campaign_id, scheduled_at=scheduled_at, send_local_time=send_local_time,
        )

    def trigger_campaign(self, campaign_id: int, dry_run: bool = False) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._service, "trigger_campaign",
            self._on_action, self._on_error, campaign_id=campaign_id, dry_run=dry_run,
        )

    def pause_campaign(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "pause_campaign",
            self._on_saved, self._on_error, campaign_id=campaign_id,
        )

    def resume_campaign(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "resume_campaign",
            self._on_action, self._on_error, campaign_id=campaign_id,
        )

    def cancel_campaign(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "cancel_campaign",
            self._on_saved, self._on_error, campaign_id=campaign_id,
        )

    def retry_failures(self, campaign_id: int) -> None:
        self._execute_authenticated_operation(
            self._service, "retry_failures",
            self._on_action, self._on_error, campaign_id=campaign_id,
        )

    # ------------------------------------------------------------------ slots
    def _on_campaigns(self, result: Optional[List[Dict[str, Any]]]) -> None:
        self.loading_changed.emit(False)
        self.campaigns_loaded.emit(result or [])

    def _on_saved(self, result: Any) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.campaign_saved.emit(result)
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo completar la acción")

    def _on_action(self, result: Any) -> None:
        self.loading_changed.emit(False)
        if result and result.get("success"):
            self.action_result.emit(result)
        else:
            self.error_occurred.emit((result or {}).get("error") or "No se pudo completar la acción")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("CampaignsController error: %s", message)
        self.error_occurred.emit(message)
