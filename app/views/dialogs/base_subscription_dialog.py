"""
Base dialog class with shared logic for subscription dialogs.
Contains common UI handlers, seat management, and event handling.
"""

from typing import Any, Dict, Optional, List
from datetime import date, datetime, time

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QLabel,
)

from ...core.logging import get_logger
from ...models.base import ClassTemplate, MembershipPlan, Seat, TimeslotGroup
from ...utils.dialog_helpers import show_error, show_warning

logger = get_logger(__name__)

AMOUNT_MAXIMUM = 1_000_000.0


class BaseSubscriptionDialog(QDialog):
    """
    Base class for subscription dialogs (New/Renew).

    Provides shared functionality for:
    - Plan combo population and price auto-update
    - Class template/group combo population
    - Seat availability and selection
    - Form validation helpers

    Subclasses should implement:
    - _build_ui(): Create dialog widgets
    - _connect_signals(): Wire up Qt signals
    - _collect_form(): Gather form data for submission
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_loaded = False
        self._pending_seat_selection: Optional[int] = None

        # These attributes must be set by subclasses in _build_ui()
        self.plan_combo: QComboBox
        self.class_combo: QComboBox
        self.seat_combo: QComboBox
        self.seat_label: QLabel
        self.start_date: QDateEdit  # or similar widget
        self.amount_input: Any  # QDoubleSpinBox

    # ---------------------------
    # Shared Handlers: Plans
    # ---------------------------
    def _on_plan_changed(self, idx: int) -> None:
        """Update amount when plan selection changes."""
        plan = self.plan_combo.itemData(idx)
        if isinstance(plan, MembershipPlan):
            self.amount_input.setValue(float(plan.price))

    def _on_plans_loaded(self, plans: List[MembershipPlan]) -> None:
        """Populate plan combo with loaded plans."""
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()

        if not plans:
            show_warning(self, "No se encontraron planes de membresía.", title="Planes")
            self.plan_combo.blockSignals(False)
            return

        for plan in plans:
            self.plan_combo.addItem(f"{plan.name} - ${plan.price:,.2f}", plan)

        # Auto-select first and update amount
        self.plan_combo.setCurrentIndex(0)
        self._on_plan_changed(0)
        self.plan_combo.blockSignals(False)
        self._maybe_ready()

    # ---------------------------
    # Shared Handlers: Class Templates/Groups
    # ---------------------------
    def _on_timeslot_groups_loaded(self, groups: List[TimeslotGroup]) -> None:
        """Handle timeslot groups loaded from the service."""
        self.class_combo.blockSignals(True)
        self.class_combo.clear()

        if not groups:
            show_warning(self, "No se encontraron clases.", title="Clases")
            self.class_combo.blockSignals(False)
            return

        # Fill combo with grouped timeslots
        for group in groups:
            label = group.display_label()
            self.class_combo.addItem(label, group)

        self.class_combo.setCurrentIndex(0)
        self.class_combo.blockSignals(False)

        # If the first group requires seats, load availability for the selected date
        first_group = self.class_combo.currentData()
        if isinstance(first_group, TimeslotGroup) and first_group.requires_seats():
            self._show_seat_selector()
            if hasattr(self, 'controller'):
                self.controller.refresh_seats_for_selection(first_group, self._selected_start_date())

        self._maybe_ready()

    def _on_class_templates_loaded(self, templates: List[ClassTemplate]) -> None:
        """
        Fallback handler for individual templates.
        This is used when timeslot grouping is not available.
        """
        logger.warning("Loading individual templates instead of groups")
        self.class_combo.blockSignals(True)
        self.class_combo.clear()

        if not templates:
            show_warning(self, "No se encontraron clases.", title="Clases")
            self.class_combo.blockSignals(False)
            return

        # Create display labels for templates
        for t in templates:
            label = getattr(t, "display_name", None)
            if callable(label):
                text = t.display_name()
            else:
                # fallback: "Lun 07:00  Spinning (Sala A)"
                wd = getattr(t, "weekday", None)
                wd_names = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
                wd_txt = wd_names.get(wd, "?") if wd is not None else "?"
                time_txt = getattr(t, "start_time_local", "") or ""
                typ = getattr(t, "class_type_name", "") or ""
                venue = getattr(t, "venue_name", "") or ""
                parts = [wd_txt, time_txt, typ, venue]
                text = " ".join([p for p in parts if p]).strip()
            self.class_combo.addItem(text, t)

        self.class_combo.setCurrentIndex(0)
        self.class_combo.blockSignals(False)

        # If the first requires seat, load with the current date
        first = self.class_combo.currentData()
        if isinstance(first, ClassTemplate) and first.requires_seats():
            self._show_seat_selector()
            if hasattr(self, 'controller'):
                self.controller.refresh_seats_for_selection(first, self._selected_start_date())

        self._maybe_ready()

    # ---------------------------
    # Shared Handlers: UI Events
    # ---------------------------
    def _on_class_changed(self, index: int) -> None:
        """Update seat availability when class changes."""
        self._clear_seats()

        selection = self.class_combo.itemData(index)
        start_date = self._selected_start_date()

        requires_seat = False
        if isinstance(selection, TimeslotGroup):
            requires_seat = selection.requires_seats()
        elif isinstance(selection, ClassTemplate):
            requires_seat = selection.requires_seats()
        elif hasattr(self, 'controller'):
            template, _ = self.controller.resolve_template_for_selection(selection, start_date)
            requires_seat = bool(template and template.requires_seats())

        if requires_seat:
            self._show_seat_selector()
            if hasattr(self, 'controller'):
                self.controller.refresh_seats_for_selection(selection, start_date)
        else:
            self._clear_seats()

    def _on_date_changed(self, _qdate: QDate) -> None:
        """Reload seat availability when date changes."""
        selection = self.class_combo.currentData()
        if selection is None:
            return

        start_date = self._selected_start_date()

        requires_seat = False
        if hasattr(self, 'controller'):
            template, _ = self.controller.resolve_template_for_selection(selection, start_date)
            requires_seat = bool(template and template.requires_seats())

        if requires_seat:
            self._show_seat_selector()
            if hasattr(self, 'controller'):
                self.controller.refresh_seats_for_selection(selection, start_date)
        else:
            self._clear_seats()

    # ---------------------------
    # Shared Handlers: Seats
    # ---------------------------
    def _on_seats_loaded(self, seats: List[Seat]) -> None:
        """Populate seat combo with available seats."""
        self.seat_combo.blockSignals(True)
        self.seat_combo.clear()

        if not seats:
            self.seat_combo.setEnabled(False)
            self.seat_combo.blockSignals(False)
            return

        first_available = -1
        for idx, seat in enumerate(seats):
            label = getattr(seat, "label", str(getattr(seat, "id", "")))
            is_available = bool(getattr(seat, "is_available", True))
            if not is_available:
                label += " (Ocupado)"
            self.seat_combo.addItem(label, seat)
            model_index = self.seat_combo.model().index(idx, 0)
            if not is_available:
                self.seat_combo.model().setData(model_index, QColor('#888888'), Qt.ItemDataRole.ForegroundRole)
                self.seat_combo.model().setData(model_index, 'Lugar ocupado', Qt.ItemDataRole.ToolTipRole)
            else:
                self.seat_combo.model().setData(model_index, 'Disponible', Qt.ItemDataRole.ToolTipRole)
                if first_available == -1:
                    first_available = idx

        # Handle pending seat selection
        if self._pending_seat_selection is not None:
            for i in range(self.seat_combo.count()):
                data = self.seat_combo.itemData(i)
                if isinstance(data, Seat) and data.id == self._pending_seat_selection:
                    self.seat_combo.setCurrentIndex(i)
                    if bool(getattr(data, 'is_available', True)):
                        first_available = i
                    break
            self._pending_seat_selection = None

        if first_available >= 0:
            self.seat_combo.setCurrentIndex(first_available)
        self.seat_combo.setEnabled(first_available >= 0)
        self.seat_combo.blockSignals(False)

    def _on_seats_error(self, error: str) -> None:
        """Handle seat loading errors."""
        show_error(self, error or "No se pudieron cargar los lugares")

    # ---------------------------
    # Shared Helper Methods
    # ---------------------------
    def _selected_start_date(self) -> date:
        """Get the selected start date as a Python date object."""
        qd = self.start_date.date()
        return date(qd.year(), qd.month(), qd.day())

    def _build_start_at(self, start_date: date) -> datetime:
        """Build a timezone-aware start datetime at midnight for the given date."""
        local_tz = datetime.now().astimezone().tzinfo
        return datetime.combine(start_date, time.min, tzinfo=local_tz)

    def _append_template_and_seat(self, form_data: Dict[str, Any], start_date: date) -> None:
        """Attach template_id and seat_id to form data when available."""
        selection = self.class_combo.currentData()
        if hasattr(self, 'controller'):
            resolved_template, _ = self.controller.resolve_template_for_selection(selection, start_date)
            if resolved_template is not None:
                form_data["template_id"] = int(resolved_template.id)

        selected_seat = self.seat_combo.currentData()
        if isinstance(selected_seat, Seat):
            form_data["seat_id"] = int(selected_seat.id)

    def _clear_seats(self) -> None:
        """Clear and hide seat selector."""
        self.seat_label.hide()
        self.seat_combo.clear()
        self.seat_combo.setVisible(False)
        self.seat_combo.setEnabled(False)

    def _show_seat_selector(self) -> None:
        """Show seat selector controls."""
        self.seat_label.show()
        self.seat_combo.setVisible(True)
        self.seat_combo.setEnabled(True)

    def _current_item(self) -> Optional[Any]:
        """Get current selected item (can be TimeslotGroup, ClassTemplate, or None)."""
        return self.class_combo.currentData() if self.class_combo.currentIndex() >= 0 else None

    def _current_template(self) -> Optional[ClassTemplate]:
        """Resolve the current selection into an actual template for the chosen date."""
        if not hasattr(self, 'controller'):
            return None
        selection = self._current_item()
        template, _ = self.controller.resolve_template_for_selection(selection, self._selected_start_date())
        return template

    def _maybe_ready(self) -> None:
        """
        Hook for subclasses to check if dialog is ready for submission.
        Default implementation does nothing.
        """
        pass

    def _fill_seats(self, seats: List[Seat], template: Optional[ClassTemplate] = None) -> None:
        """
        Fill seat combo with seats. If template is provided, will check if seats are required.
        This is a helper for subclasses that need more control over seat filling.
        """
        requires = bool(template and template.requires_seats())
        self.seat_combo.blockSignals(True)
        self.seat_combo.clear()

        if not requires or not seats:
            self._clear_seats()
            self.seat_combo.blockSignals(False)
            return

        self._show_seat_selector()
        first_available = -1
        for idx, seat in enumerate(seats):
            label = seat.display_name() if hasattr(seat, "display_name") else str(seat.id)
            is_available = bool(getattr(seat, "is_available", True))
            if not is_available:
                label += " (Ocupado)"
            self.seat_combo.addItem(label, seat)
            model_index = self.seat_combo.model().index(idx, 0)
            if not is_available:
                self.seat_combo.model().setData(model_index, QColor('#888888'), Qt.ItemDataRole.ForegroundRole)
                self.seat_combo.model().setData(model_index, 'Lugar ocupado', Qt.ItemDataRole.ToolTipRole)
            if is_available and first_available == -1:
                first_available = idx

        if first_available >= 0:
            self.seat_combo.setCurrentIndex(first_available)
        self.seat_combo.setEnabled(first_available >= 0)
        self.seat_combo.blockSignals(False)
