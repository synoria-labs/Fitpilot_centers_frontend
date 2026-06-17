from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication

from app.auth.auth_service import AuthService
from app.controllers import auth_controller


class _FakeGraphQLClient:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    async def execute(self, query, variables=None, use_auth=True):
        self.calls.append(
            {
                "query": query,
                "variables": variables,
                "use_auth": use_auth,
            }
        )
        if self.error:
            raise self.error
        return self.result


class _FakeSessionStore:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True


@pytest.fixture(scope="module")
def qcore_app():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.mark.asyncio
async def test_logout_clears_local_state_when_server_confirms(monkeypatch):
    session = _FakeSessionStore()
    client = _FakeGraphQLClient({"logout": True})
    clear_calls = {"cookies": 0, "persistent": 0}

    monkeypatch.setattr(
        "app.graphql.client.GraphQLClient.clear_cookies",
        lambda: clear_calls.__setitem__("cookies", clear_calls["cookies"] + 1),
    )
    monkeypatch.setattr(
        "app.auth.persistent_storage.clear_refresh_token",
        lambda: clear_calls.__setitem__("persistent", clear_calls["persistent"] + 1) or True,
    )

    result = await AuthService(client, session).logout()

    assert result is True
    assert session.cleared is True
    assert clear_calls == {"cookies": 1, "persistent": 1}
    assert len(client.calls) == 1
    assert "logout" in client.calls[0]["query"]


@pytest.mark.asyncio
async def test_logout_clears_local_state_when_server_fails(monkeypatch):
    session = _FakeSessionStore()
    client = _FakeGraphQLClient(error=RuntimeError("network down"))
    clear_calls = {"cookies": 0, "persistent": 0}

    monkeypatch.setattr(
        "app.graphql.client.GraphQLClient.clear_cookies",
        lambda: clear_calls.__setitem__("cookies", clear_calls["cookies"] + 1),
    )
    monkeypatch.setattr(
        "app.auth.persistent_storage.clear_refresh_token",
        lambda: clear_calls.__setitem__("persistent", clear_calls["persistent"] + 1) or True,
    )

    result = await AuthService(client, session).logout()

    assert result is False
    assert session.cleared is True
    assert clear_calls == {"cookies": 1, "persistent": 1}


def test_auth_controller_tracks_single_logout_operation(monkeypatch, qcore_app):
    fake_service = object()
    operation = object()
    calls = []

    monkeypatch.setattr(auth_controller.container, "get", lambda name: fake_service)

    def fake_start_authenticated_operation(**kwargs):
        calls.append(kwargs)
        return operation

    monkeypatch.setattr(
        auth_controller,
        "start_authenticated_operation",
        fake_start_authenticated_operation,
    )

    controller = auth_controller.AuthController()
    controller.handle_logout()
    controller.handle_logout()

    assert controller._logout_operation is operation
    assert len(calls) == 1
    assert calls[0]["service"] is fake_service
    assert calls[0]["method_name"] == "logout"

    controller._clear_logout_operation()
    assert controller._logout_operation is None
