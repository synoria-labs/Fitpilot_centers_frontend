"""Selector de clases: primero la actividad, después sus horarios en una parrilla.

El horario semanal de un gimnasio *es* una parrilla de horas por días, y la lista plana que
había antes la aplanaba hasta hacerla ilegible: para lo que el usuario piensa como una sola
cosa — "el Spinning de las 8" — había que marcar una casilla por día.

Aquí la parrilla es la única fuente de verdad. Todo lo demás (franjas del día, instructor,
"Todos") son atajos que marcan celdas, no filtros independientes; así no hay que explicar en
pantalla cómo se combinan dos criterios distintos, que es donde estas interfaces se pierden.

La selección se traduce a la forma que entiende el backend::

    [{"class_type_id": 3},                          # la actividad completa
     {"class_type_id": 7, "template_ids": [11, 14]}]  # sólo esos horarios
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

# Los días se guardan 0=domingo..6=sábado (backend classModel.ClassTemplate); la semana se
# muestra empezando en lunes, que es como se lee un horario en español.
_WEEKDAY_ORDER = (1, 2, 3, 4, 5, 6, 0)
_WEEKDAY_SHORT = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 0: "Dom"}
_WEEKDAY_LONG = {
    1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves",
    5: "viernes", 6: "sábado", 0: "domingo",
}

# Franjas por hora de inicio. Sirven justo cuando los horarios no están alineados: 7:00 y
# 7:30 caen en la misma franja aunque sean filas distintas de la parrilla.
_DAY_PARTS = (
    ("morning", "Mañana", 0, 12),
    ("afternoon", "Tarde", 12, 18),
    ("evening", "Noche", 18, 24),
)


def _hour_of(template: Dict[str, Any]) -> int:
    raw = str(template.get("start_time_local") or "")
    try:
        return int(raw[:2])
    except (TypeError, ValueError):
        return 0


def time_label(template: Dict[str, Any]) -> str:
    """'08:00' a partir de un start_time_local que llega como '08:00:00'."""
    raw = str(template.get("start_time_local") or "")
    return raw[:5] if len(raw) >= 5 else raw


class ChipButton(QPushButton):
    """Píldora seleccionable. El estilo vive en screen_qss para que siga el tema."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("campChip")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class _CellButton(QPushButton):
    """Una celda de la parrilla: un horario concreto de la actividad activa."""

    def __init__(self, template_ids: List[int], parent: Optional[QWidget] = None) -> None:
        super().__init__("", parent)
        self.setObjectName("campGridCell")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 30)
        self.template_ids = list(template_ids)


class ScheduleGrid(QWidget):
    """Horas en las filas, días en las columnas. Los encabezados seleccionan en bloque."""

    selection_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._templates: List[Dict[str, Any]] = []
        self._cells: Dict[tuple, _CellButton] = {}
        self._row_headers: Dict[str, QPushButton] = {}
        self._column_headers: Dict[int, QPushButton] = {}

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(4)
        self._layout.setVerticalSpacing(4)

    # ------------------------------------------------------------------ build
    def set_templates(self, templates: List[Dict[str, Any]]) -> None:
        self._templates = list(templates or [])
        self._rebuild()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cells.clear()
        self._row_headers.clear()
        self._column_headers.clear()

    def _rebuild(self) -> None:
        self._clear()
        if not self._templates:
            empty = QLabel("Esta actividad no tiene horarios configurados.")
            empty.setObjectName("campHint")
            self._layout.addWidget(empty, 0, 0)
            return

        times = sorted({time_label(t) for t in self._templates})
        # Sólo se muestran los días que realmente tienen clase: una columna vacía no aporta
        # nada y hace la parrilla más ancha de lo necesario.
        used_days = {int(t.get("weekday") or 0) for t in self._templates}
        days = [d for d in _WEEKDAY_ORDER if d in used_days]

        by_cell: Dict[tuple, List[int]] = {}
        for template in self._templates:
            key = (time_label(template), int(template.get("weekday") or 0))
            by_cell.setdefault(key, []).append(template.get("id"))

        for column, weekday in enumerate(days, start=1):
            header = QPushButton(_WEEKDAY_SHORT.get(weekday, "?"))
            header.setObjectName("campGridHeader")
            header.setCursor(Qt.CursorShape.PointingHandCursor)
            header.setToolTip(f"Seleccionar todo el {_WEEKDAY_LONG.get(weekday, '')}")
            header.clicked.connect(lambda _c=False, d=weekday: self._toggle_column(d))
            self._layout.addWidget(header, 0, column)
            self._column_headers[weekday] = header

        for row, clock in enumerate(times, start=1):
            header = QPushButton(clock)
            header.setObjectName("campGridHeader")
            header.setCursor(Qt.CursorShape.PointingHandCursor)
            header.setToolTip(f"Seleccionar todos los días a las {clock}")
            header.clicked.connect(lambda _c=False, t=clock: self._toggle_row(t))
            self._layout.addWidget(header, row, 0)
            self._row_headers[clock] = header

            for column, weekday in enumerate(days, start=1):
                ids = by_cell.get((clock, weekday))
                if not ids:
                    blank = QLabel("·")
                    blank.setObjectName("campGridBlank")
                    blank.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._layout.addWidget(blank, row, column)
                    continue
                cell = _CellButton(ids, self)
                cell.setToolTip(self._cell_tooltip(clock, weekday, ids))
                cell.toggled.connect(lambda _s: self.selection_changed.emit())
                self._layout.addWidget(cell, row, column)
                self._cells[(clock, weekday)] = cell

    def _cell_tooltip(self, clock: str, weekday: int, ids: List[int]) -> str:
        names = []
        for template in self._templates:
            if template.get("id") in ids:
                instructor = template.get("instructor_name")
                names.append(instructor or template.get("name") or "")
        detail = " · ".join(n for n in names if n)
        base = f"{_WEEKDAY_LONG.get(weekday, '')} {clock}"
        return f"{base} · {detail}" if detail else base

    # ------------------------------------------------------------------ selection
    def _set_cells(self, cells, checked: bool) -> None:
        for cell in cells:
            cell.blockSignals(True)
            cell.setChecked(checked)
            cell.blockSignals(False)
        self.selection_changed.emit()

    def _toggle_row(self, clock: str) -> None:
        row = [c for (t, _d), c in self._cells.items() if t == clock]
        # Si ya estaba toda marcada, el mismo clic la desmarca.
        self._set_cells(row, not all(c.isChecked() for c in row))

    def _toggle_column(self, weekday: int) -> None:
        column = [c for (_t, d), c in self._cells.items() if d == weekday]
        self._set_cells(column, not all(c.isChecked() for c in column))

    def select_all(self, checked: bool = True) -> None:
        self._set_cells(list(self._cells.values()), checked)

    def select_day_part(self, key: str) -> None:
        bounds = next((p for p in _DAY_PARTS if p[0] == key), None)
        if bounds is None:
            return
        _key, _label, low, high = bounds
        targets = []
        for template in self._templates:
            hour = _hour_of(template)
            if low <= hour < high:
                cell = self._cells.get(
                    (time_label(template), int(template.get("weekday") or 0))
                )
                if cell is not None:
                    targets.append(cell)
        if targets:
            self._set_cells(targets, not all(c.isChecked() for c in targets))

    def select_instructor(self, instructor_id: int) -> None:
        targets = []
        for template in self._templates:
            if template.get("instructor_id") == instructor_id:
                cell = self._cells.get(
                    (time_label(template), int(template.get("weekday") or 0))
                )
                if cell is not None:
                    targets.append(cell)
        if targets:
            self._set_cells(targets, True)

    def selected_template_ids(self) -> List[int]:
        ids: List[int] = []
        for cell in self._cells.values():
            if cell.isChecked():
                ids.extend(cell.template_ids)
        return sorted({i for i in ids if i is not None})

    def apply_template_ids(self, template_ids: Optional[Set[int]]) -> None:
        wanted = set(template_ids or ())
        for cell in self._cells.values():
            cell.blockSignals(True)
            cell.setChecked(bool(wanted) and any(i in wanted for i in cell.template_ids))
            cell.blockSignals(False)

    def has_cells(self) -> bool:
        return bool(self._cells)


class ClassPicker(QWidget):
    """Actividades arriba, parrilla de la actividad activa debajo."""

    selection_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._class_types: List[Dict[str, Any]] = []
        self._templates_by_type: Dict[int, List[Dict[str, Any]]] = {}
        self._type_chips: Dict[int, ChipButton] = {}
        self._tab_chips: Dict[int, ChipButton] = {}
        # None significa "la actividad completa"; un set, horarios concretos.
        self._selection: Dict[int, Optional[Set[int]]] = {}
        self._active_type: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._type_row = QHBoxLayout()
        self._type_row.setContentsMargins(0, 0, 0, 0)
        self._type_row.setSpacing(6)
        layout.addLayout(self._type_row)

        self._tab_row = QHBoxLayout()
        self._tab_row.setContentsMargins(0, 0, 0, 0)
        self._tab_row.setSpacing(6)
        layout.addLayout(self._tab_row)

        self._quick_row = QHBoxLayout()
        self._quick_row.setContentsMargins(0, 0, 0, 0)
        self._quick_row.setSpacing(6)
        self.all_chip = ChipButton("Todos")
        self.all_chip.setToolTip("Toda la actividad, sin importar el horario")
        self.all_chip.toggled.connect(self._on_all_toggled)
        self._quick_row.addWidget(self.all_chip)
        self._part_chips: Dict[str, ChipButton] = {}
        for key, label, _low, _high in _DAY_PARTS:
            chip = ChipButton(label)
            chip.setCheckable(False)  # es un atajo, no un estado
            chip.clicked.connect(lambda _c=False, k=key: self._on_day_part(k))
            self._quick_row.addWidget(chip)
            self._part_chips[key] = chip
        self.instructor_combo = QComboBox()
        self.instructor_combo.setMinimumWidth(150)
        self.instructor_combo.activated.connect(self._on_instructor)
        self._quick_row.addWidget(self.instructor_combo)
        self._quick_row.addStretch()
        layout.addLayout(self._quick_row)

        self.grid = ScheduleGrid()
        self.grid.selection_changed.connect(self._on_grid_changed)
        layout.addWidget(self.grid)

        self.summary_label = QLabel("Sin filtro de clase: entran todas.")
        self.summary_label.setObjectName("campHint")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self._sync_visibility()

    # ------------------------------------------------------------------ data in
    def set_classes(
        self, class_types: List[Dict[str, Any]], class_templates: List[Dict[str, Any]]
    ) -> None:
        self._class_types = list(class_types or [])
        self._templates_by_type = {}
        for template in class_templates or []:
            if not template.get("is_active"):
                continue
            self._templates_by_type.setdefault(template.get("class_type_id"), []).append(
                template
            )

        while self._type_row.count():
            item = self._type_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._type_chips.clear()

        for class_type in self._class_types:
            type_id = class_type.get("id")
            chip = ChipButton(class_type.get("name") or "?")
            chip.setChecked(type_id in self._selection)
            chip.toggled.connect(lambda checked, t=type_id: self._on_type_toggled(t, checked))
            self._type_row.addWidget(chip)
            self._type_chips[type_id] = chip
        self._type_row.addStretch()

        self._rebuild_tabs()
        self._load_active_grid()

    # ------------------------------------------------------------------ state
    def _on_type_toggled(self, type_id: Optional[int], checked: bool) -> None:
        if type_id is None:
            return
        if checked:
            self._selection.setdefault(type_id, None)  # por defecto, la actividad completa
            self._active_type = type_id
        else:
            self._selection.pop(type_id, None)
            if self._active_type == type_id:
                self._active_type = next(iter(self._selection), None)
        self._rebuild_tabs()
        self._load_active_grid()
        self._emit()

    def _rebuild_tabs(self) -> None:
        while self._tab_row.count():
            item = self._tab_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._tab_chips.clear()
        # Con una sola actividad seleccionada la fila de pestañas no dice nada nuevo.
        if len(self._selection) < 2:
            return
        for type_id in self._selection:
            chip = ChipButton(self._tab_text(type_id))
            chip.setChecked(type_id == self._active_type)
            chip.clicked.connect(lambda _c=False, t=type_id: self._set_active(t))
            self._tab_row.addWidget(chip)
            self._tab_chips[type_id] = chip
        self._tab_row.addStretch()

    def _tab_text(self, type_id: int) -> str:
        chosen = self._selection.get(type_id)
        detail = "todos" if chosen is None else str(len(chosen))
        return f"{self._type_name(type_id)} · {detail}"

    def _set_active(self, type_id: int) -> None:
        self._active_type = type_id
        self._rebuild_tabs()
        self._load_active_grid()

    def _load_active_grid(self) -> None:
        templates = self._templates_by_type.get(self._active_type, [])
        self.grid.set_templates(templates)
        chosen = self._selection.get(self._active_type)
        self.all_chip.blockSignals(True)
        self.all_chip.setChecked(chosen is None and self._active_type is not None)
        self.all_chip.blockSignals(False)
        self.grid.apply_template_ids(chosen)
        self._reload_instructors(templates)
        self._sync_visibility()
        self._refresh_summary()

    def _reload_instructors(self, templates: List[Dict[str, Any]]) -> None:
        self.instructor_combo.blockSignals(True)
        self.instructor_combo.clear()
        self.instructor_combo.addItem("Instructor…", None)
        seen = {}
        for template in templates:
            instructor_id = template.get("instructor_id")
            if instructor_id is not None and instructor_id not in seen:
                seen[instructor_id] = template.get("instructor_name") or f"#{instructor_id}"
        for instructor_id, name in seen.items():
            self.instructor_combo.addItem(name, instructor_id)
        self.instructor_combo.blockSignals(False)
        self.instructor_combo.setVisible(bool(seen))

    def _sync_visibility(self) -> None:
        active = self._active_type is not None and self.grid.has_cells()
        for index in range(self._quick_row.count()):
            widget = self._quick_row.itemAt(index).widget()
            if widget is not None and widget is not self.instructor_combo:
                widget.setVisible(active)
        self.grid.setVisible(self._active_type is not None)

    # ------------------------------------------------------------------ actions
    def _on_all_toggled(self, checked: bool) -> None:
        if self._active_type is None:
            return
        if checked:
            self._selection[self._active_type] = None
            self.grid.apply_template_ids(None)
        else:
            self._selection[self._active_type] = set(self.grid.selected_template_ids())
        self._rebuild_tabs()
        self._refresh_summary()
        self._emit()

    def _on_day_part(self, key: str) -> None:
        self.grid.select_day_part(key)

    def _on_instructor(self, index: int) -> None:
        instructor_id = self.instructor_combo.itemData(index)
        if instructor_id is not None:
            self.grid.select_instructor(instructor_id)
        self.instructor_combo.setCurrentIndex(0)

    def _on_grid_changed(self) -> None:
        """Tocar la parrilla convierte la selección en horarios concretos."""
        if self._active_type is None:
            return
        self._selection[self._active_type] = set(self.grid.selected_template_ids())
        self.all_chip.blockSignals(True)
        self.all_chip.setChecked(False)
        self.all_chip.blockSignals(False)
        self._rebuild_tabs()
        self._refresh_summary()
        self._emit()

    def _emit(self) -> None:
        self.selection_changed.emit()

    # ------------------------------------------------------------------ output
    def _type_name(self, type_id: Optional[int]) -> str:
        for class_type in self._class_types:
            if class_type.get("id") == type_id:
                return class_type.get("name") or "?"
        return "?"

    def groups(self) -> List[Dict[str, Any]]:
        """La selección en la forma que entiende el predicado del backend."""
        groups: List[Dict[str, Any]] = []
        for type_id, chosen in self._selection.items():
            if chosen is None:
                groups.append({"class_type_id": type_id})
            elif chosen:
                groups.append(
                    {"class_type_id": type_id, "template_ids": sorted(chosen)}
                )
            # Una actividad marcada pero sin ningún horario elegido no puede filtrar nada;
            # se omite en vez de generar un grupo que no coincidiría con nadie.
        return groups

    def apply_groups(self, groups: List[Dict[str, Any]]) -> None:
        self._selection = {}
        for group in groups or []:
            type_id = group.get("class_type_id")
            template_ids = group.get("template_ids")
            if type_id is None:
                # A legacy spec carried a bare template list with no activity. Resolve the
                # owning activity from the catalog so reopening the campaign lights up the
                # right chips instead of showing an empty selection.
                type_id = self._owner_type_of(template_ids)
                if type_id is None:
                    continue
            self._selection[type_id] = set(template_ids) if template_ids else None
        self._active_type = next(iter(self._selection), None)
        for type_id, chip in self._type_chips.items():
            chip.blockSignals(True)
            chip.setChecked(type_id in self._selection)
            chip.blockSignals(False)
        self._rebuild_tabs()
        self._load_active_grid()

    def _owner_type_of(self, template_ids) -> Optional[int]:
        """Which activity owns these scheduled classes, per the loaded catalog."""
        wanted = set(template_ids or ())
        if not wanted:
            return None
        for type_id, templates in self._templates_by_type.items():
            if any(t.get("id") in wanted for t in templates):
                return type_id
        return None

    def clear(self) -> None:
        self.apply_groups([])

    def has_selection(self) -> bool:
        return bool(self.groups())

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        for type_id, chosen in self._selection.items():
            name = self._type_name(type_id)
            if chosen is None:
                lines.append(f"{name}: todos los horarios")
                continue
            templates = [
                t for t in self._templates_by_type.get(type_id, []) if t.get("id") in chosen
            ]
            if not templates:
                lines.append(f"{name}: sin horarios elegidos")
                continue
            times = sorted({time_label(t) for t in templates})
            days = sorted(
                {int(t.get("weekday") or 0) for t in templates},
                key=_WEEKDAY_ORDER.index,
            )
            lines.append(
                f"{name}: {_describe_days(days)} · {', '.join(times)} "
                f"— {len(templates)} clase(s)"
            )
        return lines

    def _refresh_summary(self) -> None:
        lines = self.summary_lines()
        self.summary_label.setText(
            "\n".join(lines) if lines else "Sin filtro de clase: entran todas."
        )


def _describe_days(days: List[int]) -> str:
    """'lunes a viernes' cuando el rango es continuo, la lista si no lo es."""
    if not days:
        return ""
    if len(days) == 1:
        return _WEEKDAY_LONG.get(days[0], "")
    positions = [_WEEKDAY_ORDER.index(d) for d in days]
    if positions == list(range(positions[0], positions[0] + len(positions))):
        return f"{_WEEKDAY_LONG.get(days[0], '')} a {_WEEKDAY_LONG.get(days[-1], '')}"
    return ", ".join(_WEEKDAY_LONG.get(d, "") for d in days)
