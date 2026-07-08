"""Shared subscription service for common operations between renewal and new subscription dialogs."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from ..core.logging import get_logger
from ..models.base import ClassTemplate, MembershipPlan, Seat, TimeslotGroup
from ..threads.authenticated_operations import AuthenticatedOperation
from . import subscription_logic

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
        """Agrupa plantillas de clase por horario recurrente.

        Lógica pura extraída a ``subscription_logic``; este wrapper preserva la
        API ``SubscriptionService.build_timeslot_groups(...)``.
        """
        return subscription_logic.build_timeslot_groups(templates)

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
        """Encuentra el grupo que contiene una plantilla específica (ver subscription_logic)."""
        return subscription_logic.find_group_by_template_id(template_id, groups)

    # ---------------------------
    # Utility Methods
    # ---------------------------
    @staticmethod
    def next_occurrence_on_or_after(start_date: date, weekday_1_to_7: int) -> date:
        """Próxima ocurrencia del weekday en o después de start_date (ver subscription_logic)."""
        return subscription_logic.next_occurrence_on_or_after(start_date, weekday_1_to_7)

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
        """Valida campos comunes de formulario (ver subscription_logic)."""
        return subscription_logic.validate_basic_form_data(form_data)

    @staticmethod
    def validate_timeslot_group(group: TimeslotGroup) -> Optional[str]:
        """Valida un grupo de horario para reserva fija (ver subscription_logic)."""
        return subscription_logic.validate_timeslot_group(group)

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