"""Controller para la pestaña «Eventos especiales»."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)

_UNAVAILABLE = "Servicio de eventos especiales no disponible"


class SpecialEventsController(BaseController):
    """Coordina el servicio de eventos especiales y expone señales para la vista.

    Toda mutation devuelve el detalle recalculado del evento (cupo, bicis, bloqueos para
    publicar, desplazados...), así que terminan en ``detail_loaded``: la vista se repinta con
    lo que el servidor decidió, no con lo que el formulario cree haber enviado.
    """

    events_loaded = Signal(object)  # list[dict]
    detail_loaded = Signal(object)  # dict | None
    options_loaded = Signal(object)  # dict | None
    takeover_preview_loaded = Signal(object)  # dict | None
    restore_preview_loaded = Signal(object)  # dict | None
    campaigns_loaded = Signal(object)  # list[dict]
    follow_up_saved = Signal(object)  # dict (displacement)
    operation_succeeded = Signal(str)  # mensaje para mostrar
    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = service

    # ------------------------------------------------------------------ reads
    def load_events(self, include_past: bool = False) -> None:
        self._run("list_events", self._on_events, include_past=include_past)

    def load_event(self, event_id: int) -> None:
        self._run("get_event", self._on_detail, event_id=event_id)

    def load_options(self) -> None:
        self._run("get_form_options", self.options_loaded.emit)

    def load_takeover_preview(self, event_id: int) -> None:
        self._run("takeover_preview", self.takeover_preview_loaded.emit, event_id=event_id)

    def load_restore_preview(self, event_id: int) -> None:
        self._run("restore_preview", self.restore_preview_loaded.emit, event_id=event_id)

    def load_campaigns(self) -> None:
        self._run("list_campaigns", self.campaigns_loaded.emit)

    # ------------------------------------------------------------------ writes
    def create_event(self, data: Dict[str, Any]) -> None:
        self._run("create_event", self._on_result, data=data)

    def update_event(self, event_id: int, data: Dict[str, Any]) -> None:
        self._run("update_event", self._on_result, event_id=event_id, data=data)

    def publish_event(self, event_id: int) -> None:
        self._run("publish_event", self._on_result, event_id=event_id)

    def unpublish_event(self, event_id: int) -> None:
        self._run("unpublish_event", self._on_result, event_id=event_id)

    def cancel_event(self, event_id: int, reason: str) -> None:
        self._run("cancel_event", self._on_result, event_id=event_id, reason=reason)

    def apply_takeover(self, event_id: int, session_ids: List[int]) -> None:
        self._run("apply_takeover", self._on_result, event_id=event_id, session_ids=session_ids)

    def restore_schedule(self, event_id: int) -> None:
        self._run("restore_schedule", self._on_result, event_id=event_id)

    def add_participant(self, data: Dict[str, Any]) -> None:
        self._run("add_participant", self._on_result, data=data)

    def cancel_order(self, order_id: int, reason: str) -> None:
        self._run("cancel_order", self._on_result, order_id=order_id, reason=reason)

    def refund_order(self, order_id: int, reason: str) -> None:
        self._run("refund_order", self._on_result, order_id=order_id, reason=reason)

    def link_campaign(self, campaign_id: int, event_id: Optional[int]) -> None:
        self._run("link_campaign", self._on_result, campaign_id=campaign_id, event_id=event_id)

    def update_follow_up(self, data: Dict[str, Any]) -> None:
        self._run("update_follow_up", self._on_follow_up, data=data)

    # ------------------------------------------------------------------ plumbing
    def _run(self, method: str, on_success, **kwargs) -> None:
        if not self._service:
            self.error_occurred.emit(_UNAVAILABLE)
            return
        self.loading_changed.emit(True)

        def done(result: Any) -> None:
            self.loading_changed.emit(False)
            on_success(result)

        self._execute_authenticated_operation(self._service, method, done, self._on_error, **kwargs)

    def _on_events(self, result: Any) -> None:
        self.events_loaded.emit(result or [])

    def _on_detail(self, result: Any) -> None:
        self.detail_loaded.emit(result)

    def _on_result(self, result: Optional[Dict[str, Any]]) -> None:
        result = result or {}
        if result.get("detail") is not None:
            self.detail_loaded.emit(result["detail"])
        if result.get("success"):
            if result.get("message"):
                self.operation_succeeded.emit(result["message"])
        else:
            self.error_occurred.emit(result.get("error") or "No se pudo completar la operación")

    def _on_follow_up(self, result: Optional[Dict[str, Any]]) -> None:
        result = result or {}
        if result.get("success"):
            self.follow_up_saved.emit(result.get("displacement"))
        else:
            self.error_occurred.emit(result.get("error") or "No se pudo guardar el seguimiento")

    def _on_error(self, message: str) -> None:
        self.loading_changed.emit(False)
        logger.error("SpecialEventsController error: %s", message)
        self.error_occurred.emit(message)
