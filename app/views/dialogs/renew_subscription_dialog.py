"""Dialog for renewing member subscriptions using first-occurrence date logic.
Inherits shared logic from BaseSubscriptionDialog.
"""

from typing import Any, Dict, Optional, List

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QDate, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.logging import get_logger
from ...models.base import ClassTemplate, MembershipPlan, Seat, TimeslotGroup
from ...controllers.renew_subscription_controller import RenewSubscriptionController as Controller
from .base_subscription_dialog import BaseSubscriptionDialog, AMOUNT_MAXIMUM
from .admin_password_dialog import AdminPasswordDialog
from ...utils.qt_helpers import configure_amount_input, populate_payment_methods
from ...utils.dialog_helpers import show_error, show_info, show_success, show_warning

logger = get_logger(__name__)

MINIMUM_DIALOG_WIDTH = 620
NO_CLASS_OPTION = "<Sin clase fija>"


class RenewSubscriptionUIText:
    WINDOW_TITLE = "Renovar membresía"
    MEMBER_INFO_TITLE = "Información del miembro"

    NAME_LABEL = "Nombre"
    CURRENT_PLAN_LABEL = "Membresía actual"
    END_DATE_LABEL = "Vence"

    PLAN_LABEL = "Nuevo plan"
    START_DATE_LABEL = "Fecha de inicio"
    CLASS_LABEL = "Clase (horario fijo)"
    SEAT_LABEL = "Lugar"
    PAYMENT_METHOD_LABEL = "Método de pago"
    AMOUNT_LABEL = "Monto"

    CONFIRM_TEXT = "Renovar"
    CANCEL_TEXT = "Cancelar"

    NO_PLANS_WARNING = "No se encontraron planes."
    NO_CLASSES_WARNING = "No se encontraron clases."
    NO_SEATS_WARNING = "Sin lugares disponibles en la fecha seleccionada."
    ERROR_TITLE = "Error"
    SUCCESS_TITLE = "Renovación completada"
    RENEWAL_SUCCESS = "Suscripción renovada correctamente."
    BOOKING_SUCCESS = "Reserva fija creada correctamente."


class RenewSubscriptionDialog(BaseSubscriptionDialog):
    """
    Flujo:
      1) Carga datos del miembro y catálogos
      2) Sugerir start_date = día siguiente al fin de membresía actual (si existe), si no hoy
      3) Al cambiar fecha o clase → controller.refresh_seats(template, date)
      4) Renovar → crear standing booking (si aplica)
    """

    # Signal emitted when subscription is renewed successfully (member_id, result)
    subscription_renewed = Signal(int, dict)

    def __init__(
        self,
        controller: Controller,
        member_id: int,
        member_name: Optional[str] = None,
        member_data: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        self.controller = controller
        self.member_id = member_id
        self.member_name = member_name
        self.member_data = member_data
        self._operation_in_progress = False  # Protection flag against multiple executions

        # Internal state for autosuggestions
        self._active_membership_plan_name: Optional[str] = None
        self._active_template_id: Optional[int] = None

        super().__init__(parent)

        self.setWindowTitle(RenewSubscriptionUIText.WINDOW_TITLE)
        self.setModal(True)
        self.setMinimumWidth(MINIMUM_DIALOG_WIDTH)

        self._build_ui()
        self._connect_signals()

        self._set_loading(True)
        QTimer.singleShot(50, self._initial_load)

    # ---------------------------
    # UI
    # ---------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Grupo: info del miembro
        info_group = QGroupBox(RenewSubscriptionUIText.MEMBER_INFO_TITLE)
        info_form = QFormLayout(info_group)

        self.name_label = QLabel(self.member_name or "—")
        self.current_plan_label = QLabel("—")
        self.end_date_label = QLabel("—")

        info_form.addRow(RenewSubscriptionUIText.NAME_LABEL, self.name_label)
        info_form.addRow(RenewSubscriptionUIText.CURRENT_PLAN_LABEL, self.current_plan_label)
        info_form.addRow(RenewSubscriptionUIText.END_DATE_LABEL, self.end_date_label)

        # Grupo: renovación
        form_group = QGroupBox("Datos de renovación")
        form = QFormLayout(form_group)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        # Nuevo plan
        self.plan_combo = QComboBox()
        form.addRow(RenewSubscriptionUIText.PLAN_LABEL, self.plan_combo)

        # Fecha inicio sugerida
        self.start_date = QDateEditWithToday()
        form.addRow(RenewSubscriptionUIText.START_DATE_LABEL, self.start_date)

        # Clase fija
        self.class_combo = QComboBox()
        form.addRow(RenewSubscriptionUIText.CLASS_LABEL, self.class_combo)

        # Asiento (visible solo si la clase requiere)
        self.seat_label = QLabel(RenewSubscriptionUIText.SEAT_LABEL)
        self.seat_combo = QComboBox()
        self.seat_label.setVisible(False)
        self.seat_combo.setVisible(False)
        self.seat_combo.setEnabled(False)
        form.addRow(self.seat_label, self.seat_combo)

        # Pago
        self.payment_combo = QComboBox()
        populate_payment_methods(self.payment_combo)
        form.addRow(RenewSubscriptionUIText.PAYMENT_METHOD_LABEL, self.payment_combo)

        self.amount_input = QDoubleSpinBox()
        configure_amount_input(self.amount_input, AMOUNT_MAXIMUM)
        form.addRow(RenewSubscriptionUIText.AMOUNT_LABEL, self.amount_input)

        layout.addWidget(info_group)
        layout.addWidget(form_group)

        # Botones
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.confirm_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText(RenewSubscriptionUIText.CONFIRM_TEXT)
        self.confirm_button.setEnabled(False)
        self.cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText(RenewSubscriptionUIText.CANCEL_TEXT)
        layout.addWidget(self.button_box)

    def _connect_signals(self) -> None:
        # UI
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        # Use base class handlers for common events
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        self.start_date.dateChanged.connect(self._on_date_changed)

        # Controller - use base class handlers where possible
        self.controller.plans_loaded.connect(self._on_plans_loaded_renewal)
        self.controller.plans_error.connect(self._on_plans_error)

        # Use timeslot groups instead of individual templates
        if hasattr(self.controller.subscription_service, 'timeslot_groups_loaded'):
            self.controller.subscription_service.timeslot_groups_loaded.connect(self._on_timeslot_groups_loaded_renewal)

        self.controller.class_templates_error.connect(self._on_class_templates_error)
        self.controller.member_data_loaded.connect(self._on_member_data_loaded)
        self.controller.member_data_error.connect(self._on_member_data_error)
        self.controller.seats_loaded.connect(self._on_seats_loaded_renewal)
        self.controller.seats_error.connect(self._on_seats_error)
        self.controller.renewal_success.connect(self._on_renewal_success)
        self.controller.renewal_error.connect(self._on_renewal_error)

    # ---------------------------
    # Carga inicial
    # ---------------------------
    def _initial_load(self) -> None:
        self.controller.load_membership_plans()
        if self.controller.standing_bookings_service:
            self.controller.load_class_templates()
        self.controller.load_defaults(self.member_id, self.member_name, self.member_data)

    def _set_loading(self, loading: bool) -> None:
        self.confirm_button.setEnabled(not loading)

    # ---------------------------
    # Handlers de carga (custom versions for renewal-specific logic)
    # ---------------------------
    def _on_plans_loaded_renewal(self, plans: List[MembershipPlan]) -> None:
        """Custom plan loading that pre-selects the member's current plan."""
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()

        if not plans:
            show_warning(self, RenewSubscriptionUIText.NO_PLANS_WARNING, title="Planes")
            self.plan_combo.blockSignals(False)
            return

        for p in plans:
            self.plan_combo.addItem(f"{p.name} - ${p.price:,.2f}", p)

        # Si hay membresía activa, sugerir el mismo plan
        if self._active_membership_plan_name:
            for i in range(self.plan_combo.count()):
                mp = self.plan_combo.itemData(i)
                if isinstance(mp, MembershipPlan) and mp.name == self._active_membership_plan_name:
                    self.plan_combo.setCurrentIndex(i)
                    self.amount_input.setValue(float(mp.price))
                    break
        else:
            self.plan_combo.setCurrentIndex(0)
            p0 = self.plan_combo.currentData()
            if isinstance(p0, MembershipPlan):
                self.amount_input.setValue(float(p0.price))

        self.plan_combo.blockSignals(False)
        self._maybe_ready()

    def _on_plans_error(self, error: str) -> None:
        show_error(self, error, title=RenewSubscriptionUIText.ERROR_TITLE)

    def _on_timeslot_groups_loaded_renewal(self, groups: List[TimeslotGroup]) -> None:
        """Custom timeslot group loading that includes 'no class' option and pre-selects current booking."""
        self.class_combo.blockSignals(True)
        self.class_combo.clear()

        if not groups:
            show_warning(self, RenewSubscriptionUIText.NO_CLASSES_WARNING, title="Clases")
            self.class_combo.blockSignals(False)
            return

        # Opción "sin clase" al inicio para permitir membresías sin standing booking
        self.class_combo.addItem(NO_CLASS_OPTION, None)

        # Fill combo with grouped timeslots
        for group in groups:
            label = group.display_label()
            self.class_combo.addItem(label, group)

        # Si el miembro tiene booking activo, sugerir esa clase/grupo
        if self._active_template_id is not None:
            for i in range(self.class_combo.count()):
                item_data = self.class_combo.itemData(i)
                if isinstance(item_data, TimeslotGroup):
                    if self._active_template_id in item_data.template_ids:
                        self.class_combo.setCurrentIndex(i)
                        break

        self.class_combo.blockSignals(False)

        # Si la clase/grupo seleccionado requiere asiento, cargar asientos para la fecha elegida
        selected_item = self._current_item()
        if isinstance(selected_item, TimeslotGroup) and selected_item.requires_seats():
            self._show_seat_selector()
            self.controller.refresh_seats_for_selection(selected_item, self._selected_start_date())
        else:
            self._clear_seats()

        self._maybe_ready()

    def _on_class_templates_error(self, error: str) -> None:
        show_error(self, error, title=RenewSubscriptionUIText.ERROR_TITLE)

    def _on_member_data_loaded(self, payload: dict) -> None:
        # Guardar estado simplificado
        member = payload.get("member") or {}
        active_mem = payload.get("active_membership") or {}
        active_book = payload.get("active_booking") or {}

        # Debug logging
        logger.info(f"Dialog received member data: member={member}, active_mem keys={list(active_mem.keys()) if active_mem else 'None'}")

        full_name = member.get("full_name") or f"Miembro #{self.member_id}"
        logger.info(f"Setting member name to: {full_name}")
        self.name_label.setText(full_name)

        # Sugerir fecha inicio = día después de endDate si existe; si no, hoy
        end_iso = active_mem.get("endDate") or active_mem.get("end_date")
        self._active_membership_plan_name = active_mem.get("planName") or active_mem.get("plan_name")
        self.current_plan_label.setText(self._active_membership_plan_name or "—")

        if end_iso:
            try:
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                self.end_date_label.setText(end_dt.date().isoformat())
                self.start_date.setDate(QDate(end_dt.year, end_dt.month, end_dt.day).addDays(1))
            except Exception:
                self.end_date_label.setText("—")
                self.start_date.setDate(QDate.currentDate())
        else:
            self.end_date_label.setText("—")
            self.start_date.setDate(QDate.currentDate())

        # Prefill clase actual si existe
        self._active_template_id = active_book.get("templateId") or active_book.get("template_id")

        self._maybe_ready()

    def _on_member_data_error(self, error: str) -> None:
        logger.warning("Fallo al cargar datos del miembro: %s", error)
        self.name_label.setText(self.member_name or f"Miembro #{self.member_id}")
        self.current_plan_label.setText("—")
        self.end_date_label.setText("—")
        self.start_date.setDate(QDate.currentDate())
        self._maybe_ready()

    def _maybe_ready(self) -> None:
        has_plans = self.plan_combo.count() > 0
        has_pay = self.payment_combo.count() > 0
        if has_plans and has_pay:
            self._set_loading(False)

    # ---------------------------
    # Asientos (custom version that uses template instead of just seats)
    # ---------------------------
    def _on_seats_loaded_renewal(self, seats: List[Seat]) -> None:
        """Use the base class _fill_seats helper with current template."""
        template = self._current_template()
        self._fill_seats(seats, template)

    # ---------------------------
    # Confirm
    # ---------------------------
    def _on_accept(self) -> None:
        # Prevent multiple executions
        if self._operation_in_progress:
            logger.warning("Renewal operation already in progress, ignoring duplicate request")
            return

        form_data = self._collect_form()

        selection = self._current_item()
        selected_seat = self.seat_combo.currentData()
        if isinstance(selected_seat, Seat):
            ok, message = self.controller.ensure_seat_available(selection, self._selected_start_date(), selected_seat.id)
            if not ok:
                warn_msg = message or 'El lugar seleccionado ya no está disponible.'
                show_warning(self, warn_msg, title=RenewSubscriptionUIText.ERROR_TITLE)
                self.controller.refresh_seats_for_selection(selection, self._selected_start_date())
                return

        # Validate start date with admin authorization if needed
        validation_result = self._validate_start_date_with_admin(form_data)
        if validation_result == "cancel":
            return  # User cancelled admin password dialog
        elif validation_result == "invalid":
            return  # Date out of range or invalid password

        err = self.controller.validate_form_data(form_data)
        if err:
            show_warning(self, err, title=RenewSubscriptionUIText.ERROR_TITLE)
            return

        # Set flag and disable button to prevent multiple clicks
        self._operation_in_progress = True
        self._set_loading(True)
        self.controller.renew_subscription(form_data)

    def _on_renewal_success(self, result: Dict[str, Any]) -> None:
        """Handle successful subscription renewal from backend."""
        standing_booking_id = result.get("standing_booking_id")
        materialization_stats = result.get("materialization_stats")

        # Build success message based on what was created by the backend
        success_message = RenewSubscriptionUIText.RENEWAL_SUCCESS

        if standing_booking_id:
            # Backend created standing booking(s) for fixed-timeslot plans
            success_message += f"\n\n✓ Reserva fija creada (ID: {standing_booking_id})"

            if materialization_stats:
                # Parse materialization stats if available
                try:
                    import json
                    stats = json.loads(materialization_stats) if isinstance(materialization_stats, str) else materialization_stats
                    if isinstance(stats, dict):
                        created = stats.get("materialized_count", 0)
                        if created > 0:
                            success_message += f"\n✓ {created} clases materializadas automáticamente"
                except (json.JSONDecodeError, TypeError, AttributeError):
                    # If we can't parse stats, just show the raw data
                    success_message += f"\nDetalles: {materialization_stats}"

        # Reset flag and show success message
        self._operation_in_progress = False
        self._set_loading(False)

        # Emit signal to notify parent that subscription was renewed
        logger.info(f"Emitting subscription_renewed signal for member {self.member_id}")
        self.subscription_renewed.emit(self.member_id, result)

        # Show success message and close dialog
        show_success(self, success_message, title=RenewSubscriptionUIText.SUCCESS_TITLE)
        self.accept()

    def _on_renewal_error(self, error: str) -> None:
        self._operation_in_progress = False
        self._set_loading(False)
        show_error(self, error or "No se pudo renovar la suscripción",
                   title=RenewSubscriptionUIText.ERROR_TITLE)

    def _validate_start_date_with_admin(self, form_data: Dict[str, Any]) -> str:
        """
        Valida fecha de inicio con rangos de tolerancia.

        Rangos:
        - -7 a +30 días: permitido sin restricción
        - -30 a -8 días: requiere contraseña de administrador
        - Fuera de rango: rechazar

        Returns:
            "approved": validación exitosa, continuar
            "cancel": usuario canceló
            "invalid": validación fallida
        """
        start_at = form_data.get("start_at")
        if not isinstance(start_at, datetime):
            return "approved"

        today = date.today()
        start_date = start_at.date()
        days_difference = (start_date - today).days

        # RANGO 1: -7 a +30 días (permitido sin contraseña)
        if -7 <= days_difference <= 30:
            logger.info(f"Fecha en rango normal: {days_difference} días de diferencia")
            return "approved"

        # RANGO 2: -30 a -8 días (requiere contraseña de administrador)
        if -30 <= days_difference <= -8:
            logger.info(f"Fecha requiere autorización admin: {days_difference} días de diferencia")

            # Mostrar mensaje explicativo
            msg = (
                f"La fecha seleccionada es {abs(days_difference)} días anterior a hoy.\n\n"
                f"Para proceder con esta fecha se requiere autorización de administrador."
            )
            show_info(self, msg, title="Autorización requerida")

            # Solicitar contraseña
            dialog = AdminPasswordDialog(self)
            dialog.setWindowTitle("Autorización de Administrador")

            if dialog.exec() != QDialog.DialogCode.Accepted:
                logger.info("Usuario canceló la autorización admin")
                return "cancel"

            admin_password = getattr(dialog, "password", "")
            if not admin_password:
                show_warning(self, "La contraseña de administrador es obligatoria", title="Error")
                return "invalid"

            # TODO: Validar contraseña con el backend si existe endpoint
            # Por ahora, aceptar cualquier contraseña no vacía como válida
            logger.info("Contraseña de administrador proporcionada, autorización aprobada")
            return "approved"

        # RANGO 3: Fuera de rangos permitidos
        if days_difference < -30:
            msg = (
                f"La fecha seleccionada es demasiado antigua ({abs(days_difference)} días atrás).\n\n"
                f"No se permiten renovaciones con más de 30 días de antigüedad.\n"
                f"Rango permitido: {(today - timedelta(days=30)).isoformat()} a {(today + timedelta(days=30)).isoformat()}"
            )
        else:  # days_difference > 30
            msg = (
                f"La fecha seleccionada es demasiado futura ({days_difference} días adelante).\n\n"
                f"No se permiten renovaciones con más de 30 días de anticipación.\n"
                f"Rango permitido: {(today - timedelta(days=30)).isoformat()} a {(today + timedelta(days=30)).isoformat()}"
            )

        show_error(self, msg, title="Fecha no válida")
        logger.warning(f"Fecha rechazada: {days_difference} días de diferencia")
        return "invalid"

    def _collect_form(self) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("🔍 _collect_form() EJECUTÁNDOSE - VERSIÓN CON FIXES")
        logger.info("=" * 60)

        plan = self.plan_combo.currentData()
        if not isinstance(plan, MembershipPlan):
            raise ValueError("Plan inválido")

        # Convert date to datetime preserving la zona horaria local
        start_date = self._selected_start_date()
        start_at = self._build_start_at(start_date)

        form_data = {
            "member_id": int(self.member_id),
            "plan_id": int(plan.id),
            "start_at": start_at,  # Changed from start_date to start_at
            "payment_method": self.payment_combo.currentData(),
            "amount": float(self.amount_input.value()),
        }

        # Include template_id if a class is selected
        selection = self._current_item()
        logger.info(f"🔍 selected_item = {selection} (type: {type(selection).__name__ if selection else 'None'})")
        self._append_template_and_seat(form_data, start_date)

        # Include seat_id if a seat is selected
        selected_seat = self.seat_combo.currentData()
        if isinstance(selected_seat, Seat):
            logger.info(f"Selected seat with id: {selected_seat.id}")

        # Debug logging
        logger.info(f"Collected form data from renewal dialog:")
        for key, value in form_data.items():
            if hasattr(value, 'isoformat'):
                logger.info(f"  {key}: {value.isoformat()} (type: {type(value).__name__})")
            else:
                logger.info(f"  {key}: {value} (type: {type(value).__name__})")

        return form_data

    def closeEvent(self, event) -> None:
        self.controller.cleanup()
        super().closeEvent(event)


class QDateEditWithToday(QDateEdit):
    """QDateEdit con calendario emergente."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Enable calendar popup
        self.setCalendarPopup(True)

        # Set current date as default
        self.setDate(QDate.currentDate())

        # Allow backdating up to 30 days (admin password required for -30 to -8 days)
        self.setMinimumDate(QDate.currentDate().addDays(-30))

        # Allow future dates up to 30 days
        self.setMaximumDate(QDate.currentDate().addDays(30))

        # Enable editing and make sure it's focusable
        self.setReadOnly(False)
        self.setEnabled(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Improve styling for better visibility of the dropdown button
        self.setStyleSheet("""
            QDateEdit {
                padding: 4px;
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #cccccc;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                background-color: #f0f0f0;
            }
            QDateEdit::drop-down:hover {
                background-color: #e0e0e0;
            }
            QDateEdit::down-arrow {
                width: 10px;
                height: 10px;
            }
        """)

        # Add debug logging
        logger.info("QDateEditWithToday initialized with calendar popup enabled")
