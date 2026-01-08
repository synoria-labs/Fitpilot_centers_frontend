"""Refactored new subscription dialog:
- Weekday NO es input, se calcula primera ocurrencia a partir de start_date + weekday del template.
- Se recargan asientos cuando cambia la fecha o la clase.
- Inherits shared logic from BaseSubscriptionDialog
"""

from typing import Any, Dict
import json

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ...core.logging import get_logger
from ...models.base import Seat
from ...controllers.new_subscription_controller import NewSubscriptionController as Controller
from ...utils.qt_helpers import configure_amount_input, populate_payment_methods
from .base_subscription_dialog import BaseSubscriptionDialog, AMOUNT_MAXIMUM
from ...utils.dialog_helpers import show_error, show_info, show_warning

logger = get_logger(__name__)


class NewSubscriptionUIText:
    WINDOW_TITLE = "Registrar nueva membresía"
    GROUP_TITLE = "Datos de registro"
    NAME_LABEL = "Nombre"
    EMAIL_LABEL = "Correo electrónico"
    WHATSAPP_LABEL = "WhatsApp"
    PLAN_LABEL = "Plan"
    CLASS_LABEL = "Clase (horario fijo)"
    START_DATE_LABEL = "Fecha de inicio"
    PAYMENT_METHOD_LABEL = "Método de pago"
    AMOUNT_LABEL = "Monto"
    ACCEPT_TEXT = "Registrar"
    CANCEL_TEXT = "Cancelar"

    NO_PLANS_WARNING = "No se encontraron planes de membresía."
    NO_CLASSES_WARNING = "No se encontraron clases."
    NO_SEATS_WARNING = "Sin lugares disponibles en la fecha seleccionada."
    CREATION_ERROR = "No se pudo completar el registro."
    CONFIRMATION_TITLE = "Registro completado"
    ENROLLMENT_SUCCESS = "Inscripción creada exitosamente."
    BOOKING_SUCCESS = "Reserva fija creada exitosamente."
    CREATING_BOOKING_TEXT = "Creando reserva"
    ERROR_TITLE = "Error"


class NewSubscriptionDialog(BaseSubscriptionDialog):
    def __init__(
        self,
        controller: Controller,
        parent=None,
    ) -> None:
        self.controller = controller
        super().__init__(parent)

        self.setWindowTitle(NewSubscriptionUIText.WINDOW_TITLE)
        self.setModal(True)
        self.setMinimumWidth(560)

        self._build_ui()
        self._connect_signals()

        # Dispara carga asíncrona leve para no congelar UI
        QTimer.singleShot(100, self._initial_load)

    # ---------------------------
    # UI Building
    # ---------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.register_group = QGroupBox(NewSubscriptionUIText.GROUP_TITLE)
        form = QFormLayout(self.register_group)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        # Basic data
        self.name_input = QLineEdit()
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("ejemplo@correo.com")
        self.whatsapp_input = QLineEdit()
        self.whatsapp_input.setPlaceholderText("5512345678")
        form.addRow(NewSubscriptionUIText.NAME_LABEL, self.name_input)
        form.addRow(NewSubscriptionUIText.EMAIL_LABEL, self.email_input)
        form.addRow(NewSubscriptionUIText.WHATSAPP_LABEL, self.whatsapp_input)

        # Plan
        self.plan_combo = QComboBox()
        form.addRow(NewSubscriptionUIText.PLAN_LABEL, self.plan_combo)

        # Start date
        self.start_date = QDateEdit(QDate.currentDate())
        self.start_date.setCalendarPopup(True)
        form.addRow(NewSubscriptionUIText.START_DATE_LABEL, self.start_date)

        # Class (horario fijo)
        self.class_combo = QComboBox()
        form.addRow(NewSubscriptionUIText.CLASS_LABEL, self.class_combo)

        # Asiento (solo visible si la clase lo requiere)
        self.seat_label = QLabel("Lugar")
        self.seat_combo = QComboBox()
        self.seat_label.setVisible(False)
        self.seat_combo.setVisible(False)
        self.seat_combo.setEnabled(False)
        form.addRow(self.seat_label, self.seat_combo)

        # Pago
        self.payment_method = QComboBox()
        populate_payment_methods(self.payment_method)
        form.addRow(NewSubscriptionUIText.PAYMENT_METHOD_LABEL, self.payment_method)

        self.amount_input = QDoubleSpinBox()
        configure_amount_input(self.amount_input, AMOUNT_MAXIMUM)
        form.addRow(NewSubscriptionUIText.AMOUNT_LABEL, self.amount_input)

        layout.addWidget(self.register_group)

        # Botones
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.accept_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.accept_button.setText(NewSubscriptionUIText.ACCEPT_TEXT)
        self.cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText(NewSubscriptionUIText.CANCEL_TEXT)
        layout.addWidget(self.button_box)

    def _connect_signals(self) -> None:
        # Botones
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        # Combos y fecha - use base class handlers
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        self.start_date.dateChanged.connect(self._on_date_changed)

        # Controller signals - use base class handlers where possible
        self.controller.plans_loaded.connect(self._on_plans_loaded)
        self.controller.plans_error.connect(self._on_plans_error)

        # Use timeslot groups instead of individual templates
        if hasattr(self.controller.subscription_service, 'timeslot_groups_loaded'):
            self.controller.subscription_service.timeslot_groups_loaded.connect(self._on_timeslot_groups_loaded)

        self.controller.class_templates_error.connect(self._on_class_templates_error)
        self.controller.seats_loaded.connect(self._on_seats_loaded)
        self.controller.seats_error.connect(self._on_seats_error)
        self.controller.enrollment_success.connect(self._on_enrollment_success)
        self.controller.enrollment_error.connect(self._on_enrollment_error)

    def _initial_load(self) -> None:
        """Load initial data for the dialog."""
        self.controller.load_membership_plans()
        if hasattr(self.controller, 'load_class_templates'):
            self.controller.load_class_templates()

    # ---------------------------
    # Error handlers (specific text for this dialog)
    # ---------------------------
    def _on_plans_error(self, error: str) -> None:
        show_error(self, error or "No se pudieron cargar los planes",
                   title=NewSubscriptionUIText.ERROR_TITLE)

    def _on_class_templates_error(self, error: str) -> None:
        show_error(self, error or "No se pudieron cargar las clases",
                   title=NewSubscriptionUIText.ERROR_TITLE)

    # ---------------------------
    # Success handlers
    # ---------------------------
    def _on_enrollment_success(self, result: Dict[str, Any]) -> None:
        """
        Muestra un mensaje de confirmación amigable cuando la inscripción
        se realiza con éxito. Si el backend envía JSON embebido en el mensaje,
        se parsea para enriquecer la notificación.
        """
        raw_msg = (result or {}).get("message") or NewSubscriptionUIText.ENROLLMENT_SUCCESS
        msg = self._format_enrollment_message(raw_msg)
        show_info(self, msg, title=NewSubscriptionUIText.CONFIRMATION_TITLE)
        self._set_accept_enabled(True, NewSubscriptionUIText.ACCEPT_TEXT)  # type: ignore[attr-defined]
        super().accept()

    def _on_enrollment_error(self, error: str) -> None:
        self._set_accept_enabled(True, NewSubscriptionUIText.ACCEPT_TEXT)  # type: ignore[attr-defined]
        show_error(self, error or NewSubscriptionUIText.CREATION_ERROR,
                   title=NewSubscriptionUIText.ERROR_TITLE)

    # ---------------------------
    # Form submission
    # ---------------------------
    def _on_accept(self) -> None:
        """
        Prepara form_data y llama a controller.create_enrollment(form_data).
        """
        form_data = self._collect_form()
        if not form_data:
            return

        # Validate seat availability if selected
        selection = self.class_combo.currentData()
        sel_seat = self.seat_combo.currentData()
        if isinstance(sel_seat, Seat):
            start_d = self._selected_start_date()
            ok, message = self.controller.ensure_seat_available(selection, start_d, sel_seat.id)
            if not ok:
                self._set_accept_enabled(True, NewSubscriptionUIText.ACCEPT_TEXT)  # type: ignore[attr-defined]
                show_warning(self, message or "Lugar no disponible.",
                             title=NewSubscriptionUIText.ERROR_TITLE)
                self.controller.refresh_seats_for_selection(selection, start_d)
                return

        # Soft validation
        err = self.controller.validate_form_data(form_data)
        if err:
            show_warning(self, err or "Revisa los datos del formulario.",
                         title=NewSubscriptionUIText.ERROR_TITLE)
            return

        self._set_accept_enabled(False, "Creando")  # type: ignore[attr-defined]
        self.controller.create_enrollment(form_data)

    def _collect_form(self) -> Dict[str, Any]:
        """Collect form data for submission."""
        from ...models.base import MembershipPlan

        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        whatsapp = self.whatsapp_input.text().strip()
        plan = self.plan_combo.currentData()

        if not isinstance(plan, MembershipPlan):
            show_warning(self, "Selecciona un plan válido",
                         title=NewSubscriptionUIText.ERROR_TITLE)
            return {}

        start_d = self._selected_start_date()
        sub_start_at = self._build_start_at(start_d)

        # Match the backend schema: CreateMemberEnrollmentInput (flat structure)
        form_data: Dict[str, Any] = {
            # Person fields
            "full_name": name or None,
            "email": email or None,
            "phone_number": whatsapp or None,  # WhatsApp goes to phone_number
            # Subscription fields
            "plan_id": int(plan.id),
            "start_at": sub_start_at,
            # Payment fields
            "payment_method": self.payment_method.currentData(),
            "payment_amount": float(self.amount_input.value()),
            "payment_status": "COMPLETED",
        }

        # Include class template and seat if selected
        self._append_template_and_seat(form_data, start_d)

        return form_data

    # ---------------------------
    # Helpers
    # ---------------------------
    
    @staticmethod
    def _format_enrollment_message(raw_msg: str) -> str:
        """
        Intenta extraer un bloque JSON del mensaje (si existe) y construir
        un texto de confirmación más detallado. En caso de fallo, devuelve
        un mensaje simple y claro.
        """
        default_msg = "✓ Membresía registrada exitosamente"

        data: Dict[str, Any] = {}
        try:
            if "{" in raw_msg and "}" in raw_msg:
                json_start = raw_msg.index("{")
                json_part = raw_msg[json_start:]
                data = json.loads(json_part)
        except (json.JSONDecodeError, ValueError):
            data = {}

        if isinstance(data, dict) and data:
            parts = [default_msg]

            member = data.get("member", {}) or {}
            if member.get("full_name"):
                parts.append(f"Socio: {member['full_name']}")

            sub = data.get("subscription", {}) or {}
            if sub.get("plan_name"):
                parts.append(f"Plan: {sub['plan_name']}")

            sb = data.get("standing_booking", {}) or {}
            if sb.get("count"):
                parts.append(f"✓ {sb['count']} reserva(s) fija(s) creada(s)")

            mat = data.get("materialization", {}) or {}
            if mat.get("sessions_created"):
                parts.append(f"✓ {mat['sessions_created']} sesión(es) programada(s)")

            msg = "\n".join(parts)
            if len(parts) == 1 and raw_msg != NewSubscriptionUIText.ENROLLMENT_SUCCESS:
                return raw_msg
            return msg

        if raw_msg and raw_msg != NewSubscriptionUIText.ENROLLMENT_SUCCESS:
            return raw_msg

        return default_msg

    def _set_accept_enabled(self, enabled: bool, label: str) -> None:
        self.accept_button.setEnabled(enabled)
        self.accept_button.setText(label)

    # ---------------------------
    # Life cycle
    # ---------------------------
    def closeEvent(self, event) -> None:
        self.controller.cleanup()
        super().closeEvent(event)
