"""Real Qt renewal forms, async load order and administrator retry contract."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.controllers.pos_controller import PosController
from app.controllers.renew_subscription_controller import RenewSubscriptionController
from app.models.base import MembershipPlan
from app.services.pos_service import PosService
from app.views.dialogs.pos_renewal_line_dialog import PosRenewalLineDialog
from app.views.widgets import day_pass_session_picker as picker_module
from app.views.widgets.pos_checkout_panel import PosCheckoutPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def loads(monkeypatch):
    pending = []
    def capture(*args, **kwargs):
        pending.append(kwargs)
        return SimpleNamespace()
    monkeypatch.setattr(picker_module, "start_authenticated_operation", capture)
    return pending


@pytest.mark.parametrize("member_first", [False, True])
@pytest.mark.parametrize("selected_plan", ["Semanal", "Mensual"])
def test_preselected_fixed_plan_shows_schedule_without_toggling(qapp, loads, member_first, selected_plan):
    controller = RenewSubscriptionController(SimpleNamespace(client=object()))
    dialog = PosRenewalLineDialog(controller, 41)
    plans = [MembershipPlan(id=5, name="Diario", price=50, duration_value=1, duration_unit="day")]
    plans.extend(MembershipPlan(id=i, name=name, price=200, duration_value=value, duration_unit=unit,
                                fixed_time_slot=True)
                 for i, name, value, unit in [(4, "Semanal", 7, "day"), (2, "Mensual", 1, "month")])
    payload = {"member": {"full_name": "Socio"}, "active_membership": {
        "plan_name": selected_plan, "end_date": datetime.now().astimezone() - timedelta(days=75),
    }}
    if member_first:
        dialog._on_member_data_loaded(payload)
    dialog._on_plans_loaded_renewal(plans)
    if not member_first:
        dialog._on_member_data_loaded(payload)
    assert dialog.plan_combo.currentData().name == selected_plan
    assert not dialog.class_combo.isHidden()
    assert not dialog.class_combo.parentWidget().layout().labelForField(dialog.class_combo).isHidden()
    assert not hasattr(dialog, "_daily_picker") or dialog._daily_picker.isHidden()
    assert dialog.start_date.date() == picker_module.QDate.currentDate()
    dialog.plan_combo.setCurrentIndex(0)
    assert dialog.class_combo.isHidden() and not dialog._daily_picker.isHidden()
    assert dialog.class_combo.parentWidget().layout().labelForField(dialog.class_combo).isHidden()
    dialog.close()


@pytest.mark.parametrize("own_reservation", [False, True])
def test_past_day_pass_can_be_selected_and_own_place_is_kept(qapp, loads, own_reservation):
    picker = picker_module.DayPassSessionPicker(object(), member_id=41)
    day = picker_module.QDate.currentDate().addDays(-1)
    picker.date_edit.setDate(day)
    request = loads[-1]
    assert request["start_date"] < request["end_date"]
    assert request["include_completed"] is True and request["person_id"] == 41
    start = datetime.combine(day.toPython(), datetime.min.time(), tzinfo=picker_module.STUDIO_ZONE)
    request["on_success"]([{
        "id": 77, "name": "Spinning", "startAt": start.isoformat(),
        "endAt": (start + timedelta(hours=1)).isoformat(),
        "availableSpots": 0 if own_reservation else 1, "hasReservation": own_reservation,
    }])
    assert picker.combo.isEnabled()
    picker.combo.setCurrentIndex(1)
    assert picker.session_id() == 77
    picker.close()


def test_pos_requests_admin_only_for_overlap_and_invalid_password(qapp):
    controller = PosController(None, None, None)
    requests, errors, sales = [], [], []
    controller.admin_authorization_required.connect(requests.append)
    controller.error_occurred.connect(errors.append)
    controller.sale_completed.connect(sales.append)
    for code in ("MEMBERSHIP_OVERLAP", "ADMIN_PASSWORD_INVALID"):
        controller._on_sale_done({"success": False, "error_code": code, "message": code})
    controller._on_sale_done({"success": False, "message": "Sin cupo"})
    controller._on_sale_done({"success": True, "sale": {"id": 1}})
    assert requests == ["MEMBERSHIP_OVERLAP", "ADMIN_PASSWORD_INVALID"]
    assert errors == ["Sin cupo"] and sales == [{"id": 1}]


@pytest.mark.parametrize("accepted", [False, True])
def test_checkout_admin_cancel_does_not_charge_and_accept_retries_same_cart(monkeypatch, accepted):
    from app.views.dialogs import admin_password_dialog
    class Dialog:
        password = "test-password"
        def __init__(self, *args, **kwargs):
            assert kwargs["confirm_text"] == "Autorizar y cobrar"
        def exec(self):
            return accepted
    monkeypatch.setattr(admin_password_dialog, "AdminPasswordDialog", Dialog)
    calls = []
    checkout = SimpleNamespace(_lines=[{"plan_id": 4}], _tenders=[{"amount": 200}],
                               _current_member={"id": 18},
                               controller=SimpleNamespace(finalize_sale=lambda *a, **kw: calls.append((a, kw))))
    PosCheckoutPanel._on_admin_authorization_required(checkout, "Hay solapamiento")
    assert len(calls) == int(accepted)
    if accepted:
        assert calls[0][0][0] is checkout._lines
        assert calls[0][1] == {"admin_password": "test-password"}
        assert "admin_password" not in checkout._lines[0]


@pytest.mark.asyncio
async def test_pos_adapter_forwards_password_outside_line_items_and_retains_error_code():
    calls = []
    class Client:
        async def execute(self, query, variables):
            calls.append(variables["input"])
            return {"createSale": {"success": False, "message": "Requiere autorización", "errorCode": "MEMBERSHIP_OVERLAP"}}
    result = await PosService(Client()).create_sale(
        [{"line_type": "membership_renewal", "plan_id": 4}], [{"method": "cash", "amount": 200}],
        admin_password="test-password",
    )
    assert result["error_code"] == "MEMBERSHIP_OVERLAP"
    assert calls[0]["adminPassword"] == "test-password"
    assert "adminPassword" not in calls[0]["lineItems"][0]


@pytest.mark.asyncio
async def test_fixed_seat_adapter_identifies_the_renewing_member():
    from app.services.standing_bookings_service import StandingBookingsService
    calls = []
    class Client:
        async def execute(self, query, variables):
            calls.append(variables["input"])
            return {"templateAvailableSeats": {"seats": []}}
    await StandingBookingsService(Client()).get_available_seats(1, person_id=18)
    assert calls[0]["personId"] == 18


def test_renewal_controller_supplies_member_for_own_seat_availability(qapp, monkeypatch):
    controller = RenewSubscriptionController(SimpleNamespace(client=object()))
    monkeypatch.setattr(controller, "_load_data_intelligently", lambda member: None)
    controller.load_defaults(18)
    assert controller.subscription_service.person_id == 18
