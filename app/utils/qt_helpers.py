"""
Qt/PySide6 utilities for FitPilot frontend.

Provides helper functions for:
- ComboBox population and management
- Date conversions between Qt and Python
- Widget state management
"""

from datetime import date
from typing import Any, Callable, Optional
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox
import logging

logger = logging.getLogger(__name__)

PAYMENT_METHOD_OPTIONS = [
    ("Efectivo", "cash"),
    ("Tarjeta", "card"),
    ("Transferencia", "transfer"),
    ("Otro", "other"),
]


def populate_payment_methods(combo: QComboBox) -> None:
    """Populate a payment method combo with standard options."""
    combo.blockSignals(True)
    try:
        combo.clear()
        for label, value in PAYMENT_METHOD_OPTIONS:
            combo.addItem(label, value)
    finally:
        combo.blockSignals(False)


def configure_amount_input(spinbox: QDoubleSpinBox, maximum: float) -> None:
    """Configure a QDoubleSpinBox for amount input."""
    spinbox.setMaximum(maximum)
    spinbox.setDecimals(2)


def populate_combo_safely(
    combo: QComboBox,
    items: list[Any],
    label_fn: Callable[[Any], str],
    data_fn: Optional[Callable[[Any], Any]] = None,
    select_first: bool = True,
) -> None:
    """
    Populate a QComboBox with items while blocking signals.

    This prevents signal cascades during population and ensures
    clean state management.

    Args:
        combo: QComboBox to populate
        items: List of items to add
        label_fn: Function to extract display label from item
        data_fn: Optional function to extract user data (defaults to item itself)
        select_first: Whether to select the first item (default: True)

    Examples:
        >>> # Simple list of strings
        >>> populate_combo_safely(combo, ["Option 1", "Option 2"], lambda x: x)

        >>> # List of objects
        >>> plans = [Plan(id=1, name="Basic"), Plan(id=2, name="Premium")]
        >>> populate_combo_safely(combo, plans, lambda p: p.name, lambda p: p.id)
    """
    combo.blockSignals(True)
    try:
        combo.clear()

        for item in items:
            label = label_fn(item)
            data = data_fn(item) if data_fn else item
            combo.addItem(label, data)

        if select_first and combo.count() > 0:
            combo.setCurrentIndex(0)

    finally:
        combo.blockSignals(False)


def get_combo_selected_data(combo: QComboBox) -> Optional[Any]:
    """
    Get the user data from the currently selected combo box item.

    Args:
        combo: QComboBox to get data from

    Returns:
        User data of selected item, or None if no selection

    Examples:
        >>> data = get_combo_selected_data(combo)
        >>> if data:
        ...     print(f"Selected ID: {data}")
    """
    current_index = combo.currentIndex()
    if current_index < 0:
        return None

    return combo.itemData(current_index)


def set_combo_by_data(combo: QComboBox, data: Any, block_signals: bool = True) -> bool:
    """
    Set combo box selection by matching user data.

    Args:
        combo: QComboBox to update
        data: Data value to match
        block_signals: Whether to block signals during update

    Returns:
        True if match found and selected, False otherwise

    Examples:
        >>> # Select item with ID=5
        >>> success = set_combo_by_data(combo, 5)
    """
    if block_signals:
        combo.blockSignals(True)

    try:
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return True

        logger.warning("No combo item found with data: %s", data)
        return False

    finally:
        if block_signals:
            combo.blockSignals(False)


def qdate_to_python(qdate: QDate) -> Optional[date]:
    """
    Convert QDate to Python date object.

    Args:
        qdate: QDate object to convert

    Returns:
        Python date object, or None if qdate is invalid

    Examples:
        >>> from PySide6.QtCore import QDate
        >>> qd = QDate(2024, 3, 15)
        >>> py_date = qdate_to_python(qd)
        >>> print(py_date)
        2024-03-15
    """
    if not qdate or not qdate.isValid():
        return None

    try:
        return date(qdate.year(), qdate.month(), qdate.day())
    except ValueError as exc:
        logger.warning("Failed to convert QDate to Python date: %s", exc)
        return None


def python_to_qdate(py_date: Optional[date]) -> QDate:
    """
    Convert Python date to QDate object.

    Args:
        py_date: Python date object to convert

    Returns:
        QDate object, or invalid QDate if py_date is None

    Examples:
        >>> from datetime import date
        >>> py_date = date(2024, 3, 15)
        >>> qd = python_to_qdate(py_date)
        >>> print(qd.toString("dd/MM/yyyy"))
        15/03/2024
    """
    if py_date is None:
        return QDate()

    try:
        return QDate(py_date.year, py_date.month, py_date.day)
    except (AttributeError, ValueError) as exc:
        logger.warning("Failed to convert Python date to QDate: %s", exc)
        return QDate()


def clear_combo(combo: QComboBox, block_signals: bool = True) -> None:
    """
    Clear a combo box while optionally blocking signals.

    Args:
        combo: QComboBox to clear
        block_signals: Whether to block signals during clear

    Examples:
        >>> clear_combo(combo)
    """
    if block_signals:
        combo.blockSignals(True)

    try:
        combo.clear()
    finally:
        if block_signals:
            combo.blockSignals(False)


def enable_widget_group(widgets: list, enabled: bool) -> None:
    """
    Enable or disable a group of widgets at once.

    Args:
        widgets: List of QWidget objects
        enabled: True to enable, False to disable

    Examples:
        >>> widgets = [name_edit, email_edit, phone_edit]
        >>> enable_widget_group(widgets, False)  # Disable all
    """
    for widget in widgets:
        if widget:
            widget.setEnabled(enabled)


def set_widget_visible_group(widgets: list, visible: bool) -> None:
    """
    Show or hide a group of widgets at once.

    Args:
        widgets: List of QWidget objects
        visible: True to show, False to hide

    Examples:
        >>> error_widgets = [error_label, error_icon]
        >>> set_widget_visible_group(error_widgets, False)
    """
    for widget in widgets:
        if widget:
            widget.setVisible(visible)
