"""Caja (cash register) tab: open/close the shared register + corte de caja."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...core import container, get_logger
from ...controllers.cash_register_controller import CashRegisterController
from ...utils.dialog_helpers import show_error, show_info
from ...utils.qt_helpers import PAYMENT_METHOD_OPTIONS
from ..dialogs.cash_movement_dialog import CashMovementDialog
from ..dialogs.close_cash_session_dialog import CloseCashSessionDialog
from ..dialogs.open_cash_session_dialog import OpenCashSessionDialog

logger = get_logger(__name__)

_METHOD_LABELS = {value: label for label, value in PAYMENT_METHOD_OPTIONS}


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


class CashRegisterTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._service = container.get("cash_register_service")
        self._printing = container.get("printing_service")
        self.controller = CashRegisterController(self._service, self)
        self._session: Optional[Dict[str, Any]] = None
        self._report: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._connect()
        self.controller.load_open_session()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Caja")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        self.status_label = QLabel("Cargando…")
        self.status_label.setStyleSheet("font-size: 15px;")
        root.addWidget(self.status_label)

        card = QFrame()
        card.setObjectName("cashCard")
        card.setStyleSheet("#cashCard { background: rgba(255,255,255,0.04); border-radius: 10px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        self.detail_label = QLabel("")
        self.detail_label.setTextFormat(Qt.TextFormat.RichText)
        self.detail_label.setWordWrap(True)
        card_layout.addWidget(self.detail_label)
        root.addWidget(card)

        actions = QHBoxLayout()
        self.open_btn = QPushButton("Abrir caja")
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.movement_btn = QPushButton("Movimiento de efectivo")
        self.movement_btn.clicked.connect(self._on_movement_clicked)
        self.print_btn = QPushButton("Imprimir corte")
        self.print_btn.clicked.connect(self._on_print_clicked)
        self.close_btn = QPushButton("Corte de caja")
        self.close_btn.clicked.connect(self._on_close_clicked)
        self.refresh_btn = QPushButton("Actualizar")
        self.refresh_btn.clicked.connect(lambda: self.controller.load_open_session())
        for b in (self.open_btn, self.movement_btn, self.print_btn, self.close_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.refresh_btn)
        root.addLayout(actions)
        root.addStretch()

    def _connect(self) -> None:
        self.controller.session_changed.connect(self._on_session_changed)
        self.controller.report_changed.connect(self._on_report_changed)
        self.controller.action_completed.connect(self._on_action_completed)
        self.controller.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_session_changed(self, session: Optional[Dict[str, Any]]) -> None:
        self._session = session
        is_open = bool(session)
        self.open_btn.setVisible(not is_open)
        self.movement_btn.setEnabled(is_open)
        self.print_btn.setEnabled(is_open)
        self.close_btn.setEnabled(is_open)
        if is_open:
            self.status_label.setText("🟢 Caja abierta")
            self._report = None
            self._render_detail()
        else:
            self.status_label.setText("⚪ No hay caja abierta")
            self.detail_label.setText("Abre la caja para empezar a cobrar en efectivo.")

    @Slot(object)
    def _on_report_changed(self, report: Optional[Dict[str, Any]]) -> None:
        self._report = report
        self._render_detail()

    def _render_detail(self) -> None:
        if not self._session:
            return
        s = self._session
        r = self._report or {}
        lines = [
            f"<b>Fondo inicial:</b> {_money(s.get('openingFloat'))}",
            f"<b>Ventas:</b> {r.get('salesCount', 0)} ({_money(r.get('salesTotal'))})",
            f"<b>Efectivo esperado:</b> {_money(r.get('computedExpectedCash'))}",
            f"<b>Ingresos:</b> {_money(r.get('cashIn'))} &nbsp; <b>Retiros:</b> {_money(r.get('cashOut'))}",
        ]
        by_method = r.get("byMethod") or []
        if by_method:
            parts = "; ".join(
                f"{_METHOD_LABELS.get((b.get('method') or '').lower(), (b.get('method') or '').capitalize())}: {_money(b.get('total'))}"
                for b in by_method
            )
            lines.append(f"<b>Por método:</b> {parts}")
        self.detail_label.setText("<br>".join(lines))

    @Slot(str, str)
    def _on_action_completed(self, title: str, message: str) -> None:
        show_info(self, message, title=title)
        pending = getattr(self, "_pending_corte", None)
        if title == "Corte de caja" and pending:
            self._pending_corte = None
            try:
                self._printing.imprimir_corte_caja(pending)
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo imprimir el corte: %s", exc)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        show_error(self, error, title="Caja")

    # ------------------------------------------------------------------ actions
    def _on_open_clicked(self) -> None:
        dialog = OpenCashSessionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.controller.open_session(data["opening_float"], data["notes"])

    def _on_movement_clicked(self) -> None:
        if not self._session:
            return
        dialog = CashMovementDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            if data["amount"] <= 0:
                show_error(self, "El monto debe ser mayor a cero.", title="Movimiento")
                return
            # The controller refreshes the live report after the movement commits.
            self.controller.record_movement(
                int(self._session["id"]), data["direction"], data["amount"], data["reason"]
            )

    def _on_close_clicked(self) -> None:
        if not self._session:
            return
        dialog = CloseCashSessionDialog(self._report, self)
        if dialog.exec():
            data = dialog.get_data()
            self._pending_corte = dict(self._report or {})
            self._pending_corte["countedCash"] = data["counted_cash"]
            self.controller.close_session(
                int(self._session["id"]), data["counted_cash"], data["notes"]
            )

    def _on_print_clicked(self) -> None:
        report = self._report
        if not report:
            show_error(self, "No hay datos de corte para imprimir.", title="Caja")
            return
        ok = self._printing.imprimir_corte_caja(report)
        if not ok:
            show_error(self, "No se pudo imprimir el corte (revisa la impresora).", title="Impresión")
