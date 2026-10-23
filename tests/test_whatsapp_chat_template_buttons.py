"""Los botones de una plantilla enviada se ven en el chat, igual que en la vista previa.

El caso real: una campaña sale con «Quiero regresar» bajo la imagen, el socio lo toca y en
el chat sólo aparecía su respuesta — la burbuja de la plantilla no mostraba ningún botón,
porque el mensaje guardado no los traía ni el chat sabía dibujarlos. Ahora el backend los
expone (``templateButtons``) y la burbuja los cuelga con el mismo ``ButtonRow`` de la vista
previa. Un backend sin ese campo no debe tumbar el chat: se cae a la consulta de siempre.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from graphql import print_ast

from app.graphql import ws_client
from app.models.chat import ChatMessage
from app.services import whatsapp_chat_service as chat_service
from app.views.tabs.whatsapp import theme
from app.views.tabs.whatsapp.message_bubble import MessageBubble
from app.views.tabs.whatsapp.wa_mockup import BubbleMeta, ButtonRow, button_label

_TZ = timezone(timedelta(hours=-6))

TEMPLATE_PAYLOAD = {
    "id": 7,
    "conversationId": 1,
    "contactId": 1,
    "direction": "outbound",
    "messageType": "template",
    "textContent": "¡Hola, Claudia! Hace 407 días que no te vemos.",
    "timestamp": "2026-10-22T15:20:00-06:00",
    "waMessageId": "wamid.campaign",
    "templateButtons": [
        {"type": "QUICK_REPLY", "text": "Quiero regresar", "url": None, "phoneNumber": None},
        {"type": "URL", "text": "Ver planes", "url": "https://lovefitness.mx/planes", "phoneNumber": None},
    ],
}


def _template_message(buttons, *, direction="outbound") -> ChatMessage:
    return ChatMessage(
        id=7, conversation_id=1, contact_id=1, direction=direction, message_type="template",
        text_content="¡Hola, Claudia! Hace 407 días que no te vemos.",
        timestamp=datetime(2026, 10, 22, 15, 20, tzinfo=_TZ), wa_message_id="wamid.campaign",
        template_buttons=buttons,
    )


# ----------------------------------------------------------------------------
# Modelo
# ----------------------------------------------------------------------------
def test_message_keeps_the_template_buttons_in_the_shape_the_preview_reads():
    message = ChatMessage.from_dict(TEMPLATE_PAYLOAD)

    assert message.template_buttons == [
        {"type": "QUICK_REPLY", "text": "Quiero regresar"},
        {"type": "URL", "text": "Ver planes", "url": "https://lovefitness.mx/planes"},
    ]


def test_messages_without_template_buttons_have_none():
    payload = dict(TEMPLATE_PAYLOAD, templateButtons=None)
    assert ChatMessage.from_dict(payload).template_buttons == []
    payload = {key: value for key, value in TEMPLATE_PAYLOAD.items() if key != "templateButtons"}
    assert ChatMessage.from_dict(payload).template_buttons == []
    payload = dict(TEMPLATE_PAYLOAD, templateButtons=[{"text": "sin tipo"}, "basura"])
    assert ChatMessage.from_dict(payload).template_buttons == []


# ----------------------------------------------------------------------------
# Burbuja
# ----------------------------------------------------------------------------
def _rows(bubble):
    return bubble.findChildren(ButtonRow)


def test_the_sent_template_bubble_carries_its_buttons(qtbot):
    message = ChatMessage.from_dict(TEMPLATE_PAYLOAD)
    bubble = MessageBubble(message, pal=theme.DARK)
    qtbot.addWidget(bubble)

    assert [button_label(row.button()) for row in _rows(bubble)] == ["Quiero regresar", "Ver planes"]


def test_more_than_three_buttons_collapse_like_whatsapp(qtbot):
    buttons = [{"type": "QUICK_REPLY", "text": f"Opción {n}"} for n in range(1, 6)]
    bubble = MessageBubble(_template_message(buttons), pal=theme.DARK)
    qtbot.addWidget(bubble)

    assert [button_label(row.button()) for row in _rows(bubble)] == [
        "Opción 1", "Opción 2", "Ver todas las opciones",
    ]


def test_plain_messages_have_no_button_rows(qtbot):
    bubble = MessageBubble(_template_message([], direction="inbound"), pal=theme.DARK)
    qtbot.addWidget(bubble)

    assert _rows(bubble) == []


def test_the_timestamp_stays_above_the_buttons(qtbot):
    bubble = MessageBubble(_template_message([{"type": "QUICK_REPLY", "text": "Quiero regresar"}]), pal=theme.DARK)
    qtbot.addWidget(bubble)
    bubble.resize(420, bubble.sizeHint().height())
    bubble.show()
    qtbot.wait(20)

    meta = bubble.findChild(BubbleMeta)
    [row] = _rows(bubble)
    assert meta.geometry().bottom() < row.geometry().top()
    # The row spans the whole painted bubble, edge to edge.
    assert row.width() == bubble._bubble_frame.body_rect().width()


# ----------------------------------------------------------------------------
# Compatibilidad con un backend que aún no tiene ``templateButtons``
# ----------------------------------------------------------------------------
class _FakeClient:
    def __init__(self, *, knows_template_buttons: bool, other_error: str = "") -> None:
        self.knows_template_buttons = knows_template_buttons
        self.other_error = other_error
        self.queries = []
        self.last_error = None

    async def execute(self, query, variables=None):
        self.queries.append(query)
        if self.other_error:
            self.last_error = self.other_error
            return None
        if "templateButtons" in query and not self.knows_template_buttons:
            self.last_error = "Cannot query field 'templateButtons' on type 'ChatMessage'."
            return None
        self.last_error = None
        return {"conversationMessages": [TEMPLATE_PAYLOAD]}


def test_thread_query_asks_for_the_buttons():
    client = _FakeClient(knows_template_buttons=True)
    service = chat_service.WhatsAppChatService(client)

    messages = asyncio.run(service.get_messages(1))

    assert client.queries == [chat_service.MESSAGES_QUERY]
    assert messages[0].template_buttons[0]["text"] == "Quiero regresar"


def test_an_older_backend_falls_back_to_the_plain_thread_and_stays_there():
    client = _FakeClient(knows_template_buttons=False)
    service = chat_service.WhatsAppChatService(client)

    first = asyncio.run(service.get_messages(1))
    asyncio.run(service.get_messages(1))

    assert len(first) == 1
    assert client.queries == [
        chat_service.MESSAGES_QUERY,
        chat_service.MESSAGES_COMPAT_QUERY,
        chat_service.MESSAGES_COMPAT_QUERY,
    ]


def test_other_failures_do_not_give_up_the_buttons():
    client = _FakeClient(knows_template_buttons=True, other_error="Tiempo de espera agotado")
    service = chat_service.WhatsAppChatService(client)

    assert asyncio.run(service.get_messages(1)) == []
    assert client.queries == [chat_service.MESSAGES_QUERY]
    assert service._template_buttons_supported is True


def test_realtime_documents_ask_for_the_buttons_with_a_plain_fallback():
    def text(request):
        return print_ast(request.document)

    assert "templateButtons" in text(ws_client.MESSAGE_ADDED_SUBSCRIPTION)
    assert "templateButtons" in text(ws_client.MESSAGE_UPDATED_SUBSCRIPTION)
    assert "templateButtons" not in text(ws_client.MESSAGE_ADDED_COMPAT_SUBSCRIPTION)
    assert "templateButtons" not in text(ws_client.MESSAGE_UPDATED_COMPAT_SUBSCRIPTION)
    assert ws_client._is_unknown_template_buttons_error(
        Exception("{'message': \"Cannot query field 'templateButtons' on type 'ChatMessage'.\"}")
    )
    assert not ws_client._is_unknown_template_buttons_error(Exception("Authentication required."))
