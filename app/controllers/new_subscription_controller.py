"""Controller for handling new subscription business logic (refactor: asiento por fecha real según weekday)."""

from datetime import date, datetime, time
from typing import Any, Dict, Optional

from PySide6.QtCore import QDate, QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.base import (
    ClassTemplate,
    Member,
    MembershipSubscription,
    Payment,
    Seat,
)
from ..threads.authenticated_operations import AuthenticatedOperation
from .base_subscription_controller import BaseSubscriptionController

logger = get_logger(__name__)

class NewSubscriptionController(BaseSubscriptionController):
    """
    - Carga planes y plantillas de clase
    - Calcula la primera ocurrencia (fecha real) en base a start_date + weekday del template
    - Consulta lugares disponibles para esa fecha real
    - Crea la inscripción (miembro + suscripción + pago)
    - Crea el standing booking con el rango de la suscripción
    """

    # Additional signals specific to new subscriptions
    enrollment_success = Signal(dict)
    enrollment_error = Signal(str)

    def __init__(
        self,
        members_service: Any,
        standing_bookings_service: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(members_service, standing_bookings_service, parent)

        # Operaciones específicas de nuevas suscripciones
        self._current_operation: Optional[AuthenticatedOperation] = None

        # Entidades creadas tras enrollment
        self.created_member: Optional[Member] = None
        self.created_subscription: Optional[MembershipSubscription] = None
        self.created_payment: Optional[Payment] = None

    # ---------------------------
    # Utilidades (now using base class methods)
    # ---------------------------
    @staticmethod
    def _pydate(qdate: QDate) -> date:
        """Convierte QDate → date (naive)."""
        return date(qdate.year(), qdate.month(), qdate.day())

    @staticmethod
    def _to_utc_datetime(d: date) -> datetime:
        """date → datetime (00:00:00Z)."""
        local_tz = datetime.now().astimezone().tzinfo
        return datetime.combine(d, time.min, tzinfo=local_tz)

    # Note: _next_occurrence_on_or_after and _find_template now available via subscription_service

    # ---------------------------
    # Carga de datos (now inherited from BaseSubscriptionController)
    # ---------------------------
    # Note: load_membership_plans and load_class_templates now inherited from base class

    # ---------------------------
    # Lugares / Asientos (now inherited from BaseSubscriptionController)
    # ---------------------------
    # Note: refresh_seats now inherited from BaseSubscriptionController with improved caching and date calculation

    # ---------------------------
    # Creación de inscripción
    # ---------------------------
    def create_enrollment(self, form_data: Dict[str, Any]) -> None:
        """
        Crea inscripción completa (miembro + suscripción + pago).
        form_data: dict con datos limpios desde el dialog.
        """
        if not self.members_service:
            self.enrollment_error.emit("Servicio no disponible")
            return

        self._cancel_current_op()

        try:
            # form_data is now in flat format matching CreateMemberEnrollmentInput
            # Just pass through the fields directly
            service_kwargs: Dict[str, Any] = {
                "full_name": form_data.get("full_name"),
                "email": form_data.get("email"),
                "phone_number": form_data.get("phone_number"),
                "plan_id": form_data.get("plan_id"),
                "start_at": form_data.get("start_at"),
                "payment_method": form_data.get("payment_method"),
                "payment_amount": form_data.get("payment_amount"),
                "payment_status": form_data.get("payment_status", "COMPLETED"),
            }

            # Opcionales para que el backend cree standing bookings + sesiones como en renovacin
            if form_data.get("template_id") is not None:
                service_kwargs["template_id"] = form_data.get("template_id")
            if form_data.get("seat_id") is not None:
                service_kwargs["seat_id"] = form_data.get("seat_id")

            # Quick required check
            req = [
                ("full_name", service_kwargs.get("full_name")),
                ("plan_id", service_kwargs.get("plan_id")),
                ("start_at", service_kwargs.get("start_at")),
                ("payment_method", service_kwargs.get("payment_method")),
                ("payment_amount", service_kwargs.get("payment_amount")),
            ]
            missing = [k for k, v in req if v in (None, "")]
            if service_kwargs.get("payment_amount") in (None, 0, 0.0):
                if "payment_amount" not in missing:
                    missing.append("payment_amount")
            if missing:
                self.enrollment_error.emit(f"Faltan campos requeridos: {', '.join(missing)}")
                return

            # Flag: si enviamos template_id, el backend crea standing bookings/sesiones

            self._current_operation = self._execute_authenticated_operation(
                self.members_service,
                "create_member_enrollment",
                self._on_enrollment_success,
                self._on_enrollment_error,
                track=False,
                **service_kwargs
            )
        except Exception as e:
            logger.error(f"Error creating enrollment operation: {e}")
            self.enrollment_error.emit("No se pudo crear la inscripción")

    def _validate_specific_fields(self, form_data: Dict[str, Any]) -> Optional[str]:
        """
        Validate fields specific to new subscription enrollment.

        New subscriptions require full_name since we're creating a new member.
        All other validations (plan_id, amount, payment_method, dates) are
        handled by the shared validate_basic_form_data() in SubscriptionService.
        """
        try:
            # Validate full_name (specific to new subscriptions - creating new member)
            full_name = form_data.get("full_name", "").strip()
            if not full_name:
                return "Nombre completo requerido"

            if len(full_name) < 2:
                return "Nombre debe tener al menos 2 caracteres"

            return None  # Valid
        except Exception as e:
            logger.error(f"Validation error (new subscription specific fields): {e}")
            return "Error de validación"

    def create_subscription_operation(self, form_data: Dict[str, Any]) -> None:
        """Create the new subscription enrollment operation."""
        self.create_enrollment(form_data)

    def cleanup(self) -> None:
        """Cancela operaciones activas (llamar en closeEvent de la vista)."""
        try:
            # Cancel new subscription specific operations
            self._cancel_current_op()

            # Clear created entities
            self.created_member = None
            self.created_subscription = None
            self.created_payment = None
            self.created_standing_booking = None

            # Clear group booking state
            self._group_booking_results = None

            # Call parent cleanup for shared resources
            super().cleanup()

            logger.info("NewSubscriptionController cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    def _cancel_current_op(self) -> None:
        """Cancel current operation by disconnecting signals and clearing reference."""
        if self._current_operation:
            try:
                # Desconectar TODAS las señales de esta operación privada local
                # Es seguro usar disconnect() sin parámetros porque:
                # 1. La operación es privada (_current_operation)
                # 2. Solo este controlador conecta slots a estas señales
                # 3. Queremos cancelar TODOS los callbacks pendientes
                self._current_operation.success.disconnect()
                self._current_operation.error.disconnect()
                self._current_operation.finished.disconnect()
            except Exception:
                # Signals might not be connected, ignore errors
                pass
            # Clear the reference to allow garbage collection
            self._current_operation = None

    # ---------------------------
    # Handlers de señales (common ones now inherited from BaseSubscriptionController)
    # ---------------------------
    # Note: Plans, templates, and seats handlers now inherited from base class

    @Slot(dict)
    def _on_enrollment_success(self, result: Dict[str, Any]) -> None:
        """
        Espera un dict con llaves:
          - member
          - subscription
          - payment
        """
        self.created_member = result.get("member")
        self.created_subscription = result.get("subscription")
        self.created_payment = result.get("payment")
        self.enrollment_success.emit(result)

    @Slot(str)
    def _on_enrollment_error(self, error: str) -> None:
        self.enrollment_error.emit(error or "No se pudo crear la inscripción")

    @Slot(str)
    def _on_standing_booking_error(self, error: str) -> None:
        self.standing_booking_error.emit(error or "No se pudo crear la reserva fija")
