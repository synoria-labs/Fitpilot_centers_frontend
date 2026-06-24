"""POS renewal line dialog: pick plan + class/horario + seat (pre-filled with the
member's current data, editable) and RETURN a renewal sale line — it does NOT
submit/charge (the POS cart + tenders handle payment).

Subclasses BaseSubscriptionDialog to reuse all the class/seat/date machinery, and
is driven by a RenewSubscriptionController for plan/template/seat loading and the
member's current booking. Unlike RenewSubscriptionDialog it never calls
renew_subscription; on accept it just validates the seat and returns get_line().
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLabel, QVBoxLayout, QWidget,
)

from ...core.logging import get_logger
from ...models.base import MembershipPlan, Seat, TimeslotGroup
from ...utils.dialog_helpers import show_error, show_warning
from ...utils.qt_helpers import configure_amount_input
from .base_subscription_dialog import AMOUNT_MAXIMUM, BaseSubscriptionDialog
from .renew_subscription_dialog import NO_CLASS_OPTION, QDateEditWithToday

logger = get_logger(__name__)


class PosRenewalLineDialog(BaseSubscriptionDialog):
    def __init__(
        self,
        controller: Any,
        member_id: int,
        member_name: Optional[str] = None,
        member_data: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        self.controller = controller
        self.member_id = member_id
        self.member_name = member_name
        self.member_data = member_data

        # Current values used for pre-selection.
        self._active_membership_plan_name: Optional[str] = None
        self._active_template_id: Optional[int] = None
        self._active_seat_id: Optional[int] = None

        super().__init__(parent)

        self.setWindowTitle("Renovar membresía")
        self.setModal(True)
        self.setMinimumWidth(560)

        self._build_ui()
        self._connect_signals()
        self._set_loading(True)
        QTimer.singleShot(50, self._initial_load)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info_group = QGroupBox("Información del socio")
        info_form = QFormLayout(info_group)
        self.name_label = QLabel(self.member_name or "—")
        self.current_plan_label = QLabel("—")
        self.end_date_label = QLabel("—")
        info_form.addRow("Nombre", self.name_label)
        info_form.addRow("Membresía actual", self.current_plan_label)
        info_form.addRow("Vence", self.end_date_label)

        form_group = QGroupBox("Datos de renovación")
        form = QFormLayout(form_group)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.plan_combo = QComboBox()
        form.addRow("Nuevo plan", self.plan_combo)

        self.start_date = QDateEditWithToday()
        form.addRow("Fecha de inicio", self.start_date)

        self.class_combo = QComboBox()
        form.addRow("Clase (horario fijo)", self.class_combo)

        self.seat_label = QLabel("Lugar")
        self.seat_combo = QComboBox()
        self.seat_label.setVisible(False)
        self.seat_combo.setVisible(False)
        self.seat_combo.setEnabled(False)
        form.addRow(self.seat_label, self.seat_combo)

        self.amount_input = QDoubleSpinBox()
        configure_amount_input(self.amount_input, AMOUNT_MAXIMUM)
        form.addRow("Monto", self.amount_input)

        layout.addWidget(info_group)
        layout.addWidget(form_group)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.confirm_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("Agregar")
        self.confirm_button.setEnabled(False)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        layout.addWidget(self.button_box)

    def _connect_signals(self) -> None:
        self.button_box.accepted.connect(self._on_accept_collect)
        self.button_box.rejected.connect(self.reject)

        # Base-class handlers for UI events.
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        self.start_date.dateChanged.connect(self._on_date_changed)

        # Controller signals.
        self.controller.plans_loaded.connect(self._on_plans_loaded_renewal)
        self.controller.plans_error.connect(self._on_plans_error)
        if hasattr(self.controller.subscription_service, "timeslot_groups_loaded"):
            self.controller.subscription_service.timeslot_groups_loaded.connect(
                self._on_timeslot_groups_loaded_renewal
            )
        self.controller.class_templates_error.connect(self._on_class_templates_error)
        self.controller.member_data_loaded.connect(self._on_member_data_loaded)
        self.controller.member_data_error.connect(self._on_member_data_error)
        # Base seats handler honors _pending_seat_selection (selects the current seat).
        self.controller.seats_loaded.connect(self._on_seats_loaded)
        self.controller.seats_error.connect(self._on_seats_error)

    def _initial_load(self) -> None:
        self.controller.load_membership_plans()
        if self.controller.standing_bookings_service:
            self.controller.load_class_templates()
        self.controller.load_defaults(self.member_id, self.member_name, self.member_data)

    def _set_loading(self, loading: bool) -> None:
        self.confirm_button.setEnabled(not loading)

    def _maybe_ready(self) -> None:
        if self.plan_combo.count() > 0:
            self._set_loading(False)

    # ------------------------------------------------------------------ loads
    def _on_plans_loaded_renewal(self, plans: List[MembershipPlan]) -> None:
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()
        if not plans:
            show_warning(self, "No se encontraron planes.", title="Planes")
            self.plan_combo.blockSignals(False)
            return
        for p in plans:
            self.plan_combo.addItem(f"{p.name} - ${p.price:,.2f}", p)
        self.plan_combo.setCurrentIndex(0)
        self.plan_combo.blockSignals(False)
        p0 = self.plan_combo.currentData()
        if isinstance(p0, MembershipPlan):
            self.amount_input.setValue(float(p0.price))
        self._preselect_plan()  # override to the current plan if already known
        self._maybe_ready()

    def _on_plans_error(self, error: str) -> None:
        show_error(self, error, title="Error")

    def _on_timeslot_groups_loaded_renewal(self, groups: List[TimeslotGroup]) -> None:
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        if not groups:
            show_warning(self, "No se encontraron clases.", title="Clases")
            self.class_combo.blockSignals(False)
            return
        self.class_combo.addItem(NO_CLASS_OPTION, None)
        for group in groups:
            self.class_combo.addItem(group.display_label(), group)
        self.class_combo.blockSignals(False)
        self._preselect_class_and_seat()  # pre-select current class+seat if known
        self._maybe_ready()

    def _on_class_templates_error(self, error: str) -> None:
        show_error(self, error, title="Error")

    def _on_member_data_loaded(self, payload: dict) -> None:
        member = payload.get("member") or {}
        active_mem = payload.get("active_membership") or {}
        active_book = payload.get("active_booking") or {}

        self.name_label.setText(member.get("full_name") or self.member_name or f"Socio #{self.member_id}")
        self._active_membership_plan_name = active_mem.get("planName") or active_mem.get("plan_name")
        if self._active_membership_plan_name:
            self.current_plan_label.setText(self._active_membership_plan_name)

        end_dt = self._coerce_datetime(active_mem.get("endDate") or active_mem.get("end_date"))
        if end_dt:
            self.end_date_label.setText(end_dt.date().isoformat())
            self.start_date.setDate(QDate(end_dt.year, end_dt.month, end_dt.day).addDays(1))

        # Real booking only arrives with the background load; don't clobber with empties.
        if active_book:
            self._active_template_id = active_book.get("templateId") or active_book.get("template_id")
            self._active_seat_id = active_book.get("seatId") or active_book.get("seat_id")
            self._preselect_class_and_seat()

        self._preselect_plan()
        self._maybe_ready()

    def _on_member_data_error(self, error: str) -> None:
        logger.warning("No se pudieron cargar datos del socio: %s", error)
        self.name_label.setText(self.member_name or f"Socio #{self.member_id}")
        self._maybe_ready()

    # ------------------------------------------------------------------ pre-selection
    def _preselect_plan(self) -> None:
        if not self._active_membership_plan_name or self.plan_combo.count() == 0:
            return
        for i in range(self.plan_combo.count()):
            mp = self.plan_combo.itemData(i)
            if isinstance(mp, MembershipPlan) and mp.name == self._active_membership_plan_name:
                self.plan_combo.blockSignals(True)
                self.plan_combo.setCurrentIndex(i)
                self.plan_combo.blockSignals(False)
                self.amount_input.setValue(float(mp.price))
                break

    def _preselect_class_and_seat(self) -> None:
        """Pre-select the member's current class (+ seat) in the already-loaded combo."""
        if self._active_template_id is None or self.class_combo.count() == 0:
            return
        target = None
        for i in range(self.class_combo.count()):
            item = self.class_combo.itemData(i)
            if isinstance(item, TimeslotGroup) and self._active_template_id in item.template_ids:
                target = i
                break
        if target is None:
            return
        self.class_combo.blockSignals(True)
        self.class_combo.setCurrentIndex(target)
        self.class_combo.blockSignals(False)

        selected = self._current_item()
        if isinstance(selected, TimeslotGroup) and selected.requires_seats():
            # Honored by the base _on_seats_loaded once seats arrive.
            self._pending_seat_selection = self._active_seat_id
            self._show_seat_selector()
            self.controller.refresh_seats_for_selection(selected, self._selected_start_date())
        else:
            self._clear_seats()

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                return None
        return None

    # ------------------------------------------------------------------ accept / line
    def _on_accept_collect(self) -> None:
        plan = self.plan_combo.currentData()
        if not isinstance(plan, MembershipPlan):
            show_warning(self, "Selecciona un plan.", title="Renovación")
            return

        selection = self._current_item()
        selected_seat = self.seat_combo.currentData()
        if isinstance(selected_seat, Seat):
            ok, message = self.controller.ensure_seat_available(
                selection, self._selected_start_date(), selected_seat.id
            )
            if not ok:
                show_warning(self, message or "El lugar seleccionado ya no está disponible.", title="Renovación")
                self.controller.refresh_seats_for_selection(selection, self._selected_start_date())
                return
        self.accept()

    def get_line(self) -> Dict[str, Any]:
        plan = self.plan_combo.currentData()
        start_date = self._selected_start_date()
        line: Dict[str, Any] = {
            "line_type": "membership_renewal",
            "member_id": int(self.member_id),
            "plan_id": int(plan.id),
            "unit_price": float(self.amount_input.value()),
            "description": f"Renovación: {plan.name}",
        }
        # Adds template_id (resolved for the date) + seat_id only when a seat is chosen.
        self._append_template_and_seat(line, start_date)
        return line

    def closeEvent(self, event) -> None:
        try:
            self.controller.cleanup()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
