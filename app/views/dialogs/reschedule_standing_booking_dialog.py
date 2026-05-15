"""
Dialog for rescheduling standing bookings within membership validity.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import container, get_logger
from ...models.base import ClassTemplate, StandingBooking, TimeslotGroup
from ...services.subscription_service import SubscriptionService
from ...threads.authenticated_operations import AuthenticatedOperation, start_authenticated_operation
from ...utils.datetime_helpers import add_months, parse_iso_datetime
from ...utils.dialog_helpers import show_error, show_info, show_warning
from ..widgets.week_selector import WeekSelector
from ..widgets.weekly_class_grid import WeeklyClassGrid

logger = get_logger(__name__)


class RescheduleStandingBookingDialog(QDialog):
    """Dialog to reschedule a standing booking to another schedule."""

    def __init__(
        self,
        *,
        member_id: int,
        member_name: Optional[str] = None,
        standing_template_id: Optional[int] = None,
        membership_start: Optional[datetime] = None,
        membership_end: Optional[datetime] = None,
        membership_remaining_days: Optional[int] = None,
        standing_bookings_service: Optional[Any] = None,
        classes_service: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.member_id = int(member_id)
        self.member_name = member_name or f"Miembro #{self.member_id}"
        self.standing_template_id = standing_template_id
        self.membership_start = self._coerce_date(membership_start)
        self.membership_end = self._coerce_date(membership_end)
        self.membership_remaining_days = membership_remaining_days

        self.standing_bookings_service = standing_bookings_service or container.get(
            "standing_bookings_service"
        )
        self.classes_service = classes_service or container.get("classes_service")

        self._standing_booking: Optional[StandingBooking] = None
        self._templates: List[ClassTemplate] = []
        self._schedule_groups: List[TimeslotGroup] = []
        self._current_group: Optional[TimeslotGroup] = None
        self._source_template: Optional[ClassTemplate] = None

        self._min_date: Optional[date] = None
        self._max_date: Optional[date] = None
        self._range_end_date: Optional[date] = None

        self._class_type_code: str = "spinning"
        self._current_week_start: Optional[date] = None
        self._current_week_end: Optional[date] = None

        self._loading = False
        self._load_bookings_op: Optional[AuthenticatedOperation] = None
        self._templates_op: Optional[AuthenticatedOperation] = None
        self._sessions_op: Optional[AuthenticatedOperation] = None
        self._preview_op: Optional[AuthenticatedOperation] = None
        self._reschedule_op: Optional[AuthenticatedOperation] = None

        self._build_ui()
        self._connect_signals()
        self._load_data()

    def _build_ui(self) -> None:
        self.setWindowTitle("Cambiar horario")
        self.setMinimumWidth(900)

        layout = QVBoxLayout(self)

        info_group = QGroupBox("Socio")
        info_form = QFormLayout(info_group)

        self.member_name_label = QLabel(self.member_name)
        self.current_schedule_label = QLabel("-")
        self.membership_range_label = QLabel(self._format_range_label())

        info_form.addRow("Socio:", self.member_name_label)
        info_form.addRow("Horario actual:", self.current_schedule_label)
        info_form.addRow("Vigencia:", self.membership_range_label)
        layout.addWidget(info_group)

        form_group = QGroupBox("Cambio de horario")
        form_layout = QFormLayout(form_group)

        self.schedule_combo = QComboBox()
        self.schedule_combo.setMinimumWidth(320)
        form_layout.addRow("Nuevo horario:", self.schedule_combo)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        form_layout.addRow("Desde:", self.start_date)

        self.scope_combo = QComboBox()
        form_layout.addRow("Alcance:", self.scope_combo)

        self.end_date_value = QLabel("-")
        form_layout.addRow("Hasta:", self.end_date_value)

        self.strict_checkbox = QCheckBox("Modo estricto (si hay conflictos se cancela)")
        self.strict_checkbox.setChecked(True)
        form_layout.addRow("", self.strict_checkbox)

        self.summary_label = QLabel("Resumen: sin previsualizar")
        self.summary_label.setWordWrap(True)
        form_layout.addRow("Resumen:", self.summary_label)

        layout.addWidget(form_group)

        availability_group = QGroupBox("Disponibilidad semanal")
        availability_layout = QVBoxLayout(availability_group)

        self.week_selector = WeekSelector()
        availability_layout.addWidget(self.week_selector)

        self.weekly_grid = WeeklyClassGrid()
        availability_layout.addWidget(self.weekly_grid, 1)

        layout.addWidget(availability_group, 1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.preview_button = QPushButton("Previsualizar")
        self.apply_button = QPushButton("Aplicar cambios")
        self.apply_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancelar")

        buttons_layout.addWidget(self.preview_button)
        buttons_layout.addWidget(self.apply_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)

    def _connect_signals(self) -> None:
        self.cancel_button.clicked.connect(self.reject)
        self.preview_button.clicked.connect(self._on_preview_clicked)
        self.apply_button.clicked.connect(self._on_apply_clicked)

        self.schedule_combo.currentIndexChanged.connect(self._on_schedule_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        self.start_date.dateChanged.connect(self._on_start_date_changed)

        self.week_selector.week_changed.connect(self._on_week_changed)
        self.weekly_grid.day_selected.connect(self._on_grid_day_selected)

    def _load_data(self) -> None:
        if not self.standing_bookings_service:
            show_error(self, "Servicio de reservas no disponible.")
            return

        self.status_label.setText("Cargando horario del socio...")
        self._set_loading(True)

        self._load_bookings_op = start_authenticated_operation(
            service=self.standing_bookings_service,
            method_name="get_standing_bookings",
            parent=self,
            on_success=self._on_standing_bookings_loaded,
            on_error=self._on_standing_bookings_error,
            person_id=self.member_id,
            active_only=True,
        )

        self._templates_op = start_authenticated_operation(
            service=self.standing_bookings_service,
            method_name="get_class_templates",
            parent=self,
            on_success=self._on_templates_loaded,
            on_error=self._on_templates_error,
        )

    def _on_standing_bookings_loaded(self, bookings: List[StandingBooking]) -> None:
        self._standing_booking = self._select_standing_booking(bookings)
        if not self._standing_booking:
            self.status_label.setText("")
            show_warning(self, "No se encontro un horario fijo activo para este socio.")
            self._set_loading(False)
            return

        self.current_schedule_label.setText(self._format_booking_label(self._standing_booking))
        self._update_date_limits()
        self._maybe_build_schedule_groups()

    def _on_standing_bookings_error(self, error: str) -> None:
        self.status_label.setText("")
        show_error(self, error or "No se pudo cargar el horario fijo.")
        self._set_loading(False)

    def _on_templates_loaded(self, templates: List[ClassTemplate]) -> None:
        self._templates = [t for t in templates if getattr(t, "is_active", True)]
        self._maybe_build_schedule_groups()

    def _on_templates_error(self, error: str) -> None:
        show_error(self, error or "No se pudieron cargar las clases.")
        self._set_loading(False)

    def _maybe_build_schedule_groups(self) -> None:
        if not self._standing_booking or not self._templates:
            return

        self._source_template = next(
            (t for t in self._templates if t.id == self._standing_booking.template_id), None
        )

        if not self._source_template:
            show_warning(self, "No se encontro la clase original para este horario.")
            self._set_loading(False)
            return

        class_type_id = self._source_template.class_type_id
        filtered = [t for t in self._templates if t.class_type_id == class_type_id]
        groups = SubscriptionService.build_timeslot_groups(filtered)

        groups = [
            group
            for group in groups
            if self._source_template and self._source_template.id not in group.template_ids
        ]

        self._schedule_groups = groups
        self._populate_schedule_combo()

        self._class_type_code = (
            (self._source_template.class_type_name or "").strip().lower() or "spinning"
        )
        self._refresh_scope_options()
        self._set_loading(False)

        if self._current_group is None:
            self.status_label.setText("Selecciona un nuevo horario")
        else:
            self.status_label.setText("")

    def _populate_schedule_combo(self) -> None:
        self.schedule_combo.blockSignals(True)
        self.schedule_combo.clear()

        if not self._schedule_groups:
            self.schedule_combo.setEnabled(False)
            self.schedule_combo.blockSignals(False)
            show_warning(self, "No hay otros horarios disponibles para este tipo de clase.")
            return

        for group in self._schedule_groups:
            index = self.schedule_combo.count()
            self.schedule_combo.addItem(group.display_label(), group)
            self.schedule_combo.setItemData(index, group.display_tooltip(), Qt.ItemDataRole.ToolTipRole)

        self.schedule_combo.setEnabled(True)
        self.schedule_combo.setCurrentIndex(0)
        self.schedule_combo.blockSignals(False)
        self._on_schedule_changed(0)

    def _on_schedule_changed(self, index: int) -> None:
        data = self.schedule_combo.itemData(index)
        self._current_group = data if isinstance(data, TimeslotGroup) else None
        self._invalidate_preview()
        self._update_apply_enabled()
        self._load_week_sessions()

    def _on_scope_changed(self, _index: int) -> None:
        self._update_range()

    def _on_start_date_changed(self, _date: QDate) -> None:
        self._update_range()
        start_date = self._selected_start_date()
        self.week_selector.set_week(start_date)
        self.weekly_grid.set_selected_date(start_date)

    @Slot(date, date)
    def _on_week_changed(self, start_date: date, end_date: date) -> None:
        self._current_week_start = start_date
        self._current_week_end = end_date
        self._load_week_sessions()

    def _load_week_sessions(self) -> None:
        if not self._current_group or not self.classes_service:
            return

        if not self._current_week_start or not self._current_week_end:
            self._current_week_start, self._current_week_end = self.week_selector.get_current_week()

        self.weekly_grid.show_loading()
        template_ids = set(self._current_group.template_ids)

        self._sessions_op = start_authenticated_operation(
            service=self.classes_service,
            method_name="get_week_sessions_with_seats",
            parent=self,
            on_success=lambda sessions: self._on_sessions_loaded(sessions, template_ids),
            on_error=self._on_sessions_error,
            start_date=self._current_week_start,
            end_date=self._current_week_end,
            class_type_id=getattr(self._source_template, "class_type_id", None),
            venue_id=None,
        )

    def _on_sessions_loaded(self, sessions: List[Dict[str, Any]], template_ids: set[int]) -> None:
        sessions_by_day: Dict[date, Dict[str, Any]] = {}

        for session in sessions:
            template_id_raw = session.get("templateId") or session.get("template_id")
            template_id = int(template_id_raw) if template_id_raw is not None else None
            if template_ids and template_id not in template_ids:
                continue

            start_at_raw = session.get("startAt")
            start_at = parse_iso_datetime(start_at_raw) if isinstance(start_at_raw, str) else start_at_raw
            if not isinstance(start_at, datetime):
                continue

            session_date = start_at.date()
            seats = []
            for seat in session.get("seats", []):
                seats.append({
                    "seat_id": seat.get("seatId"),
                    "label": seat.get("label"),
                    "status": seat.get("status"),
                    "will_expire_soon": seat.get("willExpireSoon", False),
                    "occupant": seat.get("occupant"),
                })

            sessions_by_day[session_date] = {
                "id": session.get("id"),
                "name": session.get("name"),
                "start_at": start_at,
                "end_at": parse_iso_datetime(session.get("endAt")),
                "capacity": session.get("capacity"),
                "seats": seats,
                "template_id": template_id,
            }

        if not self._current_week_start:
            return

        grid_data = {}
        for i in range(7):
            day_date = self._current_week_start + timedelta(days=i)
            if day_date in sessions_by_day:
                grid_data[day_date] = sessions_by_day[day_date]

        self.weekly_grid.populate_grid(
            week_start=self._current_week_start,
            sessions_by_day=grid_data,
            class_type_code=self._class_type_code,
        )

    def _on_sessions_error(self, error: str) -> None:
        self.weekly_grid.show_error(error or "No se pudieron cargar las sesiones.")

    def _on_grid_day_selected(self, day_date: date) -> None:
        if not day_date:
            return

        if self._min_date and day_date < self._min_date:
            return
        if self._max_date and day_date > self._max_date:
            return

        self.start_date.setDate(QDate(day_date.year, day_date.month, day_date.day))

    def _on_preview_clicked(self) -> None:
        payload = self._build_reschedule_payload()
        if not payload:
            return

        self._set_loading(True)
        self.status_label.setText("Previsualizando cambios...")
        self._preview_op = start_authenticated_operation(
            service=self.standing_bookings_service,
            method_name="preview_reschedule_standing_booking",
            parent=self,
            on_success=self._on_preview_loaded,
            on_error=self._on_preview_error,
            **payload,
        )

    def _on_preview_loaded(self, result: Dict[str, Any]) -> None:
        self._set_loading(False)
        self.status_label.setText("")
        counts = result.get("counts") or {}
        self.summary_label.setText(self._format_counts_summary(counts))

        available = int(counts.get("will_create", 0))
        if available > 0:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)
            show_warning(self, "No hay fechas disponibles para reprogramar.")

    def _on_preview_error(self, error: str) -> None:
        self._set_loading(False)
        self.status_label.setText("")
        show_error(self, error or "No se pudo previsualizar el cambio.")

    def _on_apply_clicked(self) -> None:
        payload = self._build_reschedule_payload()
        if not payload:
            return

        payload["strict"] = self.strict_checkbox.isChecked()
        self._set_loading(True)
        self.status_label.setText("Aplicando cambios...")
        self._reschedule_op = start_authenticated_operation(
            service=self.standing_bookings_service,
            method_name="reschedule_standing_booking",
            parent=self,
            on_success=self._on_reschedule_loaded,
            on_error=self._on_reschedule_error,
            **payload,
        )

    def _on_reschedule_loaded(self, result: Dict[str, Any]) -> None:
        self._set_loading(False)
        self.status_label.setText("")

        success = bool(result.get("success"))
        message = result.get("message") or ""
        counts = result.get("counts") or {}
        summary = self._format_counts_summary(counts)

        if success:
            show_info(self, message or "Cambios aplicados.", detailed_text=summary, title="Cambiar clase")
            self.accept()
        else:
            show_warning(
                self,
                message or "No se pudieron aplicar los cambios.",
                detailed_text=summary,
                title="Cambiar clase",
            )

    def _on_reschedule_error(self, error: str) -> None:
        self._set_loading(False)
        self.status_label.setText("")
        show_error(self, error or "No se pudieron aplicar los cambios.")

    def _build_reschedule_payload(self) -> Optional[Dict[str, Any]]:
        if not self._standing_booking or not self._current_group:
            show_warning(self, "Selecciona un horario valido.")
            return None

        start_date = self._selected_start_date()
        end_date = self._range_end_date or start_date

        if self._max_date and start_date > self._max_date:
            show_warning(self, "La fecha seleccionada esta fuera de la vigencia.")
            return None

        target_template = self._current_group.template_for_date(start_date) or self._current_group.get_first_template()
        if not target_template:
            show_warning(self, "No se pudo resolver el horario seleccionado.")
            return None

        return {
            "standing_booking_id": self._standing_booking.id,
            "start_date": start_date,
            "end_date": end_date,
            "target_template_id": int(target_template.id),
            "target_seat_id": None,
        }

    def _refresh_scope_options(self) -> None:
        current_key = self.scope_combo.currentData()
        duration_days = self._membership_duration_days()

        options = [("day", "Dia")]
        if duration_days is None or duration_days >= 7:
            options.append(("week", "Semana"))
        if duration_days is None or duration_days >= 28:
            options.append(("month", "Mes"))
        if duration_days is None or duration_days >= 365:
            options.append(("year", "Ano"))

        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        for key, label in options:
            self.scope_combo.addItem(label, key)

        if current_key is not None:
            for index in range(self.scope_combo.count()):
                if self.scope_combo.itemData(index) == current_key:
                    self.scope_combo.setCurrentIndex(index)
                    break
        else:
            self.scope_combo.setCurrentIndex(0)

        self.scope_combo.blockSignals(False)
        self._update_range()

    def _update_date_limits(self) -> None:
        today = date.today()
        candidates_min = [today]
        if self.membership_start:
            candidates_min.append(self.membership_start)
        if self._standing_booking:
            candidates_min.append(self._standing_booking.start_date.date())

        self._min_date = max(candidates_min)

        candidates_max = []
        if self.membership_end:
            candidates_max.append(self.membership_end)
        if self._standing_booking:
            candidates_max.append(self._standing_booking.end_date.date())

        self._max_date = min(candidates_max) if candidates_max else None

        if self._min_date:
            self.start_date.setMinimumDate(
                QDate(self._min_date.year, self._min_date.month, self._min_date.day)
            )

        if self._max_date:
            self.start_date.setMaximumDate(
                QDate(self._max_date.year, self._max_date.month, self._max_date.day)
            )

        self.start_date.setDate(
            QDate(self._min_date.year, self._min_date.month, self._min_date.day)
        )

        self._update_range()
        self.week_selector.set_week(self._min_date)
        self.weekly_grid.set_selected_date(self._min_date)

    def _update_range(self) -> None:
        start_date = self._selected_start_date()
        scope_key = self.scope_combo.currentData()
        end_date = self._calculate_end_date(start_date, scope_key)

        if self._max_date and end_date > self._max_date:
            end_date = self._max_date

        self._range_end_date = end_date
        self.end_date_value.setText(end_date.isoformat() if end_date else "-")
        self._invalidate_preview()

    def _calculate_end_date(self, start_date: date, scope_key: Optional[str]) -> date:
        if scope_key == "week":
            return start_date + timedelta(days=6)
        if scope_key == "month":
            return add_months(start_date, 1) - timedelta(days=1)
        if scope_key == "year":
            return add_months(start_date, 12) - timedelta(days=1)
        return start_date

    def _invalidate_preview(self) -> None:
        self.summary_label.setText("Resumen: sin previsualizar")
        self._update_apply_enabled()

    def _update_apply_enabled(self) -> None:
        can_apply = bool(self._current_group) and bool(self._standing_booking) and not self._loading
        self.apply_button.setEnabled(can_apply)
        self.preview_button.setEnabled(bool(self._current_group) and not self._loading)

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        for widget in (
            self.schedule_combo,
            self.start_date,
            self.scope_combo,
            self.preview_button,
            self.week_selector,
        ):
            widget.setEnabled(not loading)
        self.preview_button.setEnabled(not loading and self._current_group is not None)
        self._update_apply_enabled()

    def _format_counts_summary(self, counts: Dict[str, Any]) -> str:
        total = int(counts.get("total", 0))
        available = int(counts.get("will_create", 0))
        blocked = 0
        for status, count in counts.items():
            if status in ("total", "will_create"):
                continue
            blocked += int(count)
        return f"Total: {total} | Disponibles: {available} | No disponibles: {blocked}"

    def _format_booking_label(self, booking: StandingBooking) -> str:
        day_label = self._weekday_name(booking.weekday)
        time_label = booking.start_time_local or ""
        name_label = booking.template_name or booking.class_type_name or "Clase"
        venue_label = booking.venue_name or ""
        day_time = " ".join(part for part in (day_label, time_label) if part)
        parts = [part for part in (day_time, name_label, venue_label) if part]
        return " - ".join(parts) if parts else "-"

    def _format_range_label(self) -> str:
        if not self.membership_start and not self.membership_end:
            return "-"
        start_label = self.membership_start.isoformat() if self.membership_start else "?"
        end_label = self.membership_end.isoformat() if self.membership_end else "?"
        return f"{start_label} a {end_label}"

    def _membership_duration_days(self) -> Optional[int]:
        if self.membership_start and self.membership_end:
            return (self.membership_end - self.membership_start).days + 1
        if self.membership_remaining_days is not None:
            return int(self.membership_remaining_days)
        return None

    def _weekday_name(self, weekday: Optional[int]) -> str:
        if weekday is None:
            return ""
        mapping = {
            0: "Domingo",
            1: "Lunes",
            2: "Martes",
            3: "Miercoles",
            4: "Jueves",
            5: "Viernes",
            6: "Sabado",
            7: "Domingo",
        }
        return mapping.get(int(weekday), "")

    @staticmethod
    def _coerce_date(value: Optional[datetime]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return None

    def _selected_start_date(self) -> date:
        qd = self.start_date.date()
        return date(qd.year(), qd.month(), qd.day())

    def _select_standing_booking(self, bookings: List[StandingBooking]) -> Optional[StandingBooking]:
        if not bookings:
            return None

        if self.standing_template_id is not None:
            for booking in bookings:
                if booking.template_id == self.standing_template_id:
                    return booking

        return bookings[0]
