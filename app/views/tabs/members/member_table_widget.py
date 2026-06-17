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
        self._rows: list[MemberSummary] = []
        self._configure()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def populate(self, members: Sequence[MemberSummary]) -> None:
        self._rows = list(members)
        self.setSortingEnabled(False)
        self.setRowCount(len(self._rows))

        for row, summary in enumerate(self._rows):
            self._set_row(row, summary)

        self.setSortingEnabled(True)

    def upsert_member(self, summary: MemberSummary) -> None:
        for index, existing in enumerate(self._rows):
            if existing.member_id == summary.member_id:
                self._rows[index] = summary
                self._set_row(index, summary)
                return

        self._rows.insert(0, summary)
        self.insertRow(0)
        self._set_row(0, summary)

    def remove_member(self, member_id: int) -> None:
        for index, summary in enumerate(self._rows):
            if summary.member_id == member_id:
                self._rows.pop(index)
                self.removeRow(index)
                break

    def current_summary(self) -> Optional[MemberSummary]:
        row = self.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def summaries(self) -> Iterable[MemberSummary]:
        return tuple(self._rows)

    def select_member(self, member_id: Optional[int]) -> bool:
        if member_id is None:
            if self.selectionModel() is not None:
                self.selectionModel().clearSelection()
            self.setCurrentIndex(QModelIndex())
            return False

        for index, summary in enumerate(self._rows):
            if summary.member_id == member_id:
                self.selectRow(index)
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
        summary = self.current_summary()
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
