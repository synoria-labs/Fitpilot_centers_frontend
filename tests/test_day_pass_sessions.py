"""The daily sale UI selects actual sessions and sends their IDs through every adapter."""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QComboBox, QDateEdit, QLabel, QDoubleSpinBox

from app.models.base import MembershipPlan, MembershipSubscription
from app.views.dialogs.base_subscription_dialog import BaseSubscriptionDialog
from app.views.dialogs.pos_member_line_dialog import PosMembershipLineDialog
from app.views.widgets import day_pass_session_picker as picker_module
from app.services.pos_service import _line_to_input
from app.services.members_service import MembersService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def loads(monkeypatch):
    pending = []
    def start(*args, **kwargs):
        pending.append(kwargs)
        return SimpleNamespace()
    monkeypatch.setattr(picker_module, "start_authenticated_operation", start)
    return pending


def session_row(day, ident=77):
    start = datetime.combine(day, datetime.min.time(), tzinfo=picker_module.STUDIO_ZONE) + timedelta(hours=20)
    return {"id": ident, "name": "Spinning", "startAt": start.astimezone(timezone.utc).isoformat(),
            "endAt": (start + timedelta(hours=1)).isoformat(), "availableSpots": 2, "venueName": "Sala"}


def test_picker_discards_late_results_and_requires_selection(qapp, loads):
    picker = picker_module.DayPassSessionPicker(object())
    picker.date_edit.setDate(picker.date_edit.date().addDays(3))
    first = loads[-1]
    first_day = picker.date_edit.date().toPython()
    picker.date_edit.setDate(picker.date_edit.date().addDays(1))
    second = loads[-1]
    first["on_success"]([session_row(first_day)])
    assert picker.session_id() is None
    second["on_success"]([session_row(picker.date_edit.date().toPython())])
    assert picker.session_id() is None
    picker.combo.setCurrentIndex(1)
    assert picker.session_id() == 77
    assert "20:00" in picker.combo.currentText() and "21:00" in picker.combo.currentText()
    picker.close()


def test_administration_daily_form_sends_session_without_recurring_template(qapp, loads):
    dialog = BaseSubscriptionDialog()
    dialog.controller = SimpleNamespace(members_service=SimpleNamespace(client=object()))
    layout = QVBoxLayout(dialog)
    dialog.plan_combo, dialog.class_combo, dialog.seat_combo = QComboBox(), QComboBox(), QComboBox()
    dialog.seat_label, dialog.start_date, dialog.amount_input = QLabel(), QDateEdit(), QDoubleSpinBox()
    dialog.start_date.setDate(picker_module.QDate.currentDate().addDays(3))
    for widget in (dialog.plan_combo, dialog.class_combo, dialog.start_date, dialog.seat_label, dialog.seat_combo):
        layout.addWidget(widget)
    plan = MembershipPlan(id=5, name="Diario", price=50, duration_value=1, duration_unit="day")
    dialog.plan_combo.addItem("Diario", plan)
    dialog._on_plan_changed(0)
    loads[-1]["on_success"]([session_row(dialog.start_date.date().toPython())])
    dialog._daily_picker.combo.setCurrentIndex(1)
    form = {}
    dialog._append_template_and_seat(form, dialog.start_date.date().toPython())
    assert form == {"session_id": 77}
    assert dialog._validate_daily_selection()
    assert dialog.seat_combo.isHidden()
    dialog.close()


def test_pos_daily_line_selects_session_even_when_plan_has_fixed_slot(qapp, loads):
    plan = MembershipPlan(id=5, name="Diario", price=50, duration_value=1, duration_unit="day", fixed_time_slot=True)
    dialog = PosMembershipLineDialog("new", [plan], graphql_client=object())
    dialog.name_input.setText("Nueva socia")
    dialog.daily_picker.date_edit.setDate(dialog.daily_picker.date_edit.date().addDays(3))
    loads[-1]["on_success"]([session_row(dialog.daily_picker.date_edit.date().toPython())])
    dialog.daily_picker.combo.setCurrentIndex(1)
    assert dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    line = dialog.get_line()
    assert line["session_id"] == 77
    assert _line_to_input(line)["sessionId"] == 77
    assert "templateId" not in _line_to_input(line)
    dialog.close()


@pytest.mark.asyncio
async def test_membership_adapters_forward_session_id():
    calls = []
    class Client:
        async def execute(self, query, variables):
            calls.append(variables["input"])
            return {}
    service = MembersService(Client())
    await service.create_member_enrollment(full_name="Nueva", email=None, phone_number=None, plan_id=5,
        start_at=datetime.now(timezone.utc), payment_method="card", payment_amount=50, session_id=77)
    await service.renew_subscription(1, 5, session_id=78)
    assert [item["sessionId"] for item in calls] == [77, 78]
    assert all("templateId" not in item or item["templateId"] is None for item in calls)


def test_cached_subscription_expires_during_same_calendar_day():
    end = datetime.now(timezone.utc) - timedelta(minutes=1)
    sub = MembershipSubscription(id=1, person_id=1, plan_id=5, session_id=77,
        start_at=end - timedelta(hours=1), end_at=end, status="active")
    assert not sub.is_active() and sub.is_expired() and sub.status_display() == "Vencido"
    sub.status = "canceled"
    assert sub.status_display() == "Cancelado"
