"""A tap on a template QUICK_REPLY button used to render as the literal placeholder
"[button]" in the chat (the backend never stored the button's text, and the frontend had no
label for the "button"/"interactive" message types). Once the backend fix populates
text_content with the button's title, the formatter should show it clearly marked — not the
raw fallback, and not silently identical to typed text either."""
from app.models.chat import ChatMessage
from app.views.tabs.whatsapp.message_formatter import (
    display_text_for_message,
    snippet_for_message,
)


def _message(message_type: str, text_content) -> ChatMessage:
    return ChatMessage(
        id=1, conversation_id=1, contact_id=1, direction="inbound",
        message_type=message_type, text_content=text_content,
    )


def test_button_tap_shows_marked_text_not_bracket_placeholder():
    text = display_text_for_message(_message("button", "Quiero reservar"))
    assert text == "🔘 Quiero reservar"
    assert "[button]" not in text


def test_interactive_reply_shows_marked_text():
    text = display_text_for_message(_message("interactive", "Ver horarios"))
    assert text == "🔘 Ver horarios"


def test_button_without_text_falls_back_to_bracket_placeholder():
    """No backfill for historical rows ingested before the backend fix — text_content is
    still None for those, and the generic fallback is the honest thing to show."""
    text = display_text_for_message(_message("button", None))
    assert text == "[button]"


def test_snippet_for_message_reuses_the_marked_button_text():
    snippet = snippet_for_message(_message("button", "Quiero reservar"))
    assert snippet == "🔘 Quiero reservar"


def test_plain_text_message_is_unaffected():
    text = display_text_for_message(_message("text", "hola"))
    assert text == "hola"
