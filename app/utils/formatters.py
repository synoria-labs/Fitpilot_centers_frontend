"""
Formatting utilities for FitPilot frontend.

Provides consistent formatting for:
- Currency (money values)
- Percentages
- Dates and times
"""

from datetime import date, datetime
from typing import Optional


def format_currency(
    amount: float, symbol: str = "$", decimals: int = 2, thousands_sep: str = ","
) -> str:
    """
    Format a numeric amount as currency.

    Args:
        amount: The numeric amount to format
        symbol: Currency symbol (default: "$")
        decimals: Number of decimal places (default: 2)
        thousands_sep: Thousands separator (default: ",")

    Returns:
        Formatted currency string

    Examples:
        >>> format_currency(1234.56)
        '$1,234.56'
        >>> format_currency(1000000, decimals=0)
        '$1,000,000'
    """
    format_str = f"{{:,.{decimals}f}}"
    formatted_amount = format_str.format(amount)

    if thousands_sep != ",":
        formatted_amount = formatted_amount.replace(",", thousands_sep)

    return f"{symbol}{formatted_amount}"


def format_percentage(
    value: float, decimals: int = 1, include_symbol: bool = True
) -> str:
    """
    Format a numeric value as a percentage.

    Args:
        value: The numeric value to format (e.g., 0.15 for 15%)
        decimals: Number of decimal places (default: 1)
        include_symbol: Whether to include the % symbol (default: True)

    Returns:
        Formatted percentage string

    Examples:
        >>> format_percentage(0.15)
        '15.0%'
        >>> format_percentage(0.1234, decimals=2)
        '12.34%'
    """
    percentage = value * 100 if value <= 1.0 else value
    format_str = f"{{:.{decimals}f}}"
    formatted = format_str.format(percentage)

    return f"{formatted}%" if include_symbol else formatted


def format_date(
    date_obj: Optional[date | datetime], format_str: str = "%d/%m/%Y"
) -> str:
    """
    Format a date object as a string.

    Args:
        date_obj: Date or datetime object to format
        format_str: Format string (default: "%d/%m/%Y" for DD/MM/YYYY)

    Returns:
        Formatted date string, or empty string if date_obj is None

    Examples:
        >>> from datetime import date
        >>> format_date(date(2024, 3, 15))
        '15/03/2024'
        >>> format_date(date(2024, 3, 15), "%Y-%m-%d")
        '2024-03-15'
    """
    if date_obj is None:
        return ""

    return date_obj.strftime(format_str)


def format_datetime(
    datetime_obj: Optional[datetime], format_str: str = "%d/%m/%Y %H:%M"
) -> str:
    """
    Format a datetime object as a string.

    Args:
        datetime_obj: Datetime object to format
        format_str: Format string (default: "%d/%m/%Y %H:%M" for DD/MM/YYYY HH:MM)

    Returns:
        Formatted datetime string, or empty string if datetime_obj is None

    Examples:
        >>> from datetime import datetime
        >>> format_datetime(datetime(2024, 3, 15, 14, 30))
        '15/03/2024 14:30'
    """
    if datetime_obj is None:
        return ""

    return datetime_obj.strftime(format_str)


def format_phone(phone: Optional[str]) -> str:
    """
    Format a phone number for display.

    Args:
        phone: Phone number string

    Returns:
        Formatted phone number, or empty string if None

    Examples:
        >>> format_phone("5551234567")
        '555-123-4567'
        >>> format_phone("1234567890")
        '123-456-7890'
    """
    if not phone:
        return ""

    # Remove any non-digit characters
    digits = "".join(filter(str.isdigit, phone))

    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11:
        return f"{digits[0]} {digits[1:4]}-{digits[4:7]}-{digits[7:]}"

    return phone  # Return as-is if doesn't match expected format


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted file size string

    Examples:
        >>> format_file_size(1024)
        '1.0 KB'
        >>> format_file_size(1048576)
        '1.0 MB'
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
