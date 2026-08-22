"""Table widget used to display members within the members tab."""

from typing import Iterable, Optional, Sequence

from PySide6.QtCore import Qt, Signal, QEvent, QModelIndex
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from ....viewmodels.members_state import MemberSummary
from ...table_widget_helpers import configure_table_widget
from .status_badge import create_status_icon


class MemberTableWidget(QTableWidget):
    """QTableWidget wrapper that presents member summaries."""

    selection_changed = Signal(object)  # MemberSummary | None
    activated = Signal(object)          # MemberSummary | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # QTableWidget owns the visual row order.  That order changes whenever
        # the user sorts a column, so member identity must not be inferred from
        # a parallel list index.  Keep summaries keyed by the stable ID stored
        # on each row instead.
        self._summaries_by_id: dict[int, MemberSummary] = {}
        self._configure()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def populate(self, members: Sequence[MemberSummary]) -> None:
        summaries = list(members)
        self._summaries_by_id = {
            summary.member_id: summary for summary in summaries
        }
        self.setSortingEnabled(False)
        self.setRowCount(len(summaries))

        for row, summary in enumerate(summaries):
            self._set_row(row, summary)

        self.setSortingEnabled(True)

    def upsert_member(self, summary: MemberSummary) -> None:
        row = self._row_for_member_id(summary.member_id)
        self._summaries_by_id[summary.member_id] = summary

        # Updating the text of the active sort column can move a row
        # immediately.  Disable sorting so both cells are updated atomically,
        # then let Qt restore the active visual order.
        sorting_enabled = self.isSortingEnabled()
        if sorting_enabled:
            self.setSortingEnabled(False)
        try:
            if row is None:
                row = 0
                self.insertRow(row)
            self._set_row(row, summary)
        finally:
            if sorting_enabled:
                self.setSortingEnabled(True)

    def remove_member(self, member_id: int) -> None:
        row = self._row_for_member_id(member_id)
        self._summaries_by_id.pop(member_id, None)
        if row is not None:
            self.removeRow(row)

    def current_summary(self) -> Optional[MemberSummary]:
        return self._summary_for_row(self.currentRow())

    def summaries(self) -> Iterable[MemberSummary]:
        return tuple(self._summaries_by_id.values())

    def select_member(self, member_id: Optional[int]) -> bool:
        if member_id is None:
            if self.selectionModel() is not None:
                self.selectionModel().clearSelection()
            self.setCurrentIndex(QModelIndex())
            return False

        row = self._row_for_member_id(member_id)
        if row is not None:
            self.selectRow(row)
            return True

        if self.selectionModel() is not None:
            self.selectionModel().clearSelection()
        self.setCurrentIndex(QModelIndex())
        return False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def _configure(self) -> None:
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Nombre", "Estado"])

        configure_table_widget(self)
        self.setSortingEnabled(True)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(1, 140)

        # Señales existentes
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # --- NUEVO: click en zona vacía del viewport -> limpiar selección
        self.viewport().installEventFilter(self)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _row_for_member_id(self, member_id: int) -> Optional[int]:
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == member_id:
                return row
        return None

    def _summary_for_row(self, row: int) -> Optional[MemberSummary]:
        if row < 0 or row >= self.rowCount():
            return None
        item = self.item(row, 0)
        if item is None:
            return None
        member_id = item.data(Qt.ItemDataRole.UserRole)
        return self._summaries_by_id.get(member_id)

    def _set_row(self, row: int, summary: MemberSummary) -> None:
        # Backend now calculates the real status based on dates
        values = [
            summary.full_name or "Sin nombre",
            summary.membership.status or "Sin estado",
        ]

        for col, value in enumerate(values):
            item = self.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.setItem(row, col, item)

            item.setText(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, summary.member_id)
            if col == 1:
                item.setIcon(create_status_icon(summary.membership.status))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.current_summary())

    def _on_cell_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        summary = self._summary_for_row(row)
        self.activated.emit(summary)

    # ------------------------------------------------------------------
    # Event handling extra
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        # Click sobre el fondo del viewport (no hay índice válido) -> limpiar selección
        if obj is self.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            idx = self.indexAt(event.pos())
            if not idx.isValid():
                if self.selectionModel() is not None:
                    self.selectionModel().clearSelection()
                self.setCurrentIndex(QModelIndex())
                self.selection_changed.emit(None)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        # Tecla Esc -> limpiar selección (práctico para cerrar el panel)
        if event.key() == Qt.Key.Key_Escape:
            if self.selectionModel() is not None:
                self.selectionModel().clearSelection()
            self.setCurrentIndex(QModelIndex())
            self.selection_changed.emit(None)
            return
        super().keyPressEvent(event)
