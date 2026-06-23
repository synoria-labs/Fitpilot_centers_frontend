"""View models and state helpers for members UI components."""

from dataclasses import dataclass, replace
from datetime import datetime
import re
from typing import Any, Iterable, Optional, Sequence

from ..models.base import Member, MembershipInfo, ActiveStandingBookingInfo


@dataclass(frozen=True)
class MembershipSnapshot:
    """Lightweight view model for active membership data."""

    plan_name: str = "Sin membresia"
    status: str = "Sin estado"
    remaining_days: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @classmethod
    def from_source(cls, membership: Optional[Any]) -> "MembershipSnapshot":
        if isinstance(membership, dict):
            # Parse dates from dict if they're strings
            start_date = membership.get("start_date")
            end_date = membership.get("end_date")

            if start_date and isinstance(start_date, str):
                try:
                    start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                except:
                    start_date = None

            if end_date and isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except:
                    end_date = None

            return cls(
                plan_name=str(membership.get("plan_name") or membership.get("plan") or "Sin membresia"),
                status=str(membership.get("status") or "Sin estado"),
                remaining_days=membership.get("remaining_days") or membership.get("remainingDays"),
                start_date=start_date,
                end_date=end_date,
            )

        if isinstance(membership, MembershipInfo):
            return cls(
                plan_name=str(membership.plan_name or "Sin membresia"),
                status=str(membership.status or "Sin estado"),
                remaining_days=membership.remaining_days,
                start_date=membership.start_date,
                end_date=membership.end_date,
            )

        return cls()


@dataclass(frozen=True)
class StandingBookingSnapshot:
    template_id: Optional[int] = None
    template_name: str = ""
    class_type_name: str = ""
    weekday: Optional[int] = None
    start_time_local: Optional[str] = None
    venue_name: Optional[str] = None
    instructor_name: Optional[str] = None

    @classmethod
    def from_source(cls, booking: Optional[Any]) -> Optional["StandingBookingSnapshot"]:
        if booking is None:
            return None

        if isinstance(booking, ActiveStandingBookingInfo):
            return cls(
                template_id=int(booking.template_id),
                template_name=str(booking.template_name or ""),
                class_type_name=str(booking.class_type_name or ""),
                weekday=booking.weekday,
                start_time_local=booking.start_time_local,
                venue_name=booking.venue_name,
                instructor_name=booking.instructor_name
            )

        if isinstance(booking, dict):
            return cls(
                template_id=booking.get("template_id") or booking.get("templateId"),
                template_name=str(booking.get("template_name") or booking.get("templateName") or ""),
                class_type_name=str(booking.get("class_type_name") or booking.get("classTypeName") or ""),
                weekday=booking.get("weekday"),
                start_time_local=booking.get("start_time_local") or booking.get("startTimeLocal"),
                venue_name=booking.get("venue_name") or booking.get("venueName"),
                instructor_name=booking.get("instructor_name") or booking.get("instructorName")
            )

        return None


@dataclass(frozen=True)
class MemberSummary:
    """Dataset displayed on the members table."""

    member_id: int
    full_name: str
    email: str
    phone_number: str
    membership: MembershipSnapshot
    standing_booking: Optional[StandingBookingSnapshot]
    source: Any

    @classmethod
    def from_member(cls, member: Any) -> "MemberSummary":
        if isinstance(member, Member):
            membership = MembershipSnapshot.from_source(member.active_membership)
            standing_booking = StandingBookingSnapshot.from_source(member.active_standing_booking)
            return cls(
                member_id=int(member.id),
                full_name=str(member.full_name or "Sin nombre"),
                email=str(member.email or ""),
                phone_number=str(member.phone_number or ""),
                membership=membership,
                standing_booking=standing_booking,
                source=member,
            )

        # fallback for dict payloads coming from older services
        member_id = int(member.get("id") or member.get("member_id") or 0)
        membership = MembershipSnapshot.from_source(member.get("active_membership"))
        standing_booking = StandingBookingSnapshot.from_source(member.get("active_standing_booking"))
        full_name = str(member.get("full_name") or member.get("name") or "Sin nombre")
        email = str(member.get("email") or member.get("mail") or "")
        phone = str(member.get("phone_number") or member.get("phone") or "")
        return cls(
            member_id=member_id,
            full_name=full_name,
            email=email,
            phone_number=phone,
            membership=membership,
            standing_booking=standing_booking,
            source=member,
        )

    def with_source(self, source: Any) -> "MemberSummary":
        return replace(self, source=source)

    def matches(self, member_id: int) -> bool:
        return self.member_id == member_id


@dataclass(frozen=True)
class MemberDetailState:
    """Detailed state used by the member detail card."""

    member_id: Optional[int] = None
    full_name: str = "-"
    email: str = "-"
    phone_number: str = "-"
    profile_picture_url: Optional[str] = None
    registration_date: Optional[datetime] = None
    membership: MembershipSnapshot = MembershipSnapshot()
    standing_booking: Optional[StandingBookingSnapshot] = None

    @classmethod
    def from_summary(cls, summary: Optional[MemberSummary]) -> "MemberDetailState":
        if summary is None:
            return cls()

        # Extract registration date from source if available
        registration_date = None
        if hasattr(summary.source, 'registration_date'):
            registration_date = summary.source.registration_date
        elif isinstance(summary.source, dict) and 'registration_date' in summary.source:
            reg_date = summary.source['registration_date']
            if isinstance(reg_date, str):
                try:
                    registration_date = datetime.fromisoformat(reg_date.replace('Z', '+00:00'))
                except:
                    registration_date = None
            elif isinstance(reg_date, datetime):
                registration_date = reg_date

        # Extract profile picture URL
        profile_picture_url = None
        if hasattr(summary.source, 'profile_picture_url'):
            profile_picture_url = summary.source.profile_picture_url
        elif isinstance(summary.source, dict) and 'profile_picture_url' in summary.source:
            profile_picture_url = summary.source['profile_picture_url']

        return cls(
            member_id=summary.member_id,
            full_name=summary.full_name or "-",
            email=summary.email or "-",
            phone_number=summary.phone_number or "-",
            profile_picture_url=profile_picture_url,
            registration_date=registration_date,
            membership=summary.membership,
            standing_booking=summary.standing_booking,
        )


@dataclass(frozen=True)
class MemberListState:
    """Aggregate state tracked by the members controller."""

    members: tuple[MemberSummary, ...] = ()
    total: int = 0
    search: Optional[str] = None
    loading: bool = False
    limit: int = 100
    offset: int = 0

    @property
    def page(self) -> int:
        if self.limit <= 0:
            return 1
        return (self.offset // self.limit) + 1

    @property
    def total_pages(self) -> int:
        if self.total <= 0 or self.limit <= 0:
            return 1
        return ((self.total - 1) // self.limit) + 1

    @property
    def has_previous(self) -> bool:
        return self.offset > 0

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.members) < self.total

    @property
    def visible_start(self) -> int:
        return self.offset + 1 if self.members else 0

    @property
    def visible_end(self) -> int:
        return self.offset + len(self.members)

    def with_loading(self, loading: bool) -> "MemberListState":
        return replace(self, loading=loading)

    def with_search(self, search: Optional[str]) -> "MemberListState":
        return replace(self, search=search)

    def with_pagination(self, *, limit: int, offset: int) -> "MemberListState":
        return replace(self, limit=max(1, int(limit)), offset=max(0, int(offset)))

    def with_members(
        self,
        members: Sequence[MemberSummary],
        total: Optional[int] = None,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> "MemberListState":
        return replace(
            self,
            members=tuple(members),
            total=len(members) if total is None else total,
            limit=self.limit if limit is None else max(1, int(limit)),
            offset=self.offset if offset is None else max(0, int(offset)),
        )

    def upsert_member(self, summary: MemberSummary) -> "MemberListState":
        updated = []
        exists = False
        for item in self.members:
            if item.matches(summary.member_id):
                updated.append(summary)
                exists = True
            else:
                updated.append(item)
        if not exists:
            updated.insert(0, summary)
        return self.with_members(updated, self.total if exists else self.total + 1)

    def remove_member(self, member_id: int) -> "MemberListState":
        filtered = [item for item in self.members if not item.matches(member_id)]
        total = max(0, self.total - (1 if len(filtered) < len(self.members) else 0))
        return replace(self, members=tuple(filtered), total=total)


@dataclass(frozen=True)
class BasicInfoPayload:
    """Payload for updating basic member information."""

    name: str
    email: str
    phone: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "email": self.email, "phone": self.phone}

    def is_valid(self) -> bool:
        return all(
            (
                bool(self.name.strip()),
                _is_valid_email(self.email),
                _is_valid_phone(self.phone),
            )
        )


def map_members(payload: Iterable[Any]) -> list[MemberSummary]:
    """Convert a list of service payloads to table summaries."""
    return [MemberSummary.from_member(item) for item in payload]


def _is_valid_email(value: str) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def _is_valid_phone(value: str) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\+?\d{8,15}", value))
