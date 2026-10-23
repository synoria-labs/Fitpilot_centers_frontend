"""El chat y la vista previa de plantillas comparten el mismo dibujo de WhatsApp.

Cubren lo que el rediseño promete y un refactor podría romper sin que se note: horas y días
como los imprime WhatsApp, el mismo formato de texto (negritas, enlaces) en ambos lados, la
colita sólo en el primer mensaje de cada racha, los separadores de día, las respuestas que
citan su mensaje, el botón redondo del compositor (graba o envía) y que ese botón sea azul
FitPilot y no verde, también en la vista previa.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

from app.models.chat import ChatMedia, ChatMessage
from app.views.tabs.whatsapp import theme
from app.views.tabs.whatsapp.composer_widget import ComposerWidget
from app.views.tabs.whatsapp.message_bubble import _TIME_SPACER_RE, MessageBubble, QuotedMessage
from app.views.tabs.whatsapp.message_formatter import (
    clock_text,
    day_label,
    list_time_text,
    message_html,
    quote_snippet,
    quote_text_for_message,
    whatsapp_markup_html,
)
from app.views.tabs.whatsapp.message_thread_widget import DayChip, MessageThreadWidget
from app.views.tabs.whatsapp.wa_mockup import ComposerBar, time_spacer_html

_TZ = timezone(timedelta(hours=-6))


def _message(mid, direction, text, ts, *, mtype="text", wa=None, ctx=None, media=None) -> ChatMessage:
    return ChatMessage(
        id=mid, conversation_id=1, contact_id=1, direction=direction, message_type=mtype,
        text_content=text, timestamp=ts, wa_message_id=wa or f"wamid.{mid}",
        context_message_id=ctx, media=media,
    )


# ----------------------------------------------------------------------------
# Horas, días y texto
# ----------------------------------------------------------------------------
def test_clock_text_prints_the_time_as_whatsapp():
    assert clock_text(datetime(2026, 10, 22, 18, 42)) == "6:42 p. m."
    assert clock_text(datetime(2026, 10, 22, 0, 5)) == "12:05 a. m."
    assert clock_text(datetime(2026, 10, 22, 12, 0)) == "12:00 p. m."


def test_day_label_names_the_last_week_and_dates_the_rest():
    today = date(2026, 10, 23)
    assert day_label(today, today) == "Hoy"
    assert day_label(date(2026, 10, 22), today) == "Ayer"
    assert day_label(date(2026, 10, 19), today) == "Lunes"
    assert day_label(date(2026, 10, 14), today) == "14/10/2026"


def test_conversation_list_stamp_is_the_time_today_and_the_day_before():
    now = datetime(2026, 10, 23, 10, 0, tzinfo=_TZ)
    assert list_time_text(datetime(2026, 10, 23, 9, 40, tzinfo=_TZ), now) == "9:40 a. m."
    assert list_time_text(datetime(2026, 10, 22, 21, 15, tzinfo=_TZ), now) == "Ayer"
    assert list_time_text(datetime(2026, 10, 14, 8, 0, tzinfo=_TZ), now) == "14/10/2026"
    assert list_time_text(None, now) == ""


def test_message_html_applies_whatsapp_formatting_and_links():
    html = message_html(
        "*Plan* _lunes_ ~no~ https://lovefitness.mx/a_b_c <b>", theme.DARK, clickable_links=True
    )
    assert "<strong>Plan</strong>" in html
    assert "<em>lunes</em>" in html
    assert "<s>no</s>" in html
    # Underscores inside a link are part of the address, not italics.
    assert '<a href="https://lovefitness.mx/a_b_c"' in html
    assert "&lt;b&gt;" in html


def test_preview_tints_links_and_marks_variables_without_anchors():
    html = message_html("Hola {{1}}, paga en https://pay.mx.", theme.DARK, highlight_variables=True)
    assert "<a " not in html
    assert f'<span style="color:{theme.DARK.link};">https://pay.mx</span>.' in html
    assert theme.DARK.var_bg in html
    assert whatsapp_markup_html("Visita https://lovefitness.mx") == "Visita https://lovefitness.mx"


def test_quotes_show_the_first_line_and_the_media_label():
    assert quote_snippet("\n*Hola* Daniela\nsegunda línea") == "Hola Daniela"
    assert quote_snippet("", "📷") == "📷 Archivo"
    photo = ChatMedia(id=1, media_type="image", downloaded=True)
    ts = datetime(2026, 10, 23, 10, 0, tzinfo=_TZ)
    assert quote_text_for_message(_message(1, "inbound", "Mira esto", ts, mtype="image", media=photo)) == "📷 Mira esto"
    assert quote_text_for_message(_message(2, "inbound", None, ts, mtype="image", media=photo)) == "📷 Imagen"


@pytest.mark.parametrize("extra", [0, 4])
def test_copied_text_leaves_out_the_timestamp_room(extra):
    document = QTextDocument()
    document.setHtml("Hola Daniela" + time_spacer_html("10:05 a. m.", "#202C33", extra=extra))
    assert _TIME_SPACER_RE.sub("", document.toPlainText()) == "Hola Daniela"
    # A message that merely ends in a time keeps it.
    assert _TIME_SPACER_RE.sub("", "Nos vemos a las 7:00 p. m.") == "Nos vemos a las 7:00 p. m."


def test_copying_a_bubble_gives_the_message_without_its_timestamp(qtbot):
    message = _message(1, "outbound", "Paga aquí: https://pay.mx", datetime(2026, 10, 23, 10, 5, tzinfo=_TZ))
    bubble = MessageBubble(message, pal=theme.DARK)
    qtbot.addWidget(bubble)
    label = bubble.findChild(QLabel, "bubbleText")
    document = QTextDocument()
    document.setHtml(label.text())
    label.setSelection(0, document.characterCount() - 1)
    label.copy_selection()
    assert QApplication.clipboard().text() == "Paga aquí: https://pay.mx"


# ----------------------------------------------------------------------------
# Hilo: colitas, separadores de día y citas
# ----------------------------------------------------------------------------
def _thread_items(thread: MessageThreadWidget):
    layout = thread._layout
    return [layout.itemAt(index).widget() for index in range(1, layout.count())]


def test_tail_only_on_the_first_bubble_of_each_run_and_a_chip_per_day(qtbot):
    today = datetime.now(_TZ).replace(hour=9, minute=0, second=0, microsecond=0)
    earlier = today - timedelta(days=9)
    messages = [
        _message(1, "inbound", "Hola", earlier),
        _message(2, "inbound", "¿Hay clase?", earlier + timedelta(minutes=1)),
        _message(3, "outbound", "Sí, a las 7", earlier + timedelta(minutes=2)),
        _message(4, "outbound", "¿Te aparto lugar?", today),
        _message(5, "inbound", "Sí porfa", today + timedelta(minutes=5)),
    ]
    thread = MessageThreadWidget(pal=theme.DARK)
    qtbot.addWidget(thread)
    thread.set_messages(messages)

    items = _thread_items(thread)
    assert [type(item).__name__ for item in items] == [
        "DayChip", "MessageBubble", "MessageBubble", "MessageBubble",
        "DayChip", "MessageBubble", "MessageBubble",
    ]
    assert [item.text for item in items if isinstance(item, DayChip)] == [
        earlier.strftime("%d/%m/%Y"), "Hoy",
    ]
    # A new day starts a new run even from the same sender.
    assert [item.has_tail for item in items if isinstance(item, MessageBubble)] == [
        True, False, True, True, True,
    ]


def test_a_reply_quotes_the_message_it_answers(qtbot):
    ts = datetime.now(_TZ).replace(hour=9, minute=0, second=0, microsecond=0)
    messages = [
        _message(1, "outbound", "*Hola Daniela*, tu membresía vence pronto", ts, mtype="template", wa="wamid.tpl"),
        _message(2, "inbound", "Quiero renovar", ts + timedelta(minutes=3), mtype="button", ctx="wamid.tpl"),
        _message(3, "outbound", "¡Listo!", ts + timedelta(minutes=4), ctx="wamid.2"),
        _message(4, "inbound", "Gracias", ts + timedelta(minutes=5), ctx="wamid.older"),
    ]
    thread = MessageThreadWidget(pal=theme.DARK)
    qtbot.addWidget(thread)
    thread.set_contact_name("Daniela Ruiz")
    thread.set_messages(messages)

    assert thread._bubbles[2].quote == QuotedMessage(
        "Tú", "Hola Daniela, tu membresía vence pronto", theme.DARK.quote_name
    )
    assert thread._bubbles[3].quote == QuotedMessage(
        "Daniela Ruiz", "🔘 Quiero renovar", theme.avatar_color("Daniela Ruiz")
    )
    # The quoted message is not in the loaded page: no quote box rather than a broken one.
    assert thread._bubbles[4].quote is None


# ----------------------------------------------------------------------------
# Compositor: un botón redondo azul FitPilot que graba o envía
# ----------------------------------------------------------------------------
class _FakeVoiceRecorder(QObject):
    recording_started = Signal()
    recording_paused = Signal()
    recording_resumed = Signal()
    duration_changed = Signal(int)
    level_changed = Signal(float)
    ready = Signal(str)
    canceled = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []

    def start(self):
        self.calls.append("start")
        self.recording_started.emit()

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def finish(self):
        self.calls.append("finish")

    def cancel(self):
        self.calls.append("cancel")
        self.canceled.emit()


def test_round_button_records_while_empty_and_sends_once_there_is_text(qtbot):
    recorder = _FakeVoiceRecorder()
    composer = ComposerWidget(voice_recorder=recorder, pal=theme.DARK)
    qtbot.addWidget(composer)
    composer.show()

    assert composer.send_button.toolTip() == "Grabar nota de voz"
    composer.input.setText("Hola")
    assert composer.send_button.toolTip() == "Enviar"
    with qtbot.waitSignal(composer.send_requested) as sent:
        qtbot.mouseClick(composer.send_button, Qt.MouseButton.LeftButton)
    assert sent.args == ["Hola"]
    assert recorder.calls == []

    assert composer.send_button.toolTip() == "Grabar nota de voz"
    qtbot.mouseClick(composer.send_button, Qt.MouseButton.LeftButton)
    assert recorder.calls == ["start"]


def test_composer_round_button_is_fitpilot_blue():
    style = ComposerWidget(voice_recorder=_FakeVoiceRecorder(), pal=theme.DARK).styleSheet()
    rule = style[style.index("#composerSend {"):]
    assert rule.split("}")[0].strip().endswith("padding: 8px;")
    assert f"background-color: {theme.ACCENT_STRONG};" in rule.split("}")[0]


@pytest.mark.parametrize("pal", [theme.DARK, theme.LIGHT], ids=["oscuro", "claro"])
def test_preview_mic_is_fitpilot_blue_not_whatsapp_green(qtbot, pal):
    bar = ComposerBar(pal)
    qtbot.addWidget(bar)
    bar.resize(320, 54)
    image = bar.grab().toImage()
    # Inside the round button (center 293,26; radius 20), clear of the mic glyph.
    color = image.pixelColor(278, 26)
    assert color == QColor(theme.ACCENT_STRONG)
    assert color != QColor(pal.green)


# ----------------------------------------------------------------------------
# Esquema: burbujas de WhatsApp sobre el fondo y el encabezado de la app
# ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("window", "base", "whatsapp"),
    [("#f3f3f3", "#ffffff", theme.LIGHT), ("#1e1e1e", "#2d2d2d", theme.DARK)],
    ids=["claro", "oscuro"],
)
def test_chat_bubbles_are_whatsapp_on_the_app_own_background(qapp, window, base, whatsapp):
    original = QApplication.palette()
    palette = QPalette(original)
    palette.setColor(QPalette.ColorRole.Window, QColor(window))
    palette.setColor(QPalette.ColorRole.Base, QColor(base))
    qapp.setPalette(palette)
    try:
        pal = theme.app_palette()
    finally:
        qapp.setPalette(original)
    assert pal.mode == whatsapp.mode
    assert (pal.bubble_in, pal.bubble_out, pal.text) == (whatsapp.bubble_in, whatsapp.bubble_out, whatsapp.text)
    # The app's own gray behind the bubbles (wallpaper left untinted) and in the header.
    assert (pal.wallpaper, pal.wallpaper_overlay, pal.header_bg) == (window, "#00000000", window)
    assert (pal.composer_bg, pal.chip_bg) == (base, base)
    # The template preview keeps WhatsApp's own chrome: it shows the member's phone.
    assert theme.palette_for(whatsapp.mode).header_bg == whatsapp.header_bg
