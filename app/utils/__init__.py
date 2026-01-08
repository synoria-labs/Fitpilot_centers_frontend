"""
Utilities package for FitPilot frontend.

This package provides reusable utility functions for:
- Formatting (currency, percentages, dates)
- Qt helpers (combo boxes, date conversions)
- Dialog helpers (standardized messages)
- DateTime operations (parsing, formatting)
- Debouncing and throttling (delayed execution)
"""

from app.utils.formatters import format_currency, format_percentage, format_date
from app.utils.datetime_helpers import parse_iso_datetime, format_iso_datetime
from app.utils.qt_helpers import (
    populate_combo_safely,
    qdate_to_python,
    python_to_qdate,
)
from app.utils.dialog_helpers import (
    show_error,
    show_success,
    show_confirmation,
    show_info,
)
from app.utils.debounce import (
    Debouncer,
    Throttler,
    create_search_debouncer,
    create_scroll_throttler,
)

__all__ = [
    # Formatters
    "format_currency",
    "format_percentage",
    "format_date",
    # DateTime
    "parse_iso_datetime",
    "format_iso_datetime",
    # Qt Helpers
    "populate_combo_safely",
    "qdate_to_python",
    "python_to_qdate",
    # Dialog Helpers
    "show_error",
    "show_success",
    "show_confirmation",
    "show_info",
    # Debouncing
    "Debouncer",
    "Throttler",
    "create_search_debouncer",
    "create_scroll_throttler",
]
