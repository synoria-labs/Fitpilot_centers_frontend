"""Pruebas del selector de clases de campañas, con Qt real en modo offscreen.

Cubren el gesto que motiva la parrilla — un clic en la hora selecciona todos sus días — y el
contrato con el backend: lo que produce ``groups()`` es exactamente lo que entiende el
predicado ``class_affinity``.
"""
from __future__ import annotations

import pytest

from app.views.tabs.campaigns.class_picker import ClassPicker, ScheduleGrid

SPINNING, YOGA = 7, 9


def _template(tid, type_id, weekday, hhmm, instructor=None):
    return {
        "id": tid,
        "class_type_id": type_id,
        "class_type_name": "Spinning" if type_id == SPINNING else "Yoga",
        "weekday": weekday,
        "start_time_local": f"{hhmm}:00",
        "instructor_id": instructor,
        "instructor_name": {12: "Laura"}.get(instructor),
        "name": None,
        "is_active": True,
    }


# Spinning: L-V a las 08:00 (Laura imparte L/M/X) y M/J a las 19:00. Yoga: X a las 09:00.
CLASS_TYPES = [{"id": SPINNING, "name": "Spinning"}, {"id": YOGA, "name": "Yoga"}]
TEMPLATES = [
    _template(11, SPINNING, 1, "08:00", 12),
    _template(12, SPINNING, 2, "08:00", 12),
    _template(13, SPINNING, 3, "08:00", 12),
    _template(14, SPINNING, 4, "08:00"),
    _template(15, SPINNING, 5, "08:00"),
    _template(16, SPINNING, 2, "19:00"),
    _template(17, SPINNING, 4, "19:00"),
    _template(31, YOGA, 3, "09:00"),
]


@pytest.fixture
def picker(qtbot) -> ClassPicker:
    widget = ClassPicker()
    qtbot.addWidget(widget)
    widget.set_classes(CLASS_TYPES, TEMPLATES)
    return widget


def _select_activity(picker: ClassPicker, type_id: int) -> None:
    picker._type_chips[type_id].setChecked(True)


def _grid(picker: ClassPicker) -> ScheduleGrid:
    return picker.grid


def test_choosing_an_activity_defaults_to_all_of_it(picker):
    _select_activity(picker, SPINNING)
    assert picker.groups() == [{"class_type_id": SPINNING}]
    assert picker.summary_lines() == ["Spinning: todos los horarios"]


def test_clicking_the_hour_selects_every_day_at_that_hour(picker):
    """El gesto que reemplaza marcar una casilla por día."""
    _select_activity(picker, SPINNING)
    _grid(picker)._toggle_row("08:00")

    assert picker.groups() == [
        {"class_type_id": SPINNING, "template_ids": [11, 12, 13, 14, 15]}
    ]
    assert picker.summary_lines() == ["Spinning: lunes a viernes · 08:00 — 5 clase(s)"]


def test_clicking_the_hour_again_clears_the_row(picker):
    _select_activity(picker, SPINNING)
    _grid(picker)._toggle_row("08:00")
    _grid(picker)._toggle_row("08:00")
    assert _grid(picker).selected_template_ids() == []


def test_clicking_the_day_selects_every_hour_of_that_day(picker):
    _select_activity(picker, SPINNING)
    _grid(picker)._toggle_column(2)  # martes: 08:00 y 19:00
    assert picker.groups() == [{"class_type_id": SPINNING, "template_ids": [12, 16]}]


def test_day_part_covers_hours_that_do_not_line_up(picker):
    """La franja es útil justo porque agrupa horas distintas de la parrilla."""
    _select_activity(picker, SPINNING)
    _grid(picker).select_day_part("evening")  # >= 18:00
    assert picker.groups() == [{"class_type_id": SPINNING, "template_ids": [16, 17]}]


def test_instructor_selects_their_classes(picker):
    _select_activity(picker, SPINNING)
    _grid(picker).select_instructor(12)
    assert picker.groups() == [{"class_type_id": SPINNING, "template_ids": [11, 12, 13]}]


def test_each_activity_keeps_its_own_schedule_selection(picker):
    _select_activity(picker, SPINNING)
    _grid(picker)._toggle_row("08:00")
    _select_activity(picker, YOGA)          # cambia la parrilla activa

    groups = {g["class_type_id"]: g for g in picker.groups()}
    assert groups[SPINNING]["template_ids"] == [11, 12, 13, 14, 15]
    assert "template_ids" not in groups[YOGA]   # Yoga sigue en "toda la actividad"


def test_selection_survives_save_and_reopen(picker, qtbot):
    """Guardar y reabrir una campaña debe devolver exactamente la misma selección."""
    _select_activity(picker, SPINNING)
    _grid(picker)._toggle_row("08:00")
    _select_activity(picker, YOGA)
    saved = picker.groups()

    reopened = ClassPicker()
    qtbot.addWidget(reopened)
    reopened.set_classes(CLASS_TYPES, TEMPLATES)
    reopened.apply_groups(saved)

    assert reopened.groups() == saved


def test_legacy_template_only_spec_resolves_its_activity(picker):
    """Una campaña guardada antes de la parrilla no debe abrirse con la selección vacía."""
    picker.apply_groups([{"class_type_id": None, "template_ids": [16, 17]}])
    assert picker.groups() == [{"class_type_id": SPINNING, "template_ids": [16, 17]}]


def test_activity_with_no_hours_chosen_does_not_filter(picker):
    """Un grupo sin horarios no coincidiría con nadie; se omite en vez de vaciar la audiencia."""
    _select_activity(picker, SPINNING)
    picker.all_chip.setChecked(False)   # pasa de "todos" a selección explícita, aún vacía
    assert picker.groups() == []
    assert picker.summary_lines() == ["Spinning: sin horarios elegidos"]


def test_grid_only_shows_days_that_have_classes(picker):
    """Yoga solo corre en miércoles: la parrilla no debe dibujar la semana entera."""
    _select_activity(picker, YOGA)
    assert set(_grid(picker)._cells) == {("09:00", 3)}


def test_no_selection_means_no_class_filter(picker):
    assert picker.groups() == []
    assert not picker.has_selection()
