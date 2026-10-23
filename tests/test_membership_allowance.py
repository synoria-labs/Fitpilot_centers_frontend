from types import SimpleNamespace

from app.models.base import MembershipPlan, TimeslotGroup
from app.views.tabs.memberships_tab import PlanDialog


def plan(kind, limit=14):
    return MembershipPlan(id=1, name="Monthly", price=600, duration_value=1, duration_unit="month",
                          plan_type=kind, fixed_time_slot=kind == "fixed_schedule", class_limit=limit)


def test_allowance_labels_distinguish_calendar_unlimited_and_credits():
    assert plan("fixed_schedule").class_allowance_display() == "Según horario y vigencia"
    assert plan("flexible").class_allowance_display() == "Sin límite (según cupo)"
    assert plan("credit_pack", 10).class_allowance_display() == "10 clases"


def test_editing_fixed_plan_does_not_reintroduce_legacy_limit(qtbot):
    dialog = PlanDialog(plan=plan("fixed_schedule"))
    qtbot.addWidget(dialog)
    assert dialog.class_limit_input.isHidden()
    assert dialog.get_data()["class_limit"] is None
    assert "incluye 5" in dialog.type_note.text() and "7" in dialog.type_note.text()


def test_unlimited_plan_has_no_hidden_caps(qtbot):
    dialog = PlanDialog(plan=plan("flexible"))
    qtbot.addWidget(dialog)
    dialog.max_day_input.setValue(1)
    dialog.max_week_input.setValue(5)
    assert dialog.max_day_input.isHidden()
    assert dialog.get_data()["class_limit"] is None
    assert dialog.get_data()["max_sessions_per_day"] is None
    assert dialog.get_data()["max_sessions_per_week"] is None


def test_credit_pack_keeps_explicit_class_count(qtbot):
    dialog = PlanDialog(plan=plan("credit_pack", 10))
    qtbot.addWidget(dialog)
    assert not dialog.class_limit_input.isHidden()
    assert dialog.get_data()["class_limit"] == 10


def test_schedule_picker_shows_all_seven_days_including_sunday():
    group = TimeslotGroup(key="test", class_type_name="Spinning", venue_name="Gym",
                         instructor_name="Laura", start_time_local="20:00",
                         templates=[SimpleNamespace(weekday=d) for d in range(7)])
    assert "7 clases/semana" in group.display_label()
    assert "Lun, Mar, Mié, Jue, Vie, Sáb, Dom" in group.display_label()
    assert "Dom" in group.display_tooltip()
    assert group.template_for_weekday(7).weekday == 0
