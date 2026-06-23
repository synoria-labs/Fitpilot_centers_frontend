"""Controller for the Caja (cash register) tab + corte de caja."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from .base_controller import BaseController

logger = get_logger(__name__)


class CashRegisterController(BaseController):
    session_changed = Signal(object)     # open session dict or None
    report_changed = Signal(object)      # report dict or None
    action_completed = Signal(str, str)  # title, message
    loading_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, cash_register_service: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._svc = cash_register_service
        self._movement_session_id: Optional[int] = None

    # ------------------------------------------------------------------ loads
    def load_open_session(self) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._svc, "get_open_cash_session", self._on_session_loaded, self._on_error,
        )

    def load_report(self, cash_session_id: int) -> None:
        self._execute_authenticated_operation(
            self._svc, "get_cash_session_report", self._on_report_loaded, self._on_error,
            cash_session_id=cash_session_id,
        )

    # ------------------------------------------------------------------ writes
    def open_session(self, opening_float: float, notes: Optional[str] = None) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._svc, "open_cash_session", self._on_open_done, self._on_error,
            opening_float=opening_float, notes=notes,
        )

    def close_session(self, cash_session_id: int, counted_cash: float, notes: Optional[str] = None) -> None:
        self.loading_changed.emit(True)
        self._execute_authenticated_operation(
            self._svc, "close_cash_session", self._on_close_done, self._on_error,
            cash_session_id=cash_session_id, counted_cash=counted_cash, notes=notes,
        )

    def record_movement(self, cash_session_id: int, direction: str, amount: float, reason: Optional[str] = None) -> None:
        # Remember the session so we can refresh its report AFTER the write commits
        # (reloading eagerly races the insert and shows stale numbers).
        self._movement_session_id = cash_session_id
        self._execute_authenticated_operation(
            self._svc, "record_cash_movement", self._on_movement_done, self._on_error,
            cash_session_id=cash_session_id, direction=direction, amount=amount, reason=reason,
        )

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_session_loaded(self, result: Any) -> None:
        self.loading_changed.emit(False)
        session = result if isinstance(result, dict) else None
        self.session_changed.emit(session)
        if session and session.get("id"):
            self.load_report(int(session["id"]))

    @Slot(object)
    def _on_report_loaded(self, result: Any) -> None:
        self.report_changed.emit(result if isinstance(result, dict) else None)

    @Slot(object)
    def _on_open_done(self, result: Any) -> None:
        self.loading_changed.emit(False)
        if isinstance(result, dict) and result.get("success"):
            self.action_completed.emit("Caja", result.get("message") or "Caja abierta")
            self.session_changed.emit(result.get("session"))
            session = result.get("session") or {}
            if session.get("id"):
                self.load_report(int(session["id"]))
        else:
            self.error_occurred.emit(_msg(result, "No se pudo abrir la caja"))

    @Slot(object)
    def _on_close_done(self, result: Any) -> None:
        self.loading_changed.emit(False)
        if isinstance(result, dict) and result.get("success"):
            self.action_completed.emit("Corte de caja", result.get("message") or "Corte realizado")
            # Session is now closed -> no open session.
            self.session_changed.emit(None)
        else:
            self.error_occurred.emit(_msg(result, "No se pudo cerrar la caja"))

    @Slot(object)
    def _on_movement_done(self, result: Any) -> None:
        if isinstance(result, dict) and result.get("success"):
            self.action_completed.emit("Movimiento", result.get("message") or "Movimiento registrado")
            # Refresh the live corte only now that the movement is committed.
            if self._movement_session_id is not None:
                self.load_report(self._movement_session_id)
        else:
            self.error_occurred.emit(_msg(result, "No se pudo registrar el movimiento"))

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self.loading_changed.emit(False)
        self.error_occurred.emit(error)


def _msg(result: Any, fallback: str) -> str:
    if isinstance(result, dict) and result.get("message"):
        return result["message"]
    return fallback
