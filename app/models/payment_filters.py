"""Filter state for the Finances panel.

Encapsulates the combination of temporal range, status, method, and search box
that drives both the payments table and the metrics panel. The frontend works
in the user's local timezone so "today" matches what they see on their clock;
the backend normalizes to UTC.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional, Tuple


class FilterPreset(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"          # Mon..Sun containing today
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    LAST_30_DAYS = "last_30_days"
    THIS_YEAR = "this_year"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


PRESET_LABELS: dict[FilterPreset, str] = {
    FilterPreset.TODAY: "Hoy",
    FilterPreset.YESTERDAY: "Ayer",
    FilterPreset.THIS_WEEK: "Esta semana",
    FilterPreset.THIS_MONTH: "Este mes",
    FilterPreset.LAST_MONTH: "Mes anterior",
    FilterPreset.LAST_30_DAYS: "Últimos 30 días",
    FilterPreset.THIS_YEAR: "Este año",
    FilterPreset.ALL_TIME: "Todo el historial",
    FilterPreset.CUSTOM: "Personalizado",
}


def _start_of_day(d: datetime) -> datetime:
    return datetime.combine(d.date(), time.min, tzinfo=d.tzinfo)


def _end_of_day(d: datetime) -> datetime:
    return datetime.combine(d.date(), time.max, tzinfo=d.tzinfo)


def compute_preset_range(
    preset: FilterPreset,
    *,
    now: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Resolve a preset into a (start, end) datetime pair in the local timezone.

    Returns (None, None) for ALL_TIME and CUSTOM (the caller supplies the bounds).
    """
    if preset in (FilterPreset.ALL_TIME, FilterPreset.CUSTOM):
        return None, None

    now = now or datetime.now().astimezone()
    today_start = _start_of_day(now)
    today_end = _end_of_day(now)

    if preset is FilterPreset.TODAY:
        return today_start, today_end

    if preset is FilterPreset.YESTERDAY:
        y = today_start - timedelta(days=1)
        return y, _end_of_day(y)

    if preset is FilterPreset.THIS_WEEK:
        # Monday-anchored. weekday(): Mon=0..Sun=6
        monday = today_start - timedelta(days=now.weekday())
        sunday = _end_of_day(monday + timedelta(days=6))
        return monday, sunday

    if preset is FilterPreset.THIS_MONTH:
        first = today_start.replace(day=1)
        return first, today_end

    if preset is FilterPreset.LAST_MONTH:
        first_this = today_start.replace(day=1)
        last_prev = first_this - timedelta(seconds=1)
        first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return first_prev, _end_of_day(last_prev)

    if preset is FilterPreset.LAST_30_DAYS:
        return today_start - timedelta(days=29), today_end

    if preset is FilterPreset.THIS_YEAR:
        return today_start.replace(month=1, day=1), today_end

    return None, None


@dataclass(frozen=True)
class PaymentFilters:
    preset: FilterPreset = FilterPreset.THIS_MONTH
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    method: Optional[str] = None
    search: Optional[str] = None

    @classmethod
    def from_preset(
        cls, preset: FilterPreset, *, now: Optional[datetime] = None
    ) -> "PaymentFilters":
        start, end = compute_preset_range(preset, now=now)
        return cls(preset=preset, start_date=start, end_date=end)

    def with_preset(
        self, preset: FilterPreset, *, now: Optional[datetime] = None
    ) -> "PaymentFilters":
        start, end = compute_preset_range(preset, now=now)
        return replace(self, preset=preset, start_date=start, end_date=end)

    def with_custom_range(
        self, start: Optional[datetime], end: Optional[datetime]
    ) -> "PaymentFilters":
        return replace(
            self, preset=FilterPreset.CUSTOM, start_date=start, end_date=end
        )

    def with_status(self, status: Optional[str]) -> "PaymentFilters":
        return replace(self, status=status or None)

    def with_method(self, method: Optional[str]) -> "PaymentFilters":
        return replace(self, method=method or None)

    def with_search(self, search: Optional[str]) -> "PaymentFilters":
        return replace(self, search=(search or None))

    def to_graphql_kwargs(self) -> dict:
        """Compact dict of non-null fields ready to pass as GraphQL variables."""
        out: dict = {}
        if self.start_date is not None:
            out["start_date"] = self.start_date.isoformat()
        if self.end_date is not None:
            out["end_date"] = self.end_date.isoformat()
        if self.status:
            out["status"] = self.status
        if self.method:
            out["method"] = self.method
        if self.search:
            out["search"] = self.search
        return out

    def cache_key(self) -> str:
        """Stable key suitable for caching results scoped to this filter combination."""
        parts = [
            self.preset.value,
            self.start_date.isoformat() if self.start_date else "-",
            self.end_date.isoformat() if self.end_date else "-",
            self.status or "-",
            self.method or "-",
            self.search or "-",
        ]
        return ":".join(parts)
