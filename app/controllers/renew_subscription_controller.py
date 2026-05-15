"""Controller for handling subscription renewal logic."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, QTimer, Slot

from ..core.logging import get_logger
from ..models.base import ClassTemplate, MembershipPlan
from ..threads.authenticated_operations import AuthenticatedOperation
from .base_subscription_controller import BaseSubscriptionController

logger = get_logger(__name__)

class RenewSubscriptionController(BaseSubscriptionController):
    """Controller that orchestrates renewal data loading for the dialog."""

    # Additional signals specific to renewals
    member_data_loaded = Signal(dict)
    member_data_error = Signal(str)
    renewal_success = Signal(dict)
    renewal_error = Signal(str)

    def __init__(
        self,
        members_service: Any,
        standing_bookings_service: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(members_service, standing_bookings_service, parent)
        # Separate operation trackers for different operation types
        self._renewal_operation: Optional[AuthenticatedOperation] = None
        self._current_operation: Optional[AuthenticatedOperation] = None  # For data loading operations

        # Member-specific data for renewals
        self._member_data: Optional[Dict[str, Any]] = None

        # Group booking tracking
        self._group_booking_results: Optional[Dict[str, Any]] = None
        self._post_ops: Optional[list] = None

    # Note: load_membership_plans and load_class_templates now inherited from BaseSubscriptionController

    def load_member_data(self, member_id: int) -> None:
        """Load current member data including active subscription."""
        if not self.members_service:
            self.member_data_error.emit("Servicio no disponible")
            return

        try:
            self._current_operation = self._execute_authenticated_operation(
                self.members_service,
                "get_member_by_id",
                self._on_member_data_loaded,
                self._on_member_data_error,
                track=False,  # We track manually in _current_operation
                member_id=member_id,
            )
        except Exception as e:
            logger.error(f"Error loading member data: {e}")
            self.member_data_error.emit("No se pudieron cargar los datos del miembro")

    # Note: load_available_seats functionality now provided by refresh_seats from BaseSubscriptionController

    def renew_subscription(self, form_data: Dict[str, Any]) -> None:
        """Create subscription renewal using real backend service."""
        logger.info(f"Renewing subscription with form data keys: {list(form_data.keys())}")

        # Log the actual field types and values (safely)
        for key, value in form_data.items():
            if key in ['start_at', 'end_at'] and hasattr(value, 'isoformat'):
                logger.info(f"  {key}: {value.isoformat()} (type: {type(value).__name__})")
            else:
                logger.info(f"  {key}: {value} (type: {type(value).__name__})")

        if not self.members_service:
            logger.error("Members service is not available")
            self.renewal_error.emit("Servicio de miembros no disponible")
            return

        try:
            # Prevent duplicate renewal operations - use dedicated renewal_operation tracker
            if self._renewal_operation:
                logger.warning("Renewal operation already in progress - rejecting duplicate request")
                self.renewal_error.emit("Ya existe una operación de renovación en progreso")
                return

            # Transform form data to match backend service parameters
            service_params = self._transform_form_data_for_service(form_data)
            logger.info(f"Transformed service parameters: {list(service_params.keys())}")

            # Create renewal operation using the real members service
            logger.info("Creating renewal operation with MembersService.renew_subscription")
            self._renewal_operation = self._execute_authenticated_operation(
                self.members_service,
                "renew_subscription",
                self._on_renewal_operation_success,
                self._on_renewal_operation_error,
                track=False,  # We track manually in _renewal_operation
                **service_params
            )

        except Exception as e:
            logger.error(f"Error creating renewal operation: {e}")
            self._renewal_operation = None
            self.renewal_error.emit(f"Error al crear la operación de renovación: {str(e)}")

    @Slot(dict)
    def _on_renewal_operation_success(self, result: Dict[str, Any]) -> None:
        """Handle renewal response from backend and enforce success contract."""
        result = result or {}
        logger.info(
            "Renewal operation result received. Keys: %s",
            list(result.keys()) if result else [],
        )

        success = bool(result.get("success"))
        subscription = result.get("subscription")
        payment = result.get("payment")
        has_entities = bool(subscription and payment)

        if not success or not has_entities:
            error_message = self._build_renewal_failure_message(result)
            logger.warning(
                "Renewal rejected as failure. success=%s has_entities=%s error=%s",
                success,
                has_entities,
                error_message,
            )
            self._renewal_operation = None
            self.renewal_error.emit(error_message)
            return

        sub_id = subscription.get('id') if isinstance(subscription, dict) else getattr(subscription, 'id', 'Unknown')
        logger.info("New subscription created with ID: %s", sub_id)

        self._renewal_operation = None
        self.renewal_success.emit(result)

    def _build_renewal_failure_message(self, result: Dict[str, Any]) -> str:
        """Build a user-facing error message from normalized renewal payload."""
        if not isinstance(result, dict):
            return "No se pudo renovar la suscripcion."

        cause = str(result.get("error_cause") or "").strip()
        message = str(result.get("message") or "").strip()
        error_code = str(result.get("error_code") or "").strip().upper()

        if not cause:
            if error_code == "NO_AVAILABILITY":
                cause = "Falta de disponibilidad"
            elif error_code == "MISSING_TEMPLATE":
                cause = "Falta seleccionar horario"
            elif error_code == "NETWORK_ERROR":
                cause = "Error de comunicacion con el servidor"

        if cause and message:
            if cause.lower() in message.lower():
                return message
            return f"{cause}. {message}"

        if cause:
            return f"{cause}."

        if message:
            return message

        return "No se pudo renovar la suscripcion."

    @Slot(str)
    def _on_renewal_operation_error(self, error: str) -> None:
        """Handle renewal operation error from backend."""
        logger.error(f"Renewal operation failed with error: {error}")

        # Provide more specific error messages based on common issues
        if "unexpected keyword argument" in error:
            enhanced_error = f"Error de parámetros en la renovación: {error}. Verifique la configuración del backend."
        elif "authentication" in error.lower() or "token" in error.lower():
            enhanced_error = "Error de autenticación. Por favor, inicie sesión nuevamente."
        elif "connection" in error.lower() or "network" in error.lower():
            enhanced_error = "Error de conexión con el servidor. Verifique su conexión a internet."
        else:
            enhanced_error = f"Error en la renovación: {error}"

        self._renewal_operation = None
        self.renewal_error.emit(enhanced_error)

    def load_defaults(self, member_id: int, member_name: Optional[str] = None, member_data: Optional[Any] = None) -> None:
        """Load all data needed for renewal dialog (optimized approach)."""
        logger.info("Loading renewal data for member_id=%s, name=%s", member_id, member_name)

        # Load member data immediately
        self._emit_member_data(member_id, member_name, member_data)

        # Load cached data first if available, then real data
        self._load_data_intelligently(member_id)

    def _emit_member_data(self, member_id: int, member_name: Optional[str] = None, member_data: Optional[Any] = None) -> None:
        """Emit member data immediately."""
        logger.info("Emitting member data")

        # Use real member data if available, otherwise fallback
        if member_data:
            processed_member_data = self._extract_member_info(member_data, member_id, member_name)
        else:
            processed_member_data = {
                'id': member_id,
                'full_name': member_name or f'Miembro #{member_id}',
                'active_membership': {
                    'plan_name': 'Plan Actual',
                    'end_date': None,
                    'status': 'active'
                }
            }
        self.member_data_loaded.emit(processed_member_data)

    def _load_data_intelligently(self, member_id: int) -> None:
        """Load data using cached data first, then real data only if needed."""
        logger.info("Loading data intelligently with cache optimization")

        # Check if we have cached data that's still valid
        cache_status = self.get_cache_status()
        has_valid_cache = cache_status.get("status") == "active" and not cache_status.get("expired", True)

        if has_valid_cache:
            logger.info("Using cached data for faster loading")
            # Emit cached plans immediately
            cached_plans = self.subscription_service.get_cached_plans()
            if cached_plans:
                self.plans_loaded.emit(cached_plans)

            # Emit cached templates immediately
            cached_templates = self.subscription_service.get_cached_templates()
            if cached_templates:
                self.class_templates_loaded.emit(cached_templates)
        else:
            logger.info("No valid cache, loading fresh data")
            # Load fresh data - this will automatically cache it
            self.load_membership_plans()
            if self.standing_bookings_service:
                self.load_class_templates()

        # Always try to load real member data in background
        QTimer.singleShot(50, lambda: self._load_member_data_background(member_id))

    def _extract_member_info(self, member_data: Any, member_id: int, member_name: Optional[str] = None) -> Dict[str, Any]:
        """Extract member information from various data formats."""
        try:
            # Handle different data formats from the table
            if isinstance(member_data, dict):
                # Already a dictionary
                full_name = member_data.get('full_name') or member_data.get('name') or member_name or f'Miembro #{member_id}'
                active_membership = member_data.get('active_membership', {})
                active_standing_booking = member_data.get('active_standing_booking', {})
            elif hasattr(member_data, '__dict__'):
                # Object with attributes
                full_name = getattr(member_data, 'full_name', None) or getattr(member_data, 'name', None) or member_name or f'Miembro #{member_id}'
                active_membership = getattr(member_data, 'active_membership', {})
                active_standing_booking = getattr(member_data, 'active_standing_booking', {})
            else:
                # Fallback for unknown format
                full_name = member_name or f'Miembro #{member_id}'
                active_membership = {}
                active_standing_booking = {}

            # Extract class information from standing booking if available
            class_template_id = None
            class_name = None
            if isinstance(active_standing_booking, dict) and active_standing_booking:
                class_template_id = active_standing_booking.get('template_id')
                template_name = active_standing_booking.get('template_name')
                class_type_name = active_standing_booking.get('class_type_name')
                start_time = active_standing_booking.get('start_time_local')

                # Build a descriptive class name
                if template_name:
                    class_name = template_name
                elif class_type_name and start_time:
                    class_name = f"{class_type_name} {start_time}"
                elif class_type_name:
                    class_name = class_type_name

            # Ensure active_membership is a dict with enhanced data
            if not isinstance(active_membership, dict):
                if hasattr(active_membership, '__dict__'):
                    active_membership = {
                        'plan_name': getattr(active_membership, 'plan_name', 'Plan Actual'),
                        'end_date': getattr(active_membership, 'end_date', None),
                        'status': getattr(active_membership, 'status', 'active'),
                        'payment_amount': getattr(active_membership, 'payment_amount', 0),
                        'class_template_id': class_template_id,
                        'class_name': class_name,
                    }
                else:
                    active_membership = {
                        'plan_name': 'Plan Actual',
                        'end_date': None,
                        'status': 'active',
                        'payment_amount': 0,
                        'class_template_id': class_template_id,
                        'class_name': class_name,
                    }
            else:
                # Ensure required fields exist in dictionary and use real class data
                active_membership.setdefault('payment_amount', active_membership.get('price', 0))
                active_membership['class_template_id'] = class_template_id or active_membership.get('class_template_id')
                active_membership['class_name'] = class_name or active_membership.get('class_name')

            return {
                'id': member_id,
                'full_name': full_name,
                'active_membership': active_membership
            }

        except Exception as e:
            logger.error(f"Error extracting member info for member_id={member_id}: {e}")
            logger.info(f"Member data type: {type(member_data)}, data sample: {str(member_data)[:200]}...")

            # Return safe fallback with more info
            return {
                'id': member_id,
                'full_name': member_name or f'Miembro #{member_id}',
                'active_membership': {
                    'plan_name': 'Plan Actual (error en datos)',
                    'end_date': None,
                    'status': 'active',
                    'error': str(e)
                }
            }

    def _load_member_data_background(self, member_id: int) -> None:
        """Load real member data in background without duplicating other data loads."""
        logger.info("Loading member data in background")

        try:
            self.load_member_data(member_id)
        except Exception as e:
            logger.warning(f"Background member data loading failed: {e}")

    # Note: Plans, templates, and seats event handlers now inherited from BaseSubscriptionController

    @Slot(dict)
    def _on_member_data_loaded(self, member_data: Dict[str, Any]) -> None:
        """Handle successful member data loading."""
        logger.info("Member data loaded for renewal")

        # Process the raw backend data through _extract_member_info
        member_id = member_data.get('id', 0)
        processed_member_data = self._extract_member_info(member_data, member_id)

        logger.info(f"Processed member data: full_name={processed_member_data.get('full_name')}")

        # Extract active standing booking data directly from member_data
        active_standing_booking = member_data.get('active_standing_booking', {})
        logger.info(f"Active standing booking data: {active_standing_booking}")

        # Format data in the structure expected by the dialog
        dialog_payload = {
            "member": {
                "id": processed_member_data.get('id'),
                "full_name": processed_member_data.get('full_name')
            },
            "active_membership": processed_member_data.get('active_membership', {}),
            "active_booking": active_standing_booking  # Include the actual standing booking data
        }

        self._member_data = dialog_payload
        self.member_data_loaded.emit(dialog_payload)

    @Slot(str)
    def _on_member_data_error(self, error: str) -> None:
        """Handle member data loading error."""
        logger.error(f"Failed to load member data: {error}")
        self.member_data_error.emit(error)

    @Slot(dict)
    def _on_renewal_success(self, result: Dict[str, Any]) -> None:
        """Handle successful renewal."""
        logger.info("Subscription renewed successfully")
        self.renewal_success.emit(result)

    @Slot(str)
    def _on_renewal_error(self, error: str) -> None:
        """Handle renewal error."""
        logger.error(f"Failed to renew subscription: {error}")
        self.renewal_error.emit(error)

    def get_suggested_start_date(self) -> datetime:
        """Calculate suggested start date based on current membership."""
        if self._member_data and self._member_data.get('active_membership'):
            membership = self._member_data['active_membership']
            if hasattr(membership, 'end_date') and membership.end_date:
                return membership.end_date
            elif isinstance(membership, dict) and membership.get('end_date'):
                return membership['end_date']

        # Fallback to current date
        return datetime.now(timezone.utc)

    # Note: refresh_seats now inherited from BaseSubscriptionController with improved logic

    def _validate_specific_fields(self, form_data: Dict[str, Any]) -> Optional[str]:
        """Validate fields specific to renewal operations."""
        try:
            # Debug logging
            logger.info(f"Validating renewal fields. Form data keys: {list(form_data.keys())}")
            for key, value in form_data.items():
                if hasattr(value, 'isoformat'):
                    logger.info(f"  {key}: {value.isoformat()} (type: {type(value).__name__})")
                else:
                    logger.info(f"  {key}: {value} (type: {type(value).__name__})")

            # Check required fields for renewals
            if not form_data.get("member_id"):
                logger.warning("Validation failed: missing member_id")
                return "ID de miembro requerido"

            if not form_data.get("plan_id"):
                logger.warning("Validation failed: missing plan_id")
                return "Plan de membresía requerido"

            start_at = form_data.get("start_at")
            if not start_at:
                logger.warning("Validation failed: missing or empty start_at field")
                return "Fecha de inicio requerida"

            logger.info("Renewal validation passed successfully")
            return None  # Valid
        except Exception as e:
            logger.error(f"Error validating renewal-specific fields: {e}")
            return "Error de validación"

    def _transform_form_data_for_service(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform frontend form data to match backend service parameters."""
        try:
            # Map frontend field names to backend service parameter names
            service_params = {}

            # Required fields mapping
            if 'member_id' in form_data:
                service_params['member_id'] = form_data['member_id']
            if 'plan_id' in form_data:
                service_params['plan_id'] = form_data['plan_id']
            if 'start_at' in form_data:
                service_params['start_at'] = form_data['start_at']
            if 'payment_method' in form_data:
                service_params['payment_method'] = form_data['payment_method']

            # Map 'amount' to 'payment_amount' (this is the critical fix)
            if 'amount' in form_data:
                service_params['payment_amount'] = form_data['amount']
                logger.info(f"Mapped 'amount' ({form_data['amount']}) to 'payment_amount'")

            # Handle template_id: prioritize form_data, fallback to member data
            if 'template_id' in form_data and form_data['template_id']:
                # User explicitly selected a template in the dialog
                service_params['template_id'] = form_data['template_id']
                logger.info(f"Using template_id from form: {form_data['template_id']}")
            else:
                # Fallback: try to extract from member's existing standing booking data
                template_id = None
                if self._member_data:
                    # First try to get template_id from active_standing_booking
                    active_booking = self._member_data.get('active_booking')
                    if active_booking:
                        template_id = active_booking.get('template_id')
                        logger.info(f"Fallback: using template_id from active_booking: {template_id}")

                    # Fallback to check active_membership for class_template_id (legacy data)
                    if not template_id:
                        active_membership = self._member_data.get('active_membership')
                        if active_membership:
                            template_id = active_membership.get('class_template_id')
                            logger.info(f"Fallback: using template_id from active_membership: {template_id}")

                if template_id:
                    service_params['template_id'] = template_id
                else:
                    logger.info("No template_id provided - renewal will be without standing booking")

            # Handle seat_id from form data
            if 'seat_id' in form_data and form_data['seat_id']:
                service_params['seat_id'] = form_data['seat_id']
                logger.info(f"Using seat_id from form: {form_data['seat_id']}")

            # Optional fields with defaults
            service_params['payment_status'] = form_data.get('payment_status', 'COMPLETED')
            service_params['payment_comment'] = form_data.get('payment_comment', None)
            service_params['payment_provider'] = form_data.get('payment_provider', None)
            service_params['provider_payment_id'] = form_data.get('provider_payment_id', None)
            service_params['external_reference'] = form_data.get('external_reference', None)

            logger.info(f"Form data transformation completed. Original keys: {list(form_data.keys())}")
            logger.info(f"Service params keys: {list(service_params.keys())}")

            return service_params

        except Exception as e:
            logger.error(f"Error transforming form data: {e}")
            # In case of error, return original data and let the service handle the error
            return form_data

    def create_subscription_operation(self, form_data: Dict[str, Any]) -> None:
        """Create the renewal subscription operation."""
        self.renew_subscription(form_data)

    def cleanup(self) -> None:
        """Clean up resources and cancel any ongoing operations."""
        try:
            # Cancel renewal-specific operations
            if self._current_operation:
                self._current_operation = None

            # Clear renewal-specific data
            self._member_data = None
            # Clear group booking state
            self._group_booking_results = None

            # Call parent cleanup for shared resources
            super().cleanup()

            logger.info("RenewSubscriptionController cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
