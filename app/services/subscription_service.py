"""Shared subscription service for common operations between renewal and new subscription dialogs."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from ..models.base import ClassTemplate, MembershipPlan, Seat, TimeslotGroup
from ..threads.authenticated_operations import AuthenticatedOperation

logger = get_logger(__name__)


@dataclass
class SubscriptionCache:
    """Cache for frequently accessed subscription data."""
    membership_plans: List[MembershipPlan]
    class_templates: List[ClassTemplate]
    last_updated: datetime
    ttl_minutes: int = 5  # Cache TTL in minutes

    def is_expired(self) -> bool:
        """Check if cache is expired."""
        return (datetime.now() - self.last_updated).total_seconds() > (self.ttl_minutes * 60)


class SubscriptionService(QObject):
    """
    Centralized service for subscription-related operations.
    Provides caching, deduplication, and common business logic.
    """

    # Shared signals for all subscription operations
    plans_loaded = Signal(list)
    plans_error = Signal(str)
    class_templates_loaded = Signal(list)
    class_templates_error = Signal(str)
    seats_loaded = Signal(list)
    seats_error = Signal(str)

    # New signals for grouped templates
    timeslot_groups_loaded = Signal(list)  # List[TimeslotGroup]

    def __init__(
        self,
        members_service: Any,
        standing_bookings_service: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.members_service = members_service
        self.standing_bookings_service = standing_bookings_service

        # Cache management
        self._cache: Optional[SubscriptionCache] = None

        # Operation tracking to prevent duplicates
        self._active_plans_operation: Optional[AuthenticatedOperation] = None
        self._active_templates_operation: Optional[AuthenticatedOperation] = None
        self._active_seats_operation: Optional[AuthenticatedOperation] = None

        # Last seat availability snapshot (template_id, date) -> seats
        self._last_seat_request: Optional[tuple[int, date]] = None
        self._last_seat_snapshot: Optional[List[Seat]] = None

    # ---------------------------
    # Membership Plans
    # ---------------------------
    def load_membership_plans(self, force_refresh: bool = False) -> None:
        """
        Load membership plans with intelligent caching.

        Args:
            force_refresh: Force refresh even if cache is valid
        """
        # Check cache first
        if not force_refresh and self._cache and not self._cache.is_expired():
            logger.info("Using cached membership plans")
            self.plans_loaded.emit(self._cache.membership_plans)
            return

        # Prevent duplicate operations
        if self._active_plans_operation:
            logger.info("Membership plans operation already in progress")
            return

        if not self.members_service:
            logger.error("Members service not available")
            self.plans_error.emit("Servicio no disponible")
            return

        logger.info("Loading membership plans from server...")

        try:
            self._active_plans_operation = AuthenticatedOperation(
                self.members_service, "get_membership_plans", self
            )
            self._active_plans_operation.success.connect(self._on_plans_loaded)
            self._active_plans_operation.error.connect(self._on_plans_error)
            self._active_plans_operation.execute()
        except Exception as e:
            logger.error(f"Error creating membership plans operation: {e}")
            self._active_plans_operation = None
            self.plans_error.emit("No se pudieron cargar los planes de membresía")

    # ---------------------------
    # Class Templates
    # ---------------------------
    def load_class_templates(self, force_refresh: bool = False) -> None:
        """
        Load class templates with intelligent caching.

        Args:
            force_refresh: Force refresh even if cache is valid
        """
        # Check cache first
        if not force_refresh and self._cache and not self._cache.is_expired():
            logger.info("Using cached class templates")
            self.class_templates_loaded.emit(self._cache.class_templates)
            return

        # Prevent duplicate operations
        if self._active_templates_operation:
            logger.info("Class templates operation already in progress")
            return

        if not self.standing_bookings_service:
            logger.warning("Standing bookings service not available")
            self.class_templates_loaded.emit([])
            return

        logger.info("Loading class templates from server...")

        try:
            self._active_templates_operation = AuthenticatedOperation(
                self.standing_bookings_service, "get_class_templates", self
            )
            self._active_templates_operation.success.connect(self._on_class_templates_loaded)
            self._active_templates_operation.error.connect(self._on_class_templates_error)
            self._active_templates_operation.execute()
        except Exception as e:
            logger.error(f"Error creating class templates operation: {e}")
            self._active_templates_operation = None
            self.class_templates_error.emit("No se pudieron cargar las clases disponibles")

    # ---------------------------
    # Seats Management
    # ---------------------------
    def load_available_seats(self, template_id: int, date_to_check: Optional[date] = None) -> None:
        """
        Load available seats for a specific template on a specific date.

        Args:
            template_id: ID of the class template
            date_to_check: Date to check availability, defaults to today
        """
        # Cancel any existing seats operation
        if self._active_seats_operation:
            try:
                # Desconectar TODAS las señales de esta operación privada local
                # Es seguro usar disconnect() sin parámetros porque:
                # 1. La operación es privada (_active_seats_operation)
                # 2. Solo este servicio conecta slots a estas señales
                # 3. Queremos cancelar TODOS los callbacks pendientes
                self._active_seats_operation.success.disconnect()
                self._active_seats_operation.error.disconnect()
            except Exception:
                pass
            self._active_seats_operation = None

        if not self.standing_bookings_service:
            self._last_seat_request = None
            self._last_seat_snapshot = None
            self.seats_error.emit("Servicio de reservas no disponible")
            return

        try:
            check_date = date_to_check if date_to_check else date.today()

            self._last_seat_request = (int(template_id), check_date)
            self._last_seat_snapshot = None

            logger.info(f"Loading seats for template {template_id} on {check_date}")

            self._active_seats_operation = AuthenticatedOperation(
                self.standing_bookings_service,
                "get_available_seats",
                self,
                template_id=template_id,
                date_to_check=check_date,
            )
            self._active_seats_operation.success.connect(self._on_seats_loaded)
            self._active_seats_operation.error.connect(self._on_seats_error)
            self._active_seats_operation.execute()
        except Exception as e:
            logger.error(f"Error creating seats loading operation: {e}")
            self._active_seats_operation = None
            self._last_seat_request = None
            self._last_seat_snapshot = None
            self.seats_error.emit("No se pudieron cargar los lugares")

    # ---------------------------
    # Template Grouping Methods
    # ---------------------------
    @staticmethod
    def build_timeslot_groups(templates: List[ClassTemplate]) -> List[TimeslotGroup]:
        """
        Agrupa plantillas de clase por horario recurrente.

        Args:
            templates: Lista de plantillas de clase

        Returns:
            Lista de grupos de horario ordenados por tipo → venue → hora
        """
        from hashlib import md5

        buckets: Dict[str, TimeslotGroup] = {}

        for template in templates:
            # Crear clave de agrupamiento basada en características comunes
            group_key = (
                template.class_type_id,
                template.venue_id,
                template.start_time_local,
                template.instructor_id
            )

            # Generar hash estable
            key_hash = md5(str(group_key).encode()).hexdigest()[:8]  # usar solo primeros 8 chars

            if key_hash not in buckets:
                buckets[key_hash] = TimeslotGroup(
                    key=key_hash,
                    class_type_name=getattr(template, 'class_type_name', '') or 'Clase',
                    venue_name=getattr(template, 'venue_name', '') or 'Venue',
                    instructor_name=getattr(template, 'instructor_name', None),
                    start_time_local=getattr(template, 'start_time_local', '') or '00:00',
                    template_ids=[],
                    templates=[]
                )

            # Agregar template al grupo
            buckets[key_hash].template_ids.append(template.id)
            buckets[key_hash].templates.append(template)

        # Ordenar grupos por tipo de clase → venue → hora
        groups = list(buckets.values())
        groups.sort(key=lambda g: (g.class_type_name, g.venue_name, g.start_time_local))

        logger.info(f"Created {len(groups)} timeslot groups from {len(templates)} templates")
        return groups

    def get_timeslot_groups(self, force_refresh: bool = False) -> List[TimeslotGroup]:
        """
        Obtiene grupos de horario basados en las plantillas en caché.

        Args:
            force_refresh: Forzar recarga de plantillas antes de agrupar

        Returns:
            Lista de grupos de horario
        """
        # Recargar plantillas si es necesario
        if force_refresh or not self._cache or self._cache.is_expired():
            logger.info("Cache expired, need fresh templates for grouping")
            return []  # Necesitaremos cargar plantillas primero

        templates = self._cache.class_templates
        if not templates:
            logger.warning("No templates available for grouping")
            return []

        return self.build_timeslot_groups(templates)

    def find_group_by_template_id(self, template_id: int, groups: List[TimeslotGroup]) -> Optional[TimeslotGroup]:
        """
        Encuentra el grupo que contiene una plantilla específica.

        Args:
            template_id: ID de la plantilla a buscar
            groups: Lista de grupos donde buscar

        Returns:
            Grupo que contiene la plantilla o None
        """
        for group in groups:
            if template_id in group.template_ids:
                return group
        return None

    # ---------------------------
    # Utility Methods
    # ---------------------------
    @staticmethod
    def next_occurrence_on_or_after(start_date: date, weekday_1_to_7: int) -> date:
        """
        Calculate the next occurrence of a weekday on or after a given date.

        Args:
            start_date: Starting date
            weekday_1_to_7: Target weekday (1=Monday, 7=Sunday)

        Returns:
            First date >= start_date that falls on the target weekday
        """
        # Python: Monday=0..Sunday=6  | Model: Monday=1..Sunday=7
        target = (weekday_1_to_7 - 1) % 7
        delta = (target - start_date.weekday()) % 7
        return start_date + timedelta(days=delta)

    def find_template_by_id(self, template_id: int) -> Optional[ClassTemplate]:
        """Find a class template by ID in the current cache."""
        if not self._cache:
            return None

        for template in self._cache.class_templates:
            if template.id == template_id:
                return template
        return None

    def resolve_template_for_selection(self, selection: Any, target_date: date) -> tuple[Optional[ClassTemplate], Optional[date]]:
        """Resolve a TimeslotGroup/ClassTemplate/int selection into a template and occurrence date."""
        template: Optional[ClassTemplate] = None

        if selection is None:
            return None, None

        if isinstance(selection, TimeslotGroup):
            template = selection.template_for_date(target_date)
            if template is None:
                template = selection.get_first_template()
            if template is None:
                for template_id in getattr(selection, "template_ids", []) or []:
                    candidate = self.find_template_by_id(int(template_id)) if template_id is not None else None
                    if candidate is None:
                        continue
                    template = candidate
                    if getattr(candidate, "weekday", None) == target_date.isoweekday():
                        break
        elif isinstance(selection, ClassTemplate):
            template = selection
        elif isinstance(selection, int):
            template = self.find_template_by_id(selection)
        else:
            candidate_id = getattr(selection, "id", None)
            if isinstance(candidate_id, int):
                template = self.find_template_by_id(candidate_id)

        if template is None:
            return None, None

        weekday = getattr(template, "weekday", None)
        if isinstance(weekday, int):
            occurrence = self.next_occurrence_on_or_after(target_date, weekday)
        else:
            occurrence = target_date
        return template, occurrence

    def is_seat_available(self, template_id: int, target_date: date, seat_id: int) -> Optional[bool]:
        """Return True/False if snapshot matches, None if it needs refresh."""
        if self._last_seat_request != (template_id, target_date):
            return None

        seats = self._last_seat_snapshot or []
        for seat in seats:
            if isinstance(seat, Seat):
                if seat.id == seat_id:
                    return bool(getattr(seat, "is_available", True))
            elif isinstance(seat, dict):
                candidate_id = seat.get("id") or seat.get("seatId")
                if candidate_id is not None and int(candidate_id) == seat_id:
                    value = seat.get("is_available")
                    if value is None:
                        value = seat.get("isAvailable")
                    if value is None:
                        value = seat.get("status") == "free"
                    return bool(value)
        return None

    def get_cached_plans(self) -> List[MembershipPlan]:
        """Get cached membership plans if available."""
        if self._cache and not self._cache.is_expired():
            return self._cache.membership_plans
        return []

    def get_cached_templates(self) -> List[ClassTemplate]:
        """Get cached class templates if available."""
        if self._cache and not self._cache.is_expired():
            return self._cache.class_templates
        return []

    # ---------------------------
    # Validation
    # ---------------------------
    @staticmethod
    def validate_basic_form_data(form_data: Dict[str, Any]) -> Optional[str]:
        """
        Validate common form data fields.

        Supports multiple field name formats for flexibility:
        - amount/payment_amount for payment amount
        - plan_id for membership plan

        Args:
            form_data: Form data dictionary

        Returns:
            Error message if validation fails, None if valid
        """
        try:
            # Check amount (support both 'amount' and 'payment_amount')
            amount = form_data.get("payment_amount") or form_data.get("amount", 0)
            if not isinstance(amount, (int, float)) or amount <= 0:
                return "Monto debe ser mayor a 0"

            # Check payment method
            payment_method = form_data.get("payment_method")
            if not payment_method:
                return "Método de pago requerido"

            # Validate payment method values
            valid_methods = ["cash", "card", "transfer", "other"]
            if payment_method not in valid_methods:
                return f"Método de pago inválido. Debe ser uno de: {', '.join(valid_methods)}"

            # Check plan_id if present
            plan_id = form_data.get("plan_id")
            if plan_id is not None and (not isinstance(plan_id, int) or plan_id <= 0):
                return "Plan de membresía inválido"

            # Check dates coherency if present (support multiple date field names)
            start_at = form_data.get("start_at") or form_data.get("start_date")
            end_at = form_data.get("end_at") or form_data.get("end_date")

            if isinstance(start_at, datetime) and isinstance(end_at, datetime):
                if end_at <= start_at:
                    return "La fecha fin debe ser posterior a la fecha de inicio"
            elif isinstance(start_at, date) and isinstance(end_at, date):
                if end_at <= start_at:
                    return "La fecha fin debe ser posterior a la fecha de inicio"

            # NOTE: Start date validation moved to RenewSubscriptionDialog._validate_start_date_with_admin()
            # This allows flexible date ranges with admin password authentication:
            # - -7 to +30 days: allowed without restriction
            # - -30 to -8 days: requires admin password
            # - outside range: rejected
            #
            # if start_at:
            #     if isinstance(start_at, datetime):
            #         if start_at.date() < date.today():
            #             return "La fecha de inicio no puede ser anterior a hoy"
            #     elif isinstance(start_at, date):
            #         if start_at < date.today():
            #             return "La fecha de inicio no puede ser anterior a hoy"

            # Additional validations for specific form types
            if "person" in form_data:
                error = SubscriptionService._validate_person_data(form_data["person"])
                if error:
                    return error

            if "subscription" in form_data:
                error = SubscriptionService._validate_subscription_data(form_data["subscription"])
                if error:
                    return error

            return None  # Valid
        except Exception as e:
            logger.error(f"Error validating form data: {e}")
            return "Error de validación"

    @staticmethod
    def _validate_person_data(person_data: Dict[str, Any]) -> Optional[str]:
        """Validate person data specifically."""
        full_name = person_data.get("full_name", "").strip()
        if not full_name:
            return "Nombre completo es requerido"

        if len(full_name) < 2:
            return "Nombre debe tener al menos 2 caracteres"

        # Optional: validate phone if provided
        phone = person_data.get("phone_number", "").strip()
        if phone and len(phone) < 8:
            return "Teléfono debe tener al menos 8 dígitos"

        return None

    @staticmethod
    def _validate_subscription_data(subscription_data: Dict[str, Any]) -> Optional[str]:
        """Validate subscription data specifically."""
        plan_id = subscription_data.get("plan_id")
        if not plan_id or not isinstance(plan_id, int) or plan_id <= 0:
            return "Plan de membresía requerido"

        start_at = subscription_data.get("start_at")
        end_at = subscription_data.get("end_at")

        if isinstance(start_at, datetime) and isinstance(end_at, datetime):
            if end_at <= start_at:
                return "Fecha de fin debe ser posterior a fecha de inicio"

        return None

    @staticmethod
    def validate_timeslot_group(group: TimeslotGroup) -> Optional[str]:
        """
        Validate a timeslot group for standing booking creation.

        Args:
            group: TimeslotGroup to validate

        Returns:
            Error message if validation fails, None if valid
        """
        if not group.template_ids:
            return "Grupo de horario no contiene plantillas válidas"

        if not group.class_type_name or not group.venue_name:
            return "Información de clase incompleta"

        if not group.start_time_local:
            return "Hora de inicio requerida"

        return None

    # ---------------------------
    # Cache Management
    # ---------------------------
    def clear_cache(self) -> None:
        """Clear all cached data."""
        logger.info("Clearing subscription service cache")
        self._cache = None

    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status information for debugging."""
        if not self._cache:
            return {"status": "empty"}

        return {
            "status": "active",
            "expired": self._cache.is_expired(),
            "plans_count": len(self._cache.membership_plans),
            "templates_count": len(self._cache.class_templates),
            "last_updated": self._cache.last_updated.isoformat(),
            "ttl_minutes": self._cache.ttl_minutes
        }

    # ---------------------------
    # Event Handlers
    # ---------------------------
    def _on_plans_loaded(self, plans: List[MembershipPlan]) -> None:
        """Handle successful plans loading."""
        logger.info(f"Loaded {len(plans)} membership plans")
        self._active_plans_operation = None

        # Update cache
        self._update_cache(membership_plans=plans)

        self.plans_loaded.emit(plans)

    def _on_plans_error(self, error: str) -> None:
        """Handle plans loading error."""
        logger.error(f"Failed to load membership plans: {error}")
        self._active_plans_operation = None
        self.plans_error.emit(error)

    def _on_class_templates_loaded(self, templates: List[ClassTemplate]) -> None:
        """Handle successful class templates loading."""
        logger.info(f"Loaded {len(templates)} class templates")
        self._active_templates_operation = None

        # Update cache
        self._update_cache(class_templates=templates)

        # Emit individual templates
        self.class_templates_loaded.emit(templates)

        # Create and emit timeslot groups
        groups = self.build_timeslot_groups(templates)
        self.timeslot_groups_loaded.emit(groups)

    def _on_class_templates_error(self, error: str) -> None:
        """Handle class templates loading error."""
        logger.error(f"Failed to load class templates: {error}")
        self._active_templates_operation = None
        self.class_templates_error.emit(error)

    def _on_seats_loaded(self, seats: List[Seat]) -> None:
        """Handle successful seats loading."""
        logger.info(f"Loaded {len(seats)} available seats")
        self._active_seats_operation = None
        self._last_seat_snapshot = seats
        self.seats_loaded.emit(seats)

    def _on_seats_error(self, error: str) -> None:
        """Handle seats loading error."""
        logger.error(f"Failed to load seats: {error}")
        self._active_seats_operation = None
        self._last_seat_request = None
        self._last_seat_snapshot = None
        self.seats_error.emit(error)

    def _update_cache(self, membership_plans: Optional[List[MembershipPlan]] = None,
                     class_templates: Optional[List[ClassTemplate]] = None) -> None:
        """Update cache with new data."""
        if not self._cache:
            self._cache = SubscriptionCache(
                membership_plans=membership_plans or [],
                class_templates=class_templates or [],
                last_updated=datetime.now()
            )
        else:
            # Update existing cache
            if membership_plans is not None:
                self._cache.membership_plans = membership_plans
            if class_templates is not None:
                self._cache.class_templates = class_templates
            self._cache.last_updated = datetime.now()

    # ---------------------------
    # Cleanup
    # ---------------------------
    def cleanup(self) -> None:
        """Clean up resources and cancel any ongoing operations."""
        try:
            # Cancel active operations
            for operation in [self._active_plans_operation, self._active_templates_operation, self._active_seats_operation]:
                if operation:
                    try:
                        # Desconectar TODAS las señales de operaciones privadas locales
                        # Es seguro usar disconnect() sin parámetros porque:
                        # 1. Las operaciones son privadas (_active_*_operation)
                        # 2. Solo este servicio conecta slots a estas señales
                        # 3. Queremos cancelar TODOS los callbacks pendientes en cleanup
                        operation.success.disconnect()
                        operation.error.disconnect()
                    except Exception:
                        pass

            self._active_plans_operation = None
            self._active_templates_operation = None
            self._active_seats_operation = None

            # Clear cache
            self.clear_cache()

            logger.info("SubscriptionService cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")