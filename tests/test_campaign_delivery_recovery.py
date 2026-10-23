from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.controllers.campaigns_controller import CampaignsController
from app.services.campaigns_service import CampaignsService, _map_campaign, _map_metrics
from app.views.tabs.campaigns import campaigns_tab
from app.views.tabs.campaigns.panels import DeliveryPolicyPanel, MetricsPanel, RecipientsTable


@pytest.fixture
def screen(qtbot, monkeypatch):
    calls, dialogs = [], []

    def execute(_self, service, method, success, failure, **kwargs):
        calls.append(SimpleNamespace(method=method, success=success, failure=failure, kwargs=kwargs))

    monkeypatch.setattr(CampaignsController, "_execute_authenticated_operation", execute)
    monkeypatch.setattr(campaigns_tab.container, "get", lambda _: SimpleNamespace(has_capability=lambda _: True))
    monkeypatch.setattr(campaigns_tab, "show_error", lambda *args, **kwargs: dialogs.append(args[1]))
    monkeypatch.setattr(campaigns_tab, "show_info", lambda *args, **kwargs: dialogs.append(args[1]))
    tab = campaigns_tab.CampaignsTab()
    qtbot.addWidget(tab)
    campaign = dict(id=3, name="Halloween", status="completed", objective="broadcast",
                    daily_cap_policy="respect", auto_retry_meta_limits=False, recency_block_days=30)
    tab._campaigns_by_id[3] = campaign
    tab._populate_editor(campaign)
    tab._preview_timer.stop()
    calls.clear()
    yield SimpleNamespace(tab=tab, calls=calls, dialogs=dialogs)
    tab._preview_timer.stop()
    tab._live_timer.stop()


@pytest.mark.parametrize("policy", ["respect", "defer", "allow_additional"])
def test_delivery_panel_roundtrips_each_policy(qtbot, policy):
    panel = DeliveryPolicyPanel()
    qtbot.addWidget(panel)
    panel.load(dict(daily_cap_policy=policy, auto_retry_meta_limits=False, recency_block_days=7))
    assert panel.values() == dict(dailyCapPolicy=policy, autoRetryMetaLimits=False)
    assert panel.recency.value() == 7


def test_save_policy_does_not_start_campaign_or_recovery(screen):
    screen.tab.delivery_panel.policy.setCurrentIndex(2)
    screen.tab._save_delivery_policy()
    assert [call.method for call in screen.calls] == ["update_campaign"]
    assert screen.calls[0].kwargs["payload"] == dict(dailyCapPolicy="allow_additional", autoRetryMetaLimits=False)


def test_recovery_requires_saving_changed_policy_first(screen):
    screen.tab.delivery_panel.policy.setCurrentIndex(2)
    screen.tab._preview_recovery()
    assert not screen.calls
    assert "Guarda la política" in screen.dialogs[0]


@pytest.mark.parametrize("confirm", [False, True])
def test_recovery_only_runs_after_preview_and_explicit_action(screen, monkeypatch, confirm):
    screen.tab._preview_recovery()
    call = screen.calls[-1]
    assert call.method == "preview_recovery"
    monkeypatch.setattr(campaigns_tab, "show_confirmation", lambda *args, **kwargs: confirm)
    call.success(dict(eligible=2, delivered=241, duplicates=30, review=72, blocked=0, scheduled=1,
                      recipients=[dict(send_after="2026-10-24T15:00:00+00:00")]))
    assert sum(c.method == "recover_recipients" for c in screen.calls) == int(confirm)


def test_preview_for_previous_selection_cannot_recover_new_selection(screen, monkeypatch):
    screen.tab._preview_recovery()
    old = screen.calls[-1]
    screen.tab._editing_id = 4
    monkeypatch.setattr(campaigns_tab, "show_confirmation", lambda *args, **kwargs: pytest.fail("stale dialog"))
    old.success(dict(eligible=20))
    assert not any(c.method == "recover_recipients" for c in screen.calls)


def test_failed_recovery_does_not_report_a_successful_send(screen):
    results, errors = [], []
    screen.tab.controller.action_result.connect(results.append)
    screen.tab.controller.error_occurred.connect(errors.append)
    screen.tab.controller.recover_recipients(3)
    screen.calls[-1].success({"success": False, "error": "El evento ya comenzó."})
    assert not results and errors == ["El evento ya comenzó."]


def test_successful_recovery_refreshes_metrics_and_recipient_details(screen):
    screen.tab._on_action({"success": True, "pending": 3})
    assert {call.method for call in screen.calls} == {"list_campaigns", "get_metrics", "list_recipients"}


@pytest.mark.parametrize("state,enabled", [("sending", False), ("canceled", False),
                                        ("scheduled", True), ("paused", True), ("completed", True)])
def test_delivery_controls_respect_campaign_state(screen, state, enabled):
    screen.tab._status = state
    screen.tab._apply_state()
    assert screen.tab.delivery_panel.isEnabled() is enabled
    assert screen.tab.delivery_panel.recover_button.isEnabled() is enabled


def test_new_campaign_enables_bounded_meta_retry_but_legacy_does_not(screen):
    assert not screen.tab.delivery_panel.retry_meta.isChecked()
    screen.tab._on_new_clicked()
    assert screen.tab.delivery_panel.retry_meta.isChecked()
    assert screen.tab._collect_payload()["dailyCapPolicy"] == "respect"


def test_audience_preview_uses_current_campaign_and_settings(screen):
    screen.tab.delivery_panel.policy.setCurrentIndex(1)
    screen.tab._request_preview()
    call = screen.calls[-1]
    assert call.kwargs["campaign_id"] == 3
    assert call.kwargs["recency_block_days"] == 30
    assert call.kwargs["daily_cap_policy"] == "defer"


def test_metrics_and_recipient_history_show_evidence_and_local_time(qtbot):
    metrics = MetricsPanel()
    qtbot.addWidget(metrics)
    mapped = _map_metrics(dict(accepted=327, sent=255, delivered=241, rejected=72,
                              errorCounts={"131049": 4}, templateId=13,
                              updatedAt="2026-10-23T18:00:00+00:00", uniquePhones=332))
    metrics.set_metrics(mapped)
    assert "332" in metrics.detail_label.text()
    assert "131049: 4" in metrics.detail_label.text()
    assert "12:00" in metrics.detail_label.text()
    table = RecipientsTable()
    qtbot.addWidget(table)
    table.set_recipients([dict(phone_e164="+52871", status="pending", skip_reason="meta_retry",
                               send_after="2026-10-24T15:00:00+00:00",
                               attempts=[dict(state="failed", error_code=131049, error_detail="Original rejection",
                                              started_at="2026-10-23T15:00:00+00:00")])])
    assert table.table.item(0, 4).text() == "1"
    assert "131049" in table.table.item(0, 4).toolTip()
    assert table.table.item(0, 5).text() == "24/10/2026 09:00"


@pytest.mark.asyncio
async def test_service_maps_policy_false_and_requests_recovery_preview():
    node = dict(id=3, dailyCapPolicy="defer", autoRetryMetaLimits=False)
    assert _map_campaign(node)["auto_retry_meta_limits"] is False
    client = SimpleNamespace(execute=AsyncMock(return_value={"previewCampaignRecovery": {"eligible": 3}}))
    service = CampaignsService(client)
    assert (await service.preview_recovery(3))["eligible"] == 3
    assert client.execute.call_args.args[1] == {"id": 3}


def recovery_preview():
    return dict(causes=[
        dict(key='daily_cap', label='Ya recibió marketing ese día', total=2, eligible=1, blocked=1,
             selected_by_default=True, note='Política: reprogramar al próximo día permitido.'),
        dict(key='unconfirmed', label='Aceptado sin confirmar entrega', total=1, eligible=1, blocked=0,
             selected_by_default=False, note='Puede duplicar un mensaje; espera mínima de 24 h.'),
        dict(key='bad_number', label='Número inválido o sin WhatsApp', total=1, eligible=0, blocked=1,
             selected_by_default=True, note='Corrige su número en Socios.'),
    ], recipients=[
        dict(recipient_id=1, person_name='Cliente de ejemplo', phone='+52 871 000 0001', cause='daily_cap',
             detail='Omitido por límite local.', eligible=True, send_after='2026-10-24T15:00:00+00:00'),
        dict(recipient_id=2, person_name='Número compartido', phone='+52 871 000 0001', cause='daily_cap',
             detail='Límite diario.', eligible=False, blocked_reason='Número repetido en esta campaña.'),
        dict(recipient_id=3, person_name='Entrega incierta', phone='+52 871 000 0003', cause='unconfirmed',
             detail='Sin confirmación de Meta.', eligible=True, send_after='2026-10-24T15:00:00+00:00'),
        dict(recipient_id=4, person_name='Número incompleto', phone='1234', cause='bad_number',
             detail='(#100) Invalid parameter', eligible=False, blocked_reason='Corrige su número en Socios.'),
    ])


def test_recovery_dialog_defaults_filter_locally_and_show_local_dates(qtbot):
    from app.views.tabs.campaigns.recovery_dialog import RecoveryDialog
    dialog = RecoveryDialog(recovery_preview())
    qtbot.addWidget(dialog)
    assert dialog.selected_causes() == ['daily_cap', 'bad_number']
    assert dialog.table.rowCount() == 3
    assert dialog.confirm_button.text() == 'Programar reenvío (1)'
    assert '24/10/2026 09:00' in [dialog.table.item(row, 4).text() for row in range(dialog.table.rowCount())]
    dialog.cause_checks['unconfirmed'].setChecked(True)
    assert dialog.table.rowCount() == 4 and dialog.confirm_button.text() == 'Programar reenvío (2)'
    dialog.cause_checks['daily_cap'].setChecked(False)
    assert dialog.table.rowCount() == 2 and dialog.confirm_button.text() == 'Programar reenvío (1)'


def test_recovery_dialog_cannot_confirm_without_eligible_recipients(qtbot):
    from app.views.tabs.campaigns.recovery_dialog import RecoveryDialog
    preview = recovery_preview()
    for recipient in preview['recipients']:
        recipient['eligible'] = False
    dialog = RecoveryDialog(preview)
    qtbot.addWidget(dialog)
    assert not dialog.confirm_button.isEnabled()
    dialog.accept()
    assert dialog.result() == 0


def test_recovery_dialog_confirmation_passes_only_the_selected_causes(screen, monkeypatch):
    class Dialog:
        def __init__(self, result, parent):
            assert result['causes']

        def exec(self):
            return 1

        def selected_causes(self):
            return ['unconfirmed']

    monkeypatch.setattr(campaigns_tab, 'RecoveryDialog', Dialog)
    screen.tab._on_recovery_preview(3, recovery_preview())
    assert screen.calls[-1].method == 'recover_recipients'
    assert screen.calls[-1].kwargs == {'campaign_id': 3, 'causes': ['unconfirmed']}


@pytest.mark.asyncio
async def test_service_passes_empty_and_explicit_causes_and_maps_defaults():
    node = recovery_preview()
    node['causes'][0]['selectedByDefault'] = True
    client = SimpleNamespace(execute=AsyncMock(return_value={'previewCampaignRecovery': node}))
    service = CampaignsService(client)
    preview = await service.preview_recovery(3, causes=[])
    assert preview['causes'][0]['selected_by_default'] is True
    assert client.execute.call_args.args[1] == {'id': 3, 'causes': []}
    assert 'selectedByDefault' in client.execute.call_args.args[0]
    client.execute.return_value = {'recoverCampaignRecipients': {'success': True, 'pending': 1}}
    assert (await service.recover_recipients(3, causes=['bad_number']))['success']
    assert client.execute.call_args.args[1] == {'id': 3, 'causes': ['bad_number']}
