"""Shared Qt stylesheet snippets for selectable item states."""


def selectable_item_states_qss() -> str:
    """Return global QSS for list and combo popup item selection states."""
    return """
QListView::item,
QListWidget::item,
QComboBox QAbstractItemView::item {
    border-radius: 8px;
    color: palette(text);
}

QComboBox QAbstractItemView {
    selection-background-color: palette(alternate-base);
    selection-color: palette(text);
}

QListView::item:hover,
QListWidget::item:hover,
QComboBox QAbstractItemView::item:hover,
QListView::item:selected,
QListWidget::item:selected,
QComboBox QAbstractItemView::item:selected,
QListView::item:selected:active,
QListWidget::item:selected:active,
QComboBox QAbstractItemView::item:selected:active,
QListView::item:selected:!active,
QListWidget::item:selected:!active,
QComboBox QAbstractItemView::item:selected:!active {
    background-color: palette(alternate-base);
    color: palette(text);
}
"""
