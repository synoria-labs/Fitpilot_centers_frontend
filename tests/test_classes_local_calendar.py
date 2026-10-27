"""The calendar places evening bookings on their Mexico date, not the UTC date."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Config
from app.utils.datetime_helpers import to_local_datetime
from app.views.tabs import classes_tab as tab_module
from app.views.widgets.class_row_widget import ClassRowWidget

STUDIO = ZoneInfo("America/Mexico_City")


@pytest.fixture
def classes_tab(qtbot, monkeypatch):
    monkeypatch.setattr(Config, "TIMEZONE", "America/Mexico_City")
    monkeypatch.setattr(tab_module.container, "get", lambda name: None)
    monkeypatch.setattr(tab_module.ClassesTab, "_load_class_types", lambda self: None)
    widget = tab_module.ClassesTab()
    qtbot.addWidget(widget)
    widget._current_week_start = date(2026, 11, 2)
    widget._current_week_end = date(2026, 11, 8)
    widget._current_schedule = tab_module.ScheduleGroup("18:00", "Spinning", "18:00", [8, 13])
    return widget


def session(day, hour=18, *, occupied=True, ident=4329):
    start = datetime.combine(day, datetime.min.time(), tzinfo=STUDIO) + timedelta(hours=hour)
    return {
        "id": ident, "templateId": 8, "name": "Spinning", "capacity": 2,
        "startAt": start.astimezone(timezone.utc).isoformat(),
        "endAt": (start + timedelta(hours=1)).astimezone(timezone.utc).isoformat(),
        "seats": [
            {"seatId": 1, "label": "Bicicleta 1", "status": "free"},
            {"seatId": 2, "label": "Bicicleta 2", "status": "occupied" if occupied else "free",
             "occupant": {"personId": 359, "fullName": "Socia de prueba"} if occupied else None},
        ],
    }


def test_next_monday_reservation_stays_on_monday_and_tuesday_is_free(classes_tab):
    monday, tuesday = date(2026, 11, 2), date(2026, 11, 3)
    payload = [session(monday), session(tuesday, occupied=False, ident=4418)]
    classes_tab._on_sessions_loaded(payload)
    assert set(classes_tab._sessions_by_day) == {monday, tuesday}
    assert classes_tab._selected_sessions[monday]["id"] == 4329
    assert classes_tab._selected_sessions[monday]["start_at"].strftime("%H:%M") == "18:00"
    assert classes_tab._selected_sessions[monday]["end_at"].strftime("%H:%M") == "19:00"
    # Check actual visible seat widgets, not just the intermediate date map.
    layout = classes_tab.weekly_grid.grid_layout
    monday_bike = layout.itemAtPosition(1, 3).widget()
    tuesday_bike = layout.itemAtPosition(2, 3).widget()
    assert monday_bike.status == "occupied" and monday_bike.occupant_name == "Socia de prueba"
    assert tuesday_bike.status == "free" and tuesday_bike.occupant_name is None
    assert payload[0]["startAt"] == "2026-11-03T00:00:00+00:00"


@pytest.mark.parametrize("day,hour", [
    (date(2026, 11, 2), 8),
    (date(2026, 11, 2), 18),
    (date(2026, 11, 2), 19),
    (date(2026, 11, 2), 20),
    (date(2026, 11, 2), 21),
    (date(2026, 11, 8), 23),
])
def test_calendar_keeps_studio_day_for_morning_evening_and_last_day_of_week(classes_tab, day, hour):
    classes_tab._on_sessions_loaded([session(day, hour)])
    assert list(classes_tab._sessions_by_day) == [day]
    assert classes_tab.weekly_grid.sessions_by_day[day]["start_at"].hour == hour
    assert day + timedelta(days=1) not in classes_tab._sessions_by_day


@pytest.mark.parametrize("value", [
    "2026-11-03T00:00:00Z",
    "2026-11-03T00:00:00+00:00",
    "2026-11-02T18:00:00-06:00",
    datetime(2026, 11, 3, tzinfo=timezone.utc),
    datetime(2026, 11, 3),
])
def test_local_datetime_accepts_server_encodings_independently_of_pc_timezone(value, monkeypatch):
    monkeypatch.setattr(Config, "TIMEZONE", "America/Mexico_City")
    converted = to_local_datetime(value)
    assert converted.date() == date(2026, 11, 2) and converted.hour == 18


def test_class_row_formats_evening_and_overnight_ranges_in_studio_time(monkeypatch):
    monkeypatch.setattr(Config, "TIMEZONE", "America/Mexico_City")
    assert ClassRowWidget._format_time_range(None, "2026-11-03T00:00:00Z", "2026-11-03T01:00:00Z") == "18:00 - 19:00"
    assert ClassRowWidget._format_time_range(None, "2026-11-03T05:30:00Z", "2026-11-03T06:30:00Z") == "23:30 - 00:30"
