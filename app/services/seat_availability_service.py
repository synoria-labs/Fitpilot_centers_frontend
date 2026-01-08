"""Shared seat availability utilities bridging classes and standing bookings flows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional, Dict, Any

from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SeatAvailability:
    """Normalized seat availability information returned by the backend shared helper."""

    id: int
    label: str
    venue_id: Optional[int]
    is_active: bool
    is_available: bool
    status: str = "free"
    occupant_name: Optional[str] = None
    occupant_id: Optional[int] = None

    def to_frontend_dict(self) -> Dict[str, Any]:
        """Return dict representation compatible with existing widgets/dialogs."""
        return {
            "id": self.id,
            "label": self.label,
            "venue_id": self.venue_id,
            "is_active": self.is_active,
            "is_available": self.is_available,
            "status": self.status,
            "occupant": {
                "personId": self.occupant_id,
                "fullName": self.occupant_name,
            } if self.occupant_name else None,
        }


class SeatAvailabilityService:
    """Adapter around classes/standing bookings GraphQL endpoints to provide seat status."""

    def __init__(self, classes_service, standing_bookings_service):
        self._classes_service = classes_service
        self._standing_bookings_service = standing_bookings_service

    async def seats_for_template_date(
        self,
        *,
        template_id: int,
        target_date: date,
    ) -> List[SeatAvailability]:
        """Return seat availability for a template on a specific date.

        Preferred path:
            - Use sessionsWithSeats (classes_service) so we get actual seat status per session.
            - Fallback to templateAvailableSeats if the session does not exist yet.
        """
        seats = await self._fetch_seats_from_classes_service(template_id, target_date)
        if seats:
            return seats

        logger.info(
            "Seats not found via classes service for template %s on %s; falling back to standing bookings API",
            template_id,
            target_date,
        )
        return await self._fallback_standing_bookings(template_id, target_date)

    async def _fetch_seats_from_classes_service(
        self,
        template_id: int,
        target_date: date,
    ) -> List[SeatAvailability]:
        if not self._classes_service:
            logger.debug("ClassesService not available, skipping primary seat fetch")
            return []

        try:
            sessions = await self._classes_service.get_sessions_with_seats(date=target_date)
        except Exception as exc:
            logger.warning("ClassesService.get_sessions_with_seats failed: %s", exc)
            return []

        if not isinstance(sessions, Iterable):
            logger.debug("sessionsWithSeats returned non-iterable payload: %s", type(sessions))
            return []

        # normalize template ids from session payload
        for session in sessions:
            if not isinstance(session, dict):
                continue
            sess_template_id = session.get("templateId") or session.get("template_id")
            if sess_template_id and int(sess_template_id) == int(template_id):
                seats_payload = session.get("seats") or []
                return [self._seat_from_session_payload(seat) for seat in seats_payload]
        return []

    def _seat_from_session_payload(self, seat: Dict[str, Any]) -> SeatAvailability:
        occupant = seat.get("occupant") or {}
        return SeatAvailability(
            id=int(seat.get("seatId") or seat.get("seat_id") or seat.get("id")),
            label=str(seat.get("label") or ""),
            venue_id=seat.get("venueId") or seat.get("venue_id"),
            is_active=bool(seat.get("isActive", True)),
            is_available=str(seat.get("status", "free")) == "free",
            status=str(seat.get("status", "free")),
            occupant_name=occupant.get("fullName") or occupant.get("full_name"),
            occupant_id=occupant.get("personId") or occupant.get("person_id"),
        )

    async def _fallback_standing_bookings(
        self,
        template_id: int,
        target_date: date,
    ) -> List[SeatAvailability]:
        if not self._standing_bookings_service:
            return []
        try:
            seats = await self._standing_bookings_service.get_available_seats(
                template_id=template_id,
                date_to_check=target_date,
            )
        except Exception as exc:
            logger.error("Fallback standing bookings seat fetch failed: %s", exc)
            return []

        result: List[SeatAvailability] = []
        for seat in seats or []:
            if isinstance(seat, dict):
                result.append(
                    SeatAvailability(
                        id=int(seat.get("id")),
                        label=str(seat.get("label", "")),
                        venue_id=seat.get("venueId"),
                        is_active=bool(seat.get("isActive", True)),
                        is_available=bool(seat.get("isAvailable", True)),
                    )
                )
        return result
