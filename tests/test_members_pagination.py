from __future__ import annotations

from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QCoreApplication

from app.controllers.members_controller import MembersController
from app.models.base import Member
from app.services.members_service import MembersService


class _FakeGraphQLClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def execute(self, query, variables=None, use_auth=True):
        self.calls.append({"query": query, "variables": variables, "use_auth": use_auth})
        return self.result


@pytest.fixture(scope="module")
def qcore_app():
    return QCoreApplication.instance() or QCoreApplication([])


def _member(member_id: int, name: str | None = None) -> Member:
    return Member(
        id=member_id,
        full_name=name or f"Socio {member_id}",
        registration_date=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_members_service_parses_members_page_payload():
    client = _FakeGraphQLClient(
        {
            "membersPage": {
                "total": 123,
                "items": [
                    {
                        "id": 7,
                        "fullName": "Ana Socia",
                        "email": "ana@example.com",
                        "phoneNumber": "555",
                        "waId": "521555",
                        "registrationDate": "2026-01-01T00:00:00+00:00",
                        "totalPayments": 150.0,
                        "lastActivity": None,
                        "activeStandingBooking": None,
                        "activeMembership": {
                            "subscriptionId": 99,
                            "planName": "Mensual",
                            "startDate": "2026-01-01T00:00:00+00:00",
                            "endDate": "2026-02-01T00:00:00+00:00",
                            "status": "active",
                            "remainingDays": 15,
                        },
                    }
                ],
            }
        }
    )

    result = await MembersService(client).get_members(limit=50, offset=100, search="Ana")

    assert result["total"] == 123
    assert len(result["items"]) == 1
    assert result["items"][0].id == 7
    assert result["items"][0].active_membership.plan_name == "Mensual"
    assert "membersPage" in client.calls[0]["query"]
    assert client.calls[0]["variables"] == {"limit": 50, "offset": 100, "search": "Ana"}


def test_members_controller_navigates_pages(monkeypatch, qcore_app):
    controller = MembersController(members_service=object())
    calls = []

    def fake_execute(service, method_name, on_success, on_error, **kwargs):
        calls.append(
            {
                "service": service,
                "method_name": method_name,
                "on_success": on_success,
                "on_error": on_error,
                "kwargs": kwargs,
            }
        )
        return object()

    monkeypatch.setattr(controller, "_execute_authenticated_operation", fake_execute)

    controller.load_members(search="ana")
    first_request = controller._members_request_id
    controller._on_members_loaded(
        {"items": [_member(1)], "total": 250},
        first_request,
        100,
        0,
        "ana",
    )

    assert controller.state().has_next is True
    assert controller.state().has_previous is False

    controller.next_page()
    assert calls[-1]["kwargs"]["offset"] == 100
    second_request = controller._members_request_id
    controller._on_members_loaded(
        {"items": [_member(2)], "total": 250},
        second_request,
        100,
        100,
        "ana",
    )

    assert controller.state().offset == 100
    assert controller.state().has_previous is True

    controller.previous_page()
    assert calls[-1]["kwargs"]["offset"] == 0


def test_members_controller_ignores_stale_member_pages(monkeypatch, qcore_app):
    controller = MembersController(members_service=object())

    def fake_execute(service, method_name, on_success, on_error, **kwargs):
        return object()

    monkeypatch.setattr(controller, "_execute_authenticated_operation", fake_execute)

    controller.load_members(search="old")
    old_request = controller._members_request_id
    controller.load_members(search="new")
    new_request = controller._members_request_id

    controller._on_members_loaded(
        {"items": [_member(1, "Old")], "total": 1},
        old_request,
        100,
        0,
        "old",
    )
    assert controller.state().search == "new"
    assert controller.state().loading is True
    assert controller.state().members == ()

    controller._on_members_loaded(
        {"items": [_member(2, "New")], "total": 1},
        new_request,
        100,
        0,
        "new",
    )
    assert controller.state().loading is False
    assert controller.state().members[0].member_id == 2
