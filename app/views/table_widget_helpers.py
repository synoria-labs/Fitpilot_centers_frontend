"""Shared QTableWidget configuration helpers."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QTableWidget


def configure_table_widget(
    table: QTableWidget,
    *,
    editable: bool = False,
    selection_mode: QAbstractItemView.SelectionMode = QAbstractItemView.SelectionMode.SingleSelection,
    focus_policy: Qt.FocusPolicy = Qt.FocusPolicy.StrongFocus,
) -> None:
    """Apply FitPilot's default behavior to a table without touching its columns."""
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(selection_mode)
    table.setAlternatingRowColors(True)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setFocusPolicy(focus_policy)
    table.setShowGrid(True)
    table.setMouseTracking(True)
    table.viewport().setMouseTracking(True)

    if not editable:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    horizontal_header = table.horizontalHeader()
    horizontal_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    horizontal_header.setHighlightSections(False)
    horizontal_header.setSectionsMovable(False)

    vertical_header = table.verticalHeader()
    vertical_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    vertical_header.setHighlightSections(False)
    vertical_header.setSectionsMovable(False)
