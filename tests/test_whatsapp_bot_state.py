"""The robot switch persists across chat changes and asynchronous responses."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PySide6.QtCore import QObject, Signal

from app.controllers.whatsapp_chat_controller import WhatsAppChatController
from app.models.chat import ChatContact, ChatConversation
from app.services.whatsapp_chat_service import WhatsAppChatService
from app.views.tabs.whatsapp import chat_tab, composer_widget


def conversation(cid=193, enabled=False):
    return ChatConversation(
        id=cid, status="active", bot_enabled=enabled,
        contact=ChatContact(id=cid, wa_id=f"test-{cid}", phone_number="", name=f"Socio {cid}"),
    )


class SilentRecorder(QObject):
    recording_started = Signal()
    recording_paused = Signal()
    recording_resumed = Signal()
    duration_changed = Signal(int)
    level_changed = Signal(float)
    ready = Signal(str)
    canceled = Signal()
    error = Signal(str)


@pytest.fixture
def chat(monkeypatch, qtbot):
    calls, errors = [], []

    def execute(_self, service, method, success, failure, **kwargs):
        calls.append(SimpleNamespace(method=method, success=success, failure=failure, kwargs=kwargs))

    monkeypatch.setattr(WhatsAppChatController, "_execute_authenticated_operation", execute)
    monkeypatch.setattr(WhatsAppChatController, "start_realtime", lambda _self: None)
    monkeypatch.setattr(chat_tab.container, "get", lambda _key: object())
    monkeypatch.setattr(composer_widget, "VoiceNoteRecorder", SilentRecorder)
    monkeypatch.setattr(chat_tab, "show_error", lambda _parent, error, **kwargs: errors.append(error))
    tab = chat_tab.ChatTab()
    qtbot.addWidget(tab)
    calls[0].success([conversation(), conversation(315, True)])
    tab._on_conversation_selected(193)
    return SimpleNamespace(tab=tab, calls=calls, errors=errors)


def last_call(chat, method):
    return next(call for call in reversed(chat.calls) if call.method == method)


@pytest.mark.parametrize("initial", [False, True])
def test_saved_switch_survives_leaving_and_returning_before_response(chat, initial):
    tab = chat.tab
    tab.conversation_list.get_conversation(193).bot_enabled = initial
    tab._refresh_bot_state()
    tab.composer.bot_button.click()
    save = last_call(chat, "set_conversation_bot_enabled")
    assert save.kwargs == {"conversation_id": 193, "enabled": not initial}
    assert not tab.composer.bot_button.isEnabled()

    tab._on_conversation_selected(315)
    assert tab.composer.bot_button.isChecked()
    assert tab.composer.bot_button.isEnabled()
    tab._on_conversation_selected(193)
    assert tab.composer.bot_button.isChecked() is not initial
    assert not tab.composer.bot_button.isEnabled()

    save.success({"success": True, "bot_enabled": not initial})
    assert tab.conversation_list.get_conversation(193).bot_enabled is not initial
    assert tab.composer.bot_button.isEnabled()
    tab._on_conversation_selected(315)
    tab._on_conversation_selected(193)
    assert tab.composer.bot_button.isChecked() is not initial
    assert len([call for call in chat.calls if call.method == "set_conversation_bot_enabled"]) == 1


def test_late_save_updates_its_chat_without_changing_the_open_chat(chat):
    tab = chat.tab
    tab.composer.bot_button.click()
    save = last_call(chat, "set_conversation_bot_enabled")
    tab._on_conversation_selected(315)
    # The server response is authoritative even if it differs from the requested value.
    save.success({"success": True, "bot_enabled": False})
    assert tab.composer.bot_button.isChecked()
    assert tab.conversation_list.get_conversation(193).bot_enabled is False
    tab._on_conversation_selected(193)
    assert not tab.composer.bot_button.isChecked()


@pytest.mark.parametrize("transport_failure", [False, True])
def test_failed_save_restores_confirmed_state_and_surfaces_error(chat, transport_failure):
    tab = chat.tab
    tab.composer.bot_button.click()
    save = last_call(chat, "set_conversation_bot_enabled")
    if transport_failure:
        save.failure("Sin conexión")
    else:
        save.success({"success": False, "error": "Sin conexión"})
    assert not tab.composer.bot_button.isChecked()
    assert tab.composer.bot_button.isEnabled()
    assert chat.errors == ["Sin conexión"]
    # A fresh read reconciles a request whose response was lost after the commit.
    last_call(chat, "get_conversation").success(conversation(enabled=True))
    assert tab.composer.bot_button.isChecked()


def test_failure_after_switching_does_not_roll_back_another_chat(chat):
    tab = chat.tab
    tab.composer.bot_button.click()
    save = last_call(chat, "set_conversation_bot_enabled")
    tab._on_conversation_selected(315)
    save.failure("Error al guardar")
    assert tab.composer.bot_button.isChecked()
    tab._on_conversation_selected(193)
    assert not tab.composer.bot_button.isChecked()


@pytest.mark.parametrize("read_kind", ["single_before", "single_during", "page_before", "page_during"])
def test_stale_reads_cannot_undo_a_saved_switch(chat, read_kind):
    tab = chat.tab

    def read():
        if read_kind.startswith("single"):
            tab.controller.load_single_conversation(193)
            return last_call(chat, "get_conversation")
        tab.controller.load_conversations()
        return last_call(chat, "get_conversations")

    if read_kind.endswith("before"):
        stale = read()
    tab.composer.bot_button.click()
    if read_kind.endswith("during"):
        stale = read()
    last_call(chat, "set_conversation_bot_enabled").success({"success": True, "bot_enabled": True})
    stale.success(conversation() if read_kind.startswith("single") else [conversation()])
    assert tab.composer.bot_button.isChecked()
    assert tab.conversation_list.get_conversation(193).bot_enabled


def test_a_fresh_read_after_saving_can_reflect_another_admins_change(chat):
    tab = chat.tab
    tab.composer.bot_button.click()
    last_call(chat, "set_conversation_bot_enabled").success({"success": True, "bot_enabled": True})
    tab._on_conversation_selected(315)
    tab._on_conversation_selected(193)
    last_call(chat, "get_conversation").success(conversation(enabled=False))
    assert not tab.composer.bot_button.isChecked()


@pytest.mark.parametrize("save_succeeds", [False, True])
def test_pending_bot_save_does_not_unlock_composer_during_an_upload(chat, save_succeeds):
    tab = chat.tab
    tab.composer.bot_button.click()
    tab.composer.bot_button.click()  # disabled: no overlapping mutation
    assert len([call for call in chat.calls if call.method == "set_conversation_bot_enabled"]) == 1
    tab.composer.set_sending(True)
    save = last_call(chat, "set_conversation_bot_enabled")
    if save_succeeds:
        save.success({"success": True, "bot_enabled": True})
    else:
        save.failure("No se pudo guardar")
    assert not tab.composer.bot_button.isEnabled()
    assert not tab.composer.input.isEnabled()
    tab.composer.set_sending(False)
    assert tab.composer.bot_button.isEnabled()


@pytest.mark.asyncio
@pytest.mark.parametrize("server_value", [False, True])
async def test_service_preserves_the_confirmed_boolean(server_value):
    client = SimpleNamespace(execute=AsyncMock(return_value={
        "setConversationBotEnabled": {"id": 193, "botEnabled": server_value},
    }))
    result = await WhatsAppChatService(client).set_conversation_bot_enabled(193, not server_value)
    assert result == {"success": True, "bot_enabled": server_value}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, {}, {"id": 193}, {"id": 193, "botEnabled": None},
                                     {"id": 315, "botEnabled": True}])
async def test_missing_or_invalid_result_is_an_error_not_a_success(payload):
    client = SimpleNamespace(
        execute=AsyncMock(return_value={"setConversationBotEnabled": payload}),
        last_error="No autorizado",
    )
    result = await WhatsAppChatService(client).set_conversation_bot_enabled(193, True)
    assert result == {"success": False, "error": "No autorizado"}
