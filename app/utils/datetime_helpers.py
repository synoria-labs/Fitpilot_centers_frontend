"""
DateTime utilities for FitPilot frontend.

Provides functions for:
- Parsing ISO datetime strings
- Formatting datetime objects to ISO strings
- Date/time calculations and conversions
"""

from datetime import date, datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def parse_iso_datetime(iso_string: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 datetime string to a datetime object.

    Handles multiple ISO formats including:
    - 2024-03-15T10:30:00
    - 2024-03-15T10:30:00.123456
    - 2024-03-15T10:30:00Z
    - 2024-03-15T10:30:00+00:00

    Args:
        iso_string: ISO 8601 formatted datetime string

    Returns:
        datetime object, or None if parsing fails

    Examples:
        >>> parse_iso_datetime("2024-03-15T10:30:00")
        datetime(2024, 3, 15, 10, 30)
        >>> parse_iso_datetime("2024-03-15T10:30:00.123456Z")
        datetime(2024, 3, 15, 10, 30, 0, 123456)
    """
    if not iso_string:
        return None

    try:
        # Remove 'Z' suffix if present (UTC indicator)
        if iso_string.endswith("Z"):
            iso_string = iso_string[:-1] + "+00:00"

        # Try parsing with timezone
        if "+" in iso_string or iso_string.count("-") > 2:
            return datetime.fromisoformat(iso_string)

        # Try parsing without timezone
        return datetime.fromisoformat(iso_string)

    except (ValueError, AttributeError) as exc:
        logger.warning("Failed to parse ISO datetime '%s': %s", iso_string, exc)
        return None


def format_iso_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime object to ISO 8601 string.

    Args:
        dt: datetime object to format

    Returns:
        ISO 8601 formatted string, or None if dt is None

    Examples:
        >>> from datetime import datetime
        >>> format_iso_datetime(datetime(2024, 3, 15, 10, 30))
        '2024-03-15T10:30:00'
    """
    if dt is None:
        return None

    return dt.isoformat()


def parse_iso_date(iso_string: Optional[str]) -> Optional[date]:
    """
    Parse an ISO date string (YYYY-MM-DD) to a date object.

    Args:
        iso_string: ISO formatted date string

    Returns:
        date object, or None if parsing fails

    Examples:
        >>> parse_iso_date("2024-03-15")
        date(2024, 3, 15)
    """
    if not iso_string:
        return None

    try:
        return date.fromisoformat(iso_string)
    except (ValueError, AttributeError) as exc:
        logger.warning("Failed to parse ISO date '%s': %s", iso_string, exc)
        return None


def format_iso_date(d: Optional[date]) -> Optional[str]:
    """
    Format a date object to ISO string (YYYY-MM-DD).

    Args:
        d: date object to format

    Returns:
        ISO formatted date string, or None if d is None

    Examples:
        >>> from datetime import date
        >>> format_iso_date(date(2024, 3, 15))
        '2024-03-15'
    """
    if d is None:
        return None

    return d.isoformat()


def add_days(d: date, days: int) -> date:
    """
    Add days to a date.

    Args:
        d: Base date
        days: Number of days to add (can be negative)

    Returns:
        New date with days added

    Examples:
        >>> from datetime import date
        >>> add_days(date(2024, 3, 15), 7)
        date(2024, 3, 22)
    """
    return d + timedelta(days=days)


def add_months(d: date, months: int) -> date:
    """
    Add months to a date.

    Args:
        d: Base date
        months: Number of months to add (can be negative)

    Returns:
        New date with months added

    Examples:
        >>> from datetime import date
        >>> add_months(date(2024, 3, 15), 1)
        date(2024, 4, 15)
    """
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def days_between(start: date, end: date) -> int:
    """
    Calculate the number of days between two dates.

    Args:
        start: Start date
        end: End date

    Returns:
        Number of days between dates (can be negative)

    Examples:
        >>> from datetime import date
        >>> days_between(date(2024, 3, 15), date(2024, 3, 22))
        7
    """
    return (end - start).days


def is_past(d: date) -> bool:
    """
    Check if a date is in the past.

    Args:
        d: Date to check

    Returns:
        True if date is before today

    Examples:
        >>> from datetime import date, timedelta
        >>> is_past(date.today() - timedelta(days=1))
        True
        >>> is_past(date.today() + timedelta(days=1))
        False
    """
    return d < date.today()


def is_future(d: date) -> bool:
    """
    Check if a date is in the future.

    Args:
        d: Date to check

    Returns:
        True if date is after today

    Examples:
        >>> from datetime import date, timedelta
        >>> is_future(date.today() + timedelta(days=1))
        True
        >>> is_future(date.today() - timedelta(days=1))
        False
    """
    return d > date.today()


def is_today(d: date) -> bool:
    """
    Check if a date is today.

    Args:
        d: Date to check

    Returns:
        True if date is today
    """
    return d == date.today()
