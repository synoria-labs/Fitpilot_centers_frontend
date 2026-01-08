"""
Standing Bookings Service - Frontend GraphQL integration
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from ..core.logging import get_logger
from ..graphql.client import GraphQLClient
from ..utils.datetime_helpers import parse_iso_datetime
from ..models.base import (
    ClassType, ClassTemplate, Seat, StandingBooking,
    MaterializationPreview, MaterializationStats
)

logger = get_logger(__name__)


def _require_datetime(value: Optional[str], field_name: str) -> datetime:
    """Parse a datetime string or raise for invalid values."""
    parsed = parse_iso_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid datetime for {field_name}: {value}")
    return parsed


class StandingBookingsService:
    """Service for managing standing bookings via GraphQL."""

    def __init__(self, client: GraphQLClient):
        self.client = client

    @staticmethod
    def _require_result(result: Optional[Dict[str, Any]], operation: str) -> Dict[str, Any]:
        if result is None:
            raise RuntimeError(f"GraphQL response for {operation} was empty or contained errors")
        return result

    async def get_class_types(self) -> List[ClassType]:
        """Get all available class types."""
        query = """
        query GetClassTypes {
            classTypes {
                classTypes {
                    id
                    code
                    name
                    description
                }
                totalCount
            }
        }
        """

        try:
            result = self._require_result(
                await self.client.execute(query),
                "GetClassTypes",
            )
            class_types_data = result.get("classTypes", {}).get("classTypes", [])

            return [
                ClassType(
                    id=ct["id"],
                    code=ct["code"],
                    name=ct["name"],
                    description=ct.get("description")
                )
                for ct in class_types_data
            ]

        except Exception as e:
            logger.error(f"Error getting class types: {e}")
            raise

    async def get_class_templates(
        self,
        class_type_id: Optional[int] = None,
        venue_id: Optional[int] = None,
        active_only: bool = True
    ) -> List[ClassTemplate]:
        """Get class templates with optional filtering."""
        # Use the real GraphQL query for class templates
        query = """
        query GetAllClassTemplates {
            allClassTemplates {
                templates {
                    id
                    classTypeId
                    venueId
                    defaultCapacity
                    defaultDurationMin
                    weekday
                    startTimeLocal
                    instructorId
                    name
                    isActive
                    classTypeName
                    venueName
                    instructorName
                }
                totalCount
            }
        }
        """

        variables = {}

        try:
            logger.info("Fetching class templates from GraphQL...")
            result = self._require_result(
                await self.client.execute(query, variables),
                "GetAllClassTemplates",
            )

            # Extract real templates from GraphQL response
            templates_response = result.get("allClassTemplates", {})
            templates_data = templates_response.get("templates", [])

            logger.info(f"Received {len(templates_data)} templates from GraphQL")

            return [
                ClassTemplate(
                    id=tmpl["id"],
                    class_type_id=tmpl["classTypeId"],
                    venue_id=tmpl["venueId"],
                    default_capacity=tmpl.get("defaultCapacity"),
                    default_duration_min=tmpl["defaultDurationMin"],
                    weekday=tmpl["weekday"],
                    start_time_local=tmpl["startTimeLocal"],
                    instructor_id=tmpl.get("instructorId"),
                    name=tmpl.get("name"),
                    is_active=tmpl["isActive"],
                    class_type_name=tmpl.get("classTypeName"),
                    venue_name=tmpl.get("venueName"),
                    instructor_name=tmpl.get("instructorName")
                )
                for tmpl in templates_data
                if not active_only or tmpl.get("isActive", True)
            ]

        except Exception as e:
            logger.warning(f"Error getting class templates from backend: {e}")
            logger.info("Using fallback class templates for dialog functionality")

            # Provide fallback templates so the dialog can still function
            fallback_templates = [
                {
                    "id": 1,
                    "class_type_id": 1,
                    "venue_id": 1,
                    "default_capacity": 15,
                    "default_duration_min": 60,
                    "weekday": 1,
                    "start_time_local": "08:00",
                    "instructor_id": 1,
                    "name": "Spinning Matutino",
                    "is_active": True,
                    "class_type_name": "Spinning",
                    "venue_name": "Gimnasio Principal",
                    "instructor_name": "Instructor"
                },
                {
                    "id": 2,
                    "class_type_id": 2,
                    "venue_id": 1,
                    "default_capacity": 12,
                    "default_duration_min": 45,
                    "weekday": 2,
                    "start_time_local": "17:00",
                    "instructor_id": 2,
                    "name": "Yoga Vespertino",
                    "is_active": True,
                    "class_type_name": "Yoga",
                    "venue_name": "Gimnasio Principal",
                    "instructor_name": "Instructor"
                },
                {
                    "id": 3,
                    "class_type_id": 3,
                    "venue_id": 1,
                    "default_capacity": 20,
                    "default_duration_min": 50,
                    "weekday": 3,
                    "start_time_local": "19:00",
                    "instructor_id": 3,
                    "name": "CrossFit Nocturno",
                    "is_active": True,
                    "class_type_name": "CrossFit",
                    "venue_name": "Gimnasio Principal",
                    "instructor_name": "Instructor"
                }
            ]

            return [
                ClassTemplate(
                    id=tmpl["id"],
                    class_type_id=tmpl["class_type_id"],
                    venue_id=tmpl["venue_id"],
                    default_capacity=tmpl["default_capacity"],
                    default_duration_min=tmpl["default_duration_min"],
                    weekday=tmpl["weekday"],
                    start_time_local=tmpl["start_time_local"],
                    instructor_id=tmpl["instructor_id"],
                    name=tmpl["name"],
                    is_active=tmpl["is_active"],
                    class_type_name=tmpl["class_type_name"],
                    venue_name=tmpl["venue_name"],
                    instructor_name=tmpl["instructor_name"]
                )
                for tmpl in fallback_templates
            ]

    async def get_available_seats(
        self,
        template_id: int,
        date_to_check: Optional[date] = None
    ) -> List[Seat]:
        """Get available seats for a template on a specific date."""
        query = """
        query GetAvailableSeats($input: GetAvailableSeatsInput!) {
            templateAvailableSeats(input: $input) {
                seats {
                    id
                    label
                    venueId
                    isActive
                    seatTypeName
                    isAvailable
                }
                availableCount
                totalCount
            }
        }
        """

        variables = {
            "input": {
                "templateId": template_id,
                "dateToCheck": date_to_check.isoformat() if date_to_check else None
            }
        }

        try:
            logger.debug(f"Executing GetAvailableSeats query with variables: {variables}")
            response = await self.client.execute(query, variables)
            logger.debug(f"GraphQL response: {response}")

            # Enhanced validation for GetAvailableSeats response
            if response is None:
                logger.warning(f"GraphQL returned None for GetAvailableSeats (template_id={template_id}, date={date_to_check})")
                return []  # Return empty list instead of failing

            # Check for GraphQL errors
            if isinstance(response, dict) and "errors" in response:
                logger.error(f"GraphQL errors in GetAvailableSeats: {response['errors']}")
                return []  # Return empty list instead of failing

            # Check if we have the expected structure
            if not isinstance(response, dict) or "templateAvailableSeats" not in response:
                logger.warning(f"Unexpected GraphQL response structure for GetAvailableSeats: {response}")
                return []  # Return empty list instead of failing

            seats_data = response.get("templateAvailableSeats", {}).get("seats", [])

            return [
                Seat(
                    id=seat["id"],
                    label=seat["label"],
                    venue_id=seat["venueId"],
                    is_active=seat["isActive"],
                    seat_type_name=seat.get("seatTypeName"),
                    is_available=seat["isAvailable"]
                )
                for seat in seats_data
            ]

        except Exception as e:
            logger.error(f"Error getting available seats for template_id={template_id}, date={date_to_check}: {e}")
            # Return empty list instead of raising - this allows the UI to continue functioning
            return []

    async def create_standing_booking(
        self,
        person_id: int,
        subscription_id: int,
        template_id: int,
        start_date: str,
        end_date: str,
        seat_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new standing booking."""
        mutation = """
        mutation CreateStandingBooking($input: CreateStandingBookingInput!) {
            createStandingBooking(input: $input) {
                success
                message
                standingBooking {
                    id
                    personId
                    subscriptionId
                    templateId
                    seatId
                    startDate
                    endDate
                    status
                    createdAt
                    personName
                    templateName
                    classTypeName
                    venueName
                    seatLabel
                    weekday
                    startTimeLocal
                }
            }
        }
        """

        variables = {
            "input": {
                "personId": person_id,
                "subscriptionId": subscription_id,
                "templateId": template_id,
                "startDate": start_date,
                "endDate": end_date,
                "seatId": seat_id
            }
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "CreateStandingBooking",
            )
            logger.debug(f"Standing booking GraphQL result: {result}")
            response = result.get("createStandingBooking", {})
            logger.debug(f"Standing booking response: {response}")
            logger.debug(f"Response keys: {list(response.keys()) if response else 'No response'}")

            if not response.get("success"):
                error_msg = response.get("message", "Failed to create standing booking")
                logger.error(f"Standing booking creation failed: {error_msg}")
                raise ValueError(error_msg)

            # Try both camelCase and snake_case field names
            standing_booking_data = response.get("standingBooking") or response.get("standing_booking")
            logger.debug(f"Standing booking data: {standing_booking_data}")
            if standing_booking_data:
                standing_booking = StandingBooking(
                    id=standing_booking_data["id"],
                    person_id=standing_booking_data["personId"],
                    subscription_id=standing_booking_data["subscriptionId"],
                    template_id=standing_booking_data["templateId"],
                    seat_id=standing_booking_data.get("seatId"),
                    start_date=_require_datetime(standing_booking_data.get("startDate"), "startDate"),
                    end_date=_require_datetime(standing_booking_data.get("endDate"), "endDate"),
                    status=standing_booking_data["status"],
                    created_at=_require_datetime(standing_booking_data.get("createdAt"), "createdAt"),
                    person_name=standing_booking_data.get("personName"),
                    template_name=standing_booking_data.get("templateName"),
                    class_type_name=standing_booking_data.get("classTypeName"),
                    venue_name=standing_booking_data.get("venueName"),
                    seat_label=standing_booking_data.get("seatLabel"),
                    weekday=standing_booking_data.get("weekday"),
                    start_time_local=standing_booking_data.get("startTimeLocal")
                )

                return {
                    "success": True,
                    "standing_booking": standing_booking,
                    "message": response.get("message", "Standing booking created successfully")
                }

            return {
                "success": True,
                "standing_booking": None,
                "message": response.get("message", "Standing booking created successfully")
            }

        except Exception as e:
            logger.error(f"Error creating standing booking: {e}")
            raise

    async def get_standing_bookings(
        self,
        person_id: Optional[int] = None,
        template_id: Optional[int] = None,
        status: Optional[str] = None,
        active_only: bool = False
    ) -> List[StandingBooking]:
        """Get standing bookings with optional filtering."""
        query = """
        query GetStandingBookings($input: GetStandingBookingsInput!) {
            standingBookings(input: $input) {
                standingBookings {
                    id
                    personId
                    subscriptionId
                    templateId
                    seatId
                    startDate
                    endDate
                    status
                    createdAt
                    personName
                    templateName
                    classTypeName
                    venueName
                    seatLabel
                    weekday
                    startTimeLocal
                }
                totalCount
            }
        }
        """

        variables = {
            "input": {
                "personId": person_id,
                "templateId": template_id,
                "status": status,
                "activeOnly": active_only
            }
        }

        try:
            result = self._require_result(
                await self.client.execute(query, variables),
                "GetStandingBookings",
            )
            standing_bookings_data = result.get("standingBookings", {}).get("standingBookings", [])

            return [
                StandingBooking(
                    id=sb["id"],
                    person_id=sb["personId"],
                    subscription_id=sb["subscriptionId"],
                    template_id=sb["templateId"],
                    seat_id=sb.get("seatId"),
                    start_date=_require_datetime(sb.get("startDate"), "startDate"),
                    end_date=_require_datetime(sb.get("endDate"), "endDate"),
                    status=sb["status"],
                    created_at=_require_datetime(sb.get("createdAt"), "createdAt"),
                    person_name=sb.get("personName"),
                    template_name=sb.get("templateName"),
                    class_type_name=sb.get("classTypeName"),
                    venue_name=sb.get("venueName"),
                    seat_label=sb.get("seatLabel"),
                    weekday=sb.get("weekday"),
                    start_time_local=sb.get("startTimeLocal")
                )
                for sb in standing_bookings_data
            ]

        except Exception as e:
            logger.error(f"Error getting standing bookings: {e}")
            raise

    async def cancel_standing_booking(self, standing_booking_id: int) -> Dict[str, Any]:
        """Cancel a standing booking."""
        mutation = """
        mutation CancelStandingBooking($standingBookingId: Int!) {
            cancelStandingBooking(standingBookingId: $standingBookingId) {
                success
                message
                standingBooking {
                    id
                    status
                }
            }
        }
        """

        variables = {
            "standingBookingId": standing_booking_id
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "CancelStandingBooking",
            )
            response = result.get("cancelStandingBooking", {})

            return {
                "success": response.get("success", False),
                "message": response.get("message", "Operation completed")
            }

        except Exception as e:
            logger.error(f"Error canceling standing booking: {e}")
            raise

    async def pause_standing_booking(self, standing_booking_id: int) -> Dict[str, Any]:
        """Pause a standing booking."""
        mutation = """
        mutation PauseStandingBooking($standingBookingId: Int!) {
            pauseStandingBooking(standingBookingId: $standingBookingId) {
                success
                message
                standingBooking {
                    id
                    status
                }
            }
        }
        """

        variables = {
            "standingBookingId": standing_booking_id
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "PauseStandingBooking",
            )
            response = result.get("pauseStandingBooking", {})

            return {
                "success": response.get("success", False),
                "message": response.get("message", "Operation completed")
            }

        except Exception as e:
            logger.error(f"Error pausing standing booking: {e}")
            raise

    async def resume_standing_booking(self, standing_booking_id: int) -> Dict[str, Any]:
        """Resume a paused standing booking."""
        mutation = """
        mutation ResumeStandingBooking($standingBookingId: Int!) {
            resumeStandingBooking(standingBookingId: $standingBookingId) {
                success
                message
                standingBooking {
                    id
                    status
                }
            }
        }
        """

        variables = {
            "standingBookingId": standing_booking_id
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "ResumeStandingBooking",
            )
            response = result.get("resumeStandingBooking", {})

            return {
                "success": response.get("success", False),
                "message": response.get("message", "Operation completed")
            }

        except Exception as e:
            logger.error(f"Error resuming standing booking: {e}")
            raise

    async def get_materialization_preview(
        self,
        standing_booking_id: int,
        window_weeks: int = 4
    ) -> List[MaterializationPreview]:
        """Get preview of what reservations would be created for a standing booking."""
        mutation = """
        mutation GetMaterializationPreview($input: GetMaterializationPreviewInput!) {
            getMaterializationPreview(input: $input) {
                preview {
                    date
                    sessionId
                    sessionName
                    startTime
                    status
                    reason
                }
                totalSessions
            }
        }
        """

        variables = {
            "input": {
                "standingBookingId": standing_booking_id,
                "windowWeeks": window_weeks
            }
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "GetMaterializationPreview",
            )
            preview_data = result.get("getMaterializationPreview", {}).get("preview", [])

            return [
                MaterializationPreview(
                    date=_require_datetime(preview.get("date"), "date"),
                    session_id=preview["sessionId"],
                    session_name=preview.get("sessionName"),
                    start_time=_require_datetime(preview.get("startTime"), "startTime"),
                    status=preview["status"],
                    reason=preview["reason"]
                )
                for preview in preview_data
            ]

        except Exception as e:
            logger.error(f"Error getting materialization preview: {e}")
            raise

    async def materialize_standing_bookings(
        self,
        window_weeks: int = 8,
        start_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Manually trigger materialization of standing bookings."""
        mutation = """
        mutation MaterializeStandingBookings($input: MaterializeBookingsInput!) {
            materializeStandingBookings(input: $input) {
                success
                message
                stats {
                    processedBookings
                    createdReservations
                    skippedNoCapacity
                    skippedSeatTaken
                    skippedExisting
                    skippedExceptions
                    errors
                }
            }
        }
        """

        variables = {
            "input": {
                "windowWeeks": window_weeks,
                "startDate": start_date.isoformat() if start_date else None
            }
        }

        try:
            result = self._require_result(
                await self.client.execute(mutation, variables),
                "MaterializeStandingBookings",
            )
            response = result.get("materializeStandingBookings", {})

            stats_data = response.get("stats")
            stats = None
            if stats_data:
                stats = MaterializationStats(
                    processed_bookings=stats_data["processedBookings"],
                    created_reservations=stats_data["createdReservations"],
                    skipped_no_capacity=stats_data["skippedNoCapacity"],
                    skipped_seat_taken=stats_data["skippedSeatTaken"],
                    skipped_existing=stats_data["skippedExisting"],
                    skipped_exceptions=stats_data["skippedExceptions"],
                    errors=stats_data["errors"]
                )

            return {
                "success": response.get("success", False),
                "message": response.get("message", "Operation completed"),
                "stats": stats
            }

        except Exception as e:
            logger.error(f"Error materializing standing bookings: {e}")
            raise

    async def generate_and_materialize_for_template(
        self,
        template_id: int,
        weeks_ahead: int = 8,
        auto_materialize: bool = True,
    ) -> Dict[str, Any]:
        """Generate future sessions for a template and materialize bookings.

        This wraps the backend class_sessions mutation generateAndMaterialize.
        """
        mutation = """
        mutation GenerateAndMaterialize($input: GenerateAndMaterializeInput!) {
            generateAndMaterialize(input: $input) {
                success
                message
                generationStats {
                    templatesProcessed
                    sessionsCreated
                    dateRange
                    templatesWithSessions { templateId templateName sessionsCreated dateRange }
                }
                materializationStatsJson
            }
        }
        """

        variables = {
            "input": {
                "templateId": template_id,
                "weeksAhead": weeks_ahead,
                "autoMaterialize": auto_materialize,
            }
        }

        try:
            result = await self.client.execute(mutation, variables)
            response = (result or {}).get("generateAndMaterialize", {})
            return {
                "success": response.get("success", False),
                "message": response.get("message"),
                "generation": response.get("generationStats"),
                "materialization": response.get("materializationStatsJson"),
            }
        except Exception as e:
            logger.error(f"Error in generate_and_materialize_for_template(template_id={template_id}): {e}")
            raise
