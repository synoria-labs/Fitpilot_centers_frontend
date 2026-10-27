from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from PySide6.QtCore import QDate
from app.services.chatbot_config_service import ChatbotConfigService, _map_config
from app.views.tabs import membership_purchase_orders as module
from app.models.chat import ChatMembershipSnapshot
from app.views.tabs.whatsapp.membership_chip import membership_chip_text, membership_status_category


@pytest.fixture
def panel(qtbot, monkeypatch):
    calls, dialogs = [], []
    def execute(_self, service, method, success, failure, **kwargs):
        calls.append(SimpleNamespace(method=method, success=success, failure=failure, kwargs=kwargs))
    monkeypatch.setattr(module.BaseController, "_execute_authenticated_operation", execute)
    monkeypatch.setattr(module, "show_info", lambda *a, **k: dialogs.append(a[1]))
    monkeypatch.setattr(module, "show_error", lambda *a, **k: dialogs.append(a[1]))
    widget = module.MembershipPurchaseOrdersPanel(SimpleNamespace())
    qtbot.addWidget(widget)
    return SimpleNamespace(widget=widget, calls=calls, dialogs=dialogs)


def row(**kwargs):
    return dict(id=4, participantName="Cliente", planName="Semanal", amount=200, status="paid_awaiting_start",
                startDate="2026-10-27", paymentId=9, actionType="buy_package") | kwargs


def test_refresh_only_reads_and_review_orders_cannot_be_applied(panel):
    p = panel.widget
    p.refresh.click()
    assert panel.calls[-1].method == "list_purchase_orders"
    panel.calls[-1].success([row(status="needs_review", reviewReason="Revisar el importe")])
    p.table.selectRow(0)
    assert not p.confirm.isEnabled()
    assert p.table.item(0, 5).text() == "Revisar el importe"
    assert all(c.method == "list_purchase_orders" for c in panel.calls)


@pytest.mark.parametrize("confirmed", [False, True])
def test_staff_must_confirm_selected_date_before_reusing_payment(panel, monkeypatch, confirmed):
    p = panel.widget
    p._loaded([row()])
    p.table.selectRow(0)
    p.date.setDate(QDate(2026, 11, 3))
    monkeypatch.setattr(module, "show_confirmation", lambda *a, **k: confirmed)
    p.confirm.click()
    applies = [c for c in panel.calls if c.method == "confirm_purchase_start"]
    assert len(applies) == int(confirmed)
    if confirmed:
        assert applies[0].kwargs == dict(order_id=4, start_date="2026-11-03", session_id=None)
        applies[0].success({"success": True, "message": "Registro listo, sin nuevo cobro"})
        assert panel.calls[-1].method == "list_purchase_orders"


def test_daily_start_selection_ignores_stale_options(panel):
    p = panel.widget
    p._loaded([row(actionType="buy_day_pass")])
    p.table.selectRow(0)
    first = panel.calls[-1]
    p.date.setDate(QDate(2026, 11, 4))
    newer = panel.calls[-1]
    first.success([dict(sessionId=1, label="Clase anterior")])
    assert p.sessions.count() == 0
    newer.success([dict(sessionId=2, label="04/11/2026 09:00")])
    assert p.sessions.currentData() == 2 and p.confirm.isEnabled()


def test_future_membership_has_distinct_chip():
    snapshot = ChatMembershipSnapshot(status="scheduled", remaining_days=7)
    assert membership_chip_text(snapshot) == "Por iniciar"
    assert membership_status_category(snapshot) == "scheduled"


@pytest.mark.asyncio
async def test_config_preserves_haiku_and_roundtrips_in_person_flags():
    client = SimpleNamespace(execute=AsyncMock(return_value={"saveChatbotConfig": {"success": True}}))
    service = ChatbotConfigService(client)
    await service.save_config(enabled=True, require_confirmation=True, require_mp_payment=True,
        model="claude-haiku-5-5", system_prompt="Persona", offer_in_person_registration=True, sales_v2_enabled=True)
    data = client.execute.call_args.args[1]["input"]
    assert data["offerInPersonRegistration"] and data["salesV2Enabled"]
    assert data["model"] == "claude-haiku-5-5"
    mapped = _map_config(dict(offerInPersonRegistration=True, salesV2Enabled=True, model="claude-haiku-5-5"))
    assert mapped["offer_in_person_registration"] and mapped["sales_v2_enabled"]


@pytest.mark.asyncio
async def test_reconfirmation_api_never_sends_a_payment_amount_or_new_checkout():
    client = SimpleNamespace(execute=AsyncMock(return_value={"confirmMembershipPurchaseStart": {"success": True}}))
    service = ChatbotConfigService(client)
    await service.confirm_purchase_start(4, "2026-11-03", 99)
    query, values = client.execute.call_args.args
    assert values == dict(id=4, date="2026-11-03", session=99)
    assert "confirmMembershipPurchaseStart" in query
    assert "createPreference" not in query
