"""Base controller for subscription operations with shared functionality."""

from abc import abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, List

from PySide6.QtCore import QObject, Signal, Slot

from ..core.logging import get_logger
from ..models.base import ClassTemplate, MembershipPlan, Seat, TimeslotGroup
from ..services.subscription_service import SubscriptionService
from .base_controller import BaseController

logger = get_logger(__name__)


class BaseSubscriptionController(BaseController):
    """
    Abstract base controller for subscription operations.
    Provides common functionality for both new subscriptions and renewals.
    """

    # Common signals that all subscription controllers should have
    plans_loaded = Signal(list)
    plans_error = Signal(str)
    class_templates_loaded = Signal(list)
    class_templates_error = Signal(str)
    seats_loaded = Signal(list)
    seats_error = Signal(str)

    def __init__(
        self,
        members_service: Any,
        standing_bookings_service: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.members_service = members_service
        self.standing_bookings_service = standing_bookings_service

        # Shared subscription service
        self.subscription_service = SubscriptionService(
            members_service=members_service,
            standing_bookings_service=standing_bookings_service,
            parent=self
        )

        # Connect service signals to controller signals
        self._connect_service_signals()

        # Cache for quick access
        self._cached_plans: List[MembershipPlan] = []
        self._cached_templates: List[ClassTemplate] = []

        # Track last seat resolution to guard against stale selections
        self._last_selection_resolution: Optional[tuple[int, date]] = None

    def _connect_service_signals(self) -> None:
        """Connect subscription service signals to controller signals."""
        self.subscription_service.plans_loaded.connect(self._on_plans_loaded)
        self.subscription_service.plans_error.connect(self._on_plans_error)
        self.subscription_service.class_templates_loaded.connect(self._on_templates_loaded)
        self.subscription_service.class_templates_error.connect(self._on_templates_error)
        self.subscription_service.seats_loaded.connect(self._on_seats_loaded)
        self.subscription_service.seats_error.connect(self._on_seats_error)

    # ---------------------------
    # Common Loading Methods
    # ---------------------------
    def load_membership_plans(self, force_refresh: bool = False) -> None:
        """Load membership plans using the shared service."""
        logger.info("Loading membership plans via shared service")
        self.subscription_service.load_membership_plans(force_refresh=force_refresh)

    def load_class_templates(self, force_refresh: bool = False) -> None:
        """Load class templates using the shared service."""
        logger.info("Loading class templates via shared service")
        self.subscription_service.load_class_templates(force_refresh=force_refresh)

    def refresh_seats(self, template_id: Optional[int], date_to_check: Optional[date] = None) -> None:
        """Load available seats for a specific template and date."""
        if template_id is None:
            self.seats_loaded.emit([])
            return

        # Use the shared service to calculate proper date based on template weekday
        template = self.subscription_service.find_template_by_id(template_id)
        if template:
            base_date = date_to_check or date.today()
            weekday = getattr(template, "weekday", None)

            if isinstance(weekday, int):
                # Calculate first occurrence on or after base_date
                check_date = self.subscription_service.next_occurrence_on_or_after(base_date, weekday)
            else:
                check_date = base_date

            logger.info(f"Refreshing seats for template {template_id} on {check_date}")
        else:
            check_date = date_to_check or date.today()
            logger.warning(f"Template {template_id} not found in cache, using base date {check_date}")

        self._last_selection_resolution = (int(template_id), check_date) if template_id is not None else None
        self.subscription_service.load_available_seats(template_id, check_date)

    def refresh_seats_for_selection(self, selection: Any, target_date: date) -> None:
        """Resolve the selection against cached templates and reload seats."""
        template, occurrence = self.subscription_service.resolve_template_for_selection(selection, target_date)
        if not template or occurrence is None:
            self._last_selection_resolution = None
            self.seats_loaded.emit([])
            return

        self._last_selection_resolution = (int(template.id), occurrence)
        self.subscription_service.load_available_seats(template.id, occurrence)

    def resolve_template_for_selection(self, selection: Any, target_date: date) -> tuple[Optional[ClassTemplate], Optional[date]]:
        """Expose shared template resolution for dialogs."""
        return self.subscription_service.resolve_template_for_selection(selection, target_date)

    def ensure_seat_available(self, selection: Any, target_date: date, seat_id: int) -> tuple[bool, Optional[str]]:
        """Check last availability snapshot to avoid overlapping bookings."""
        template, occurrence = self.subscription_service.resolve_template_for_selection(selection, target_date)
        if not template or occurrence is None:
            return False, "Selecciona una clase válida antes de elegir un lugar."

        availability = self.subscription_service.is_seat_available(int(template.id), occurrence, int(seat_id))
        if availability is None:
            self.refresh_seats_for_selection(selection, target_date)
            return False, "Actualizando la disponibilidad del lugar, intenta nuevamente."
        if not availability:
            return False, "El lugar seleccionado ya está ocupado para la fecha elegida."
        return True, None

    # ---------------------------
    # Common Validation
    # ---------------------------
    def validate_form_data(self, form_data: Dict[str, Any]) -> Optional[str]:
        """
        Validate common form data fields.
        Subclasses can override this to add specific validations.
        """
        # Use shared validation from service
        error = self.subscription_service.validate_basic_form_data(form_data)
        if error:
            return error

        # Additional validations that subclasses can implement
        return self._validate_specific_fields(form_data)

    @abstractmethod
    def _validate_specific_fields(self, form_data: Dict[str, Any]) -> Optional[str]:
        """
        Validate fields specific to the controller type.
        Must be implemented by subclasses.
        """
        pass

    # ---------------------------
    # Common Utility Methods
    # ---------------------------
    def find_template_by_id(self, template_id: int) -> Optional[ClassTemplate]:
        """Find a template by ID in the cached data."""
        return self.subscription_service.find_template_by_id(template_id)

    def get_suggested_start_date(self, current_membership_end: Optional[datetime] = None) -> datetime:
        """
        Calculate suggested start date for subscription.

        Args:
            current_membership_end: End date of current membership (for renewals)

        Returns:
            Suggested start date
        """
        if current_membership_end:
            # For renewals: start the day after current membership ends
            next_day = current_membership_end + timedelta(days=1)
            return next_day.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # For new subscriptions: start today
            return datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

    def suggest_plan_by_name(self, plan_name: Optional[str]) -> Optional[MembershipPlan]:
        """Find a plan by name in the cached plans."""
        if not plan_name:
            return None

        for plan in self._cached_plans:
            if plan.name == plan_name:
                return plan
        return None

    def suggest_template_by_id(self, template_id: Optional[int]) -> Optional[ClassTemplate]:
        """Find a template by ID in the cached templates."""
        if template_id is None:
            return None

        for template in self._cached_templates:
            if template.id == template_id:
                return template
        return None

    # ---------------------------
    # Cache Management
    # ---------------------------
    def get_cache_status(self) -> Dict[str, Any]:
        """Get cache status for debugging."""
        return self.subscription_service.get_cache_status()

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.subscription_service.clear_cache()
        self._cached_plans.clear()
        self._cached_templates.clear()

    # ---------------------------
    # Event Handlers
    # ---------------------------
    @Slot(list)
    def _on_plans_loaded(self, plans: List[MembershipPlan]) -> None:
        """Handle successful plans loading."""
        self._cached_plans = plans
        self.plans_loaded.emit(plans)

    @Slot(str)
    def _on_plans_error(self, error: str) -> None:
        """Handle plans loading error."""
        self.plans_error.emit(error)

    @Slot(list)
    def _on_templates_loaded(self, templates: List[ClassTemplate]) -> None:
        """Handle successful templates loading."""
        self._cached_templates = templates
        self.class_templates_loaded.emit(templates)

    @Slot(str)
    def _on_templates_error(self, error: str) -> None:
        """Handle templates loading error."""
        self.class_templates_error.emit(error)

    @Slot(list)
    def _on_seats_loaded(self, seats: List[Seat]) -> None:
        """Handle successful seats loading."""
        self.seats_loaded.emit(seats)

    @Slot(str)
    def _on_seats_error(self, error: str) -> None:
        """Handle seats loading error."""
        self.seats_error.emit(error)

    # ---------------------------
    # Abstract Methods
    # ---------------------------
    @abstractmethod
    def create_subscription_operation(self, form_data: Dict[str, Any]) -> None:
        """
        Create the main subscription operation.
        Must be implemented by subclasses.
        """
        pass

    # ---------------------------
    # Cleanup
    # ---------------------------
    def cleanup(self) -> None:
        """Clean up resources and cancel any ongoing operations."""
        try:
            if self.subscription_service:
                self.subscription_service.cleanup()

            self._cached_plans.clear()
            self._cached_templates.clear()
            self._last_selection_resolution = None

            logger.info(f"{self.__class__.__name__} cleaned up")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
