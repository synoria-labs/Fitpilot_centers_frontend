from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.campaigns_service import CampaignsService, _map_metrics
from app.views.tabs.campaigns.button_metrics_panel import CampaignButtonsPanel
from tests.test_campaign_delivery_recovery import screen  # noqa: F401 - shared async-controller fixture


def report():
    return dict(button_clicks=3, button_clickers=1, converted_clickers=1, text_replies=2, text_reply_people=1,
                total=3, offset=0, limit=50, updated_at="2026-10-23T18:00:00+00:00", buttons=[
                    dict(key="reserve", label="Quiero reservar", measurable=True, clicks=2,
                         unique_people=1, converted_people=1),
                    dict(key="info", label="Más información", measurable=True, clicks=1,
                         unique_people=1, converted_people=1, historical=True),
                    dict(key="url", label="Pagar ahora", measurable=False, clicks=None,
                         unique_people=None, converted_people=None)], items=[
                    dict(person_name="Ana", phone="528710000001", button_label="Quiero reservar",
                         clicked_at="2026-10-23T17:00:00+00:00", converted=True,
                         converted_at="2026-10-23T18:00:00+00:00")])


def test_panel_distinguishes_clicks_people_text_and_unmeasured_links(qtbot):
    panel = CampaignButtonsPanel()
    qtbot.addWidget(panel)
    panel.set_analytics(report())
    assert "Pulsaciones: 3 · Personas únicas: 1" in panel.summary.text()
    assert "Respuestas escritas a la campaña: 2" in panel.summary.text()
    assert panel.buttons_table.item(0, 1).text() == "2"
    assert panel.buttons_table.item(1, 0).text() == "Más información (histórico)"
    assert "sin medición" in panel.buttons_table.item(2, 0).text()
    assert panel.buttons_table.item(2, 1).text() == "—"
    assert panel.people_table.item(0, 0).text() == "Ana"
    assert panel.people_table.item(0, 3).text() == "23/10/2026 11:00"
    assert panel.people_table.item(0, 4).text() == "23/10/2026 12:00"
    assert "causalidad" in panel.source.text()
    assert not panel.next_btn.isEnabled()


def test_filters_paging_and_refresh_are_read_only(screen):
    panel = screen.tab.button_metrics_panel
    panel.set_analytics(report() | {"total": 61})
    panel.next_btn.click()
    assert screen.calls[-1].method == "get_button_analytics"
    assert screen.calls[-1].kwargs == dict(campaign_id=3, button_key=None, offset=50)
    screen.calls[-1].success(report() | {"total": 61, "offset": 50})
    panel.button_filter.setCurrentIndex(1)
    assert screen.calls[-1].kwargs == dict(campaign_id=3, button_key="reserve", offset=0)
    screen.calls[-1].success(report() | {"total": 2})
    assert panel.selected_key() == "reserve"
    panel.refresh_btn.click()
    assert all(call.method == "get_button_analytics" for call in screen.calls)


def test_stale_campaign_filter_and_page_responses_are_ignored(screen):
    panel = screen.tab.button_metrics_panel
    panel.set_analytics(report() | {"total": 61})
    panel.refresh_btn.click()
    original = screen.calls[-1]
    panel.next_btn.click()
    next_page = screen.calls[-1]
    original.success(report() | {"button_clicks": 999})
    assert "999" not in panel.summary.text()
    next_page.success(report() | {"total": 61, "offset": 50})
    assert panel.offset == 50
    panel.button_filter.setCurrentIndex(1)
    original.success(report() | {"button_clicks": 999})
    assert "999" not in panel.summary.text()
    screen.tab._populate_editor(dict(id=4, name="Otra", status="completed", objective="broadcast"))
    next_page.success(report() | {"button_clicks": 999})
    assert panel.people_table.rowCount() == 0 and "999" not in panel.summary.text()


def test_error_never_becomes_zero_or_keeps_old_people(screen):
    panel = screen.tab.button_metrics_panel
    panel.set_analytics(report())
    panel.refresh_btn.click()
    screen.calls[-1].failure("Sin permiso")
    assert "Sin permiso" in panel.summary.text()
    assert panel.people_table.rowCount() == 0 and panel.buttons_table.rowCount() == 0
    assert not panel.next_btn.isEnabled()


def test_older_refresh_cannot_overwrite_newer_snapshot_for_the_same_filter(screen):
    panel = screen.tab.button_metrics_panel
    panel.refresh_btn.click()
    older = screen.calls[-1]
    panel.refresh_btn.click()
    newer = screen.calls[-1]
    newer.success(report() | {"button_clicks": 7})
    older.success(report() | {"button_clicks": 999})
    assert "Pulsaciones: 7" in panel.summary.text() and "999" not in panel.summary.text()


def test_metrics_refresh_requests_current_button_filter(screen):
    panel = screen.tab.button_metrics_panel
    panel.set_analytics(report())
    panel.button_filter.setCurrentIndex(1)
    screen.calls.clear()
    screen.tab._on_metrics({})
    assert screen.calls[-1].kwargs == dict(campaign_id=3, button_key="reserve", offset=0)
    screen.tab._on_new_clicked()
    assert panel.people_table.rowCount() == 0 and panel.selected_key() is None
    assert not panel.isVisible()


@pytest.mark.asyncio
async def test_service_preserves_nullable_counts_and_requests_exact_campaign_page():
    client = SimpleNamespace(execute=AsyncMock(return_value={"campaignButtonAnalytics": dict(
        buttonClicks=3, buttonClickers=1, textReplies=2, textReplyPeople=1, convertedClickers=1,
        total=2, limit=50, offset=0, updatedAt="2026-10-23T18:00:00Z", buttons=[
            dict(key="url", label="Pagar", kind="URL", measurable=False, clicks=None,
                 uniquePeople=None, convertedPeople=None)], items=[
            dict(personName="Ana", phone="52871", buttonLabel="Reservar", clickedAt="2026-10-23T17:00:00Z")])}))
    service = CampaignsService(client)
    data = await service.get_button_analytics(3, button_key="url", offset=50)
    assert data["button_clicks"] == 3 and data["buttons"][0]["unique_people"] is None
    assert data["items"][0]["person_name"] == "Ana"
    query, variables = client.execute.call_args.args
    assert "campaignButtonAnalytics" in query and "clickedAt" in query
    assert variables == dict(id=3, key="url", offset=50, limit=50)
    assert _map_metrics(dict(buttonClicks=3))["button_clicks"] == 3
    client.execute.return_value = {}
    assert (await service.get_button_analytics(3))["error"]
