"""Reusable WhatsApp template preview: a phone mockup of the member's chat.

The template renders the way WhatsApp draws it — bubble with its tail, header media, body
with WhatsApp formatting, footer, timestamp and the buttons attached under the message
(collapsed into «Ver todas las opciones» past three) — over the chat wallpaper, in
WhatsApp's dark or light scheme (sun/moon in the mock header; the choice is shared by every
preview and persisted).

The preview is lightly interactive: a quick reply «sends» the member's quoted reply, «Ver
todas las opciones» opens the bottom sheet, and the other buttons say what they would do.

Header images load through the shared MediaLoader (async download + disk cache) and the
decoded pixmaps stay in a small in-memory cache, so re-rendering on every keystroke touches
neither the network nor the disk. Failures fall back to a stand-in card and are logged.
"""
from __future__ import annotations

import html
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ....core.logging import get_logger
from ....services.media_loader import get_media_loader
from .message_formatter import clock_text, message_html, quote_snippet, whatsapp_markup_html
from .theme import WaPalette, palette_for
from .wa_mockup import (
    CarouselCard,
    ChatHeader,
    ComposerBar,
    MessageCard,
    OptionsSheet,
    OutgoingBubble,
    PhoneScreen,
    ScrollDownButton,
    button_code,
    button_hint,
    button_label,
    button_type,
    day_chip_qss,
    notice_qss,
    preview_prefs,
)

logger = get_logger(__name__)

def _empty_body_html(pal: WaPalette) -> str:
    return f'<span style="color:{pal.text_secondary};"><i>Escribe el mensaje para verlo aquí…</i></span>'


def _location_caption_html(location: Dict[str, Any], pal: WaPalette) -> str:
    name = html.escape(str(location.get("name") or "").strip())
    address = html.escape(str(location.get("address") or "").strip())
    if not (name or address):
        lat = str(location.get("latitude") or "").strip()
        lng = str(location.get("longitude") or "").strip()
        address = html.escape(", ".join(part for part in (lat, lng) if part))
    parts = []
    if name:
        parts.append(f'<span style="color:{pal.text}; font-weight:600;">{name}</span>')
    if address:
        parts.append(address)
    return "<br>".join(parts)


def set_preview_business_name(name: str) -> None:
    """Name shown in the mock WhatsApp header of every preview (e.g. the gym's)."""
    preview_prefs().set_business_name(name)


def set_preview_appearance(mode: str) -> None:
    """Switch every preview between WhatsApp's ``"dark"`` and ``"light"`` schemes."""
    preview_prefs().set_appearance(mode)


_SCROLL_QSS = """
QScrollArea#templatePreviewScroll, QScrollArea#templatePreviewCarousel {
    background: transparent;
    border: none;
}
QWidget#templatePreviewThread, QWidget#templatePreviewCarouselStrip {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 1px 4px 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 6px;
    margin: 0 4px 1px 4px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: rgba(134, 150, 160, 120);
    border-radius: 3px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""


class TemplatePreviewWidget(QWidget):
    """Phone mockup of the member's WhatsApp chat showing one template message."""

    _MAX_BUBBLE_WIDTH = 340
    _THREAD_MARGINS = (6, 10, 10, 14)  # left leaves room for the bubble tail
    _PIXMAP_CACHE_SIZE = 16
    _MAX_REPLIES = 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("templatePreview")
        prefs = preview_prefs()
        self._pal = palette_for(prefs.appearance())

        # Discards async media results that belong to an older render (the tabs
        # re-render the preview on every keystroke).
        self._media_request_seq = 0
        self._media_handle = None
        self._carousel_handles: List[Any] = []
        self._pixmaps: "OrderedDict[str, QPixmap]" = OrderedDict()
        self._state: Optional[Dict[str, Any]] = None
        self._signature: Optional[tuple] = None
        self._replies: List[Tuple[str, str]] = []  # (text, time) of simulated member replies
        self._reply_widgets: List[OutgoingBubble] = []
        self._carousel_cards: List[CarouselCard] = []
        self._sheet: Optional[OptionsSheet] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._screen = PhoneScreen(self._pal, self)
        root.addWidget(self._screen)

        screen_layout = QVBoxLayout(self._screen)
        screen_layout.setContentsMargins(1, 1, 1, 1)
        screen_layout.setSpacing(0)

        self._chat_header = ChatHeader(self._pal)
        self._chat_header.set_business_name(prefs.business_name())
        self._chat_header.appearance_toggle_requested.connect(self._toggle_appearance)
        screen_layout.addWidget(self._chat_header)
        self._screen.set_header(self._chat_header)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("templatePreviewScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_SCROLL_QSS)
        self._scroll.viewport().setAutoFillBackground(False)

        self._thread = QWidget()
        self._thread.setObjectName("templatePreviewThread")
        thread_layout = QVBoxLayout(self._thread)
        thread_layout.setContentsMargins(*self._THREAD_MARGINS)
        thread_layout.setSpacing(6)

        self._day_chip = QLabel("Hoy")
        thread_layout.addWidget(self._day_chip, 0, Qt.AlignmentFlag.AlignHCenter)
        thread_layout.addSpacing(2)

        self._notice = QLabel()
        self._notice.setWordWrap(True)
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setVisible(False)
        thread_layout.addWidget(self._notice, 0, Qt.AlignmentFlag.AlignHCenter)

        self._card = MessageCard(self._pal)
        self._card.button_activated.connect(self._on_button_activated)
        thread_layout.addWidget(self._card, 0, Qt.AlignmentFlag.AlignLeft)

        self._carousel = QScrollArea()
        self._carousel.setObjectName("templatePreviewCarousel")
        self._carousel.setWidgetResizable(True)
        self._carousel.setFrameShape(QFrame.Shape.NoFrame)
        self._carousel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._carousel.viewport().setAutoFillBackground(False)
        strip = QWidget()
        strip.setObjectName("templatePreviewCarouselStrip")
        self._carousel_row = QHBoxLayout(strip)
        self._carousel_row.setContentsMargins(MessageCard.TAIL, 0, 0, 8)
        self._carousel_row.setSpacing(6)
        self._carousel_row.addStretch(1)
        self._carousel.setWidget(strip)
        self._carousel.setVisible(False)
        thread_layout.addWidget(self._carousel)

        self._replies_layout = QVBoxLayout()
        self._replies_layout.setContentsMargins(0, 4, 0, 0)
        self._replies_layout.setSpacing(6)
        thread_layout.addLayout(self._replies_layout)
        thread_layout.addStretch(1)

        self._scroll.setWidget(self._thread)
        screen_layout.addWidget(self._scroll, 1)

        self._composer = ComposerBar(self._pal)
        screen_layout.addWidget(self._composer)

        self._scroll_down = ScrollDownButton(self._pal, self._screen)
        self._scroll_down.clicked.connect(self._scroll_to_bottom)
        self._scroll_animation = QPropertyAnimation(self._scroll.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(260)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        bar = self._scroll.verticalScrollBar()
        bar.valueChanged.connect(self._update_scroll_down)
        bar.rangeChanged.connect(self._update_scroll_down)

        # Bubble widths follow the thread's width (which a scrollbar can also change).
        self._scroll.viewport().installEventFilter(self)
        prefs.appearance_changed.connect(self._apply_appearance)
        prefs.business_name_changed.connect(self._chat_header.set_business_name)
        self._style_chips()
        self.set_preview(body="")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_preview(
        self,
        *,
        body: str,
        footer: Optional[str] = None,
        media_format: Optional[str] = None,
        media_url: Optional[str] = None,
        media_name: Optional[str] = None,
        header_text: Optional[str] = None,
        buttons: Optional[list] = None,
        location: Optional[dict] = None,
        carousel: Optional[list] = None,
    ) -> None:
        self._state = {
            "body": body or "",
            "footer": (footer or "").strip(),
            "media_format": (media_format or "").upper() or None,
            "media_url": (media_url or "").strip(),
            "media_name": media_name or "",
            "header_text": (header_text or "").strip(),
            "buttons": [dict(b) for b in (buttons or []) if isinstance(b, dict)],
            "location": dict(location) if isinstance(location, dict) else None,
            "carousel": [dict(c) for c in (carousel or []) if isinstance(c, dict)],
        }
        self._render()

    def show_placeholder(self, text: str) -> None:
        """Empty state (no template yet): a WhatsApp-style notice instead of a bubble."""
        self._state = None
        self._signature = None
        self._replies = []
        self._media_request_seq += 1
        self._close_sheet()
        self._card.setVisible(False)
        self._render_carousel([], self._media_request_seq)
        self._rebuild_replies()
        self._notice.setText(text)
        self._notice.setVisible(True)
        self._relayout()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render(self) -> None:
        state = self._state
        if state is None:
            return
        pal = self._pal
        signature = self._signature_of(state)
        if signature != self._signature:
            # A different message: drop the simulated replies to the previous one.
            self._signature = signature
            self._replies = []
            self._close_sheet()

        self._media_request_seq += 1
        request_id = self._media_request_seq
        carousel = state["carousel"]
        location = state["location"] if not carousel else None
        body = state["body"]

        self._notice.setVisible(False)
        self._card.setVisible(True)
        self._card.set_content(
            header_text="" if carousel else state["header_text"],
            body_html=message_html(body, pal, highlight_variables=True) if body.strip() else _empty_body_html(pal),
            footer_html="" if carousel else whatsapp_markup_html(state["footer"]),
            caption_html=_location_caption_html(location, pal) if location is not None else "",
            time_text=clock_text(),
            buttons=[] if carousel else state["buttons"],
        )
        if carousel:
            self._card.media.set_state(None)
        elif location is not None:
            self._card.media.set_state("location")
        else:
            self._render_media(request_id, state["media_format"], state["media_url"], state["media_name"])
        self._render_carousel(carousel, request_id)
        self._rebuild_replies()
        self._relayout()

    @staticmethod
    def _signature_of(state: Dict[str, Any]) -> tuple:
        location = state["location"]
        return (
            state["body"],
            state["footer"],
            state["header_text"],
            state["media_format"],
            state["media_url"],
            tuple((button_type(b), button_label(b)) for b in state["buttons"]),
            tuple(str(card.get("body") or "") for card in state["carousel"]),
            tuple(sorted((k, str(v)) for k, v in location.items())) if location is not None else None,
        )

    def _render_media(
        self, request_id: int, media_format: Optional[str], media_url: str, media_name: str
    ) -> None:
        media = self._card.media
        if not media_format:
            media.set_state(None)
            return
        label = media_name or (Path(media_url).name if media_url else "")
        if media_format == "IMAGE":
            if not media_url:
                media.set_state("missing", title="Sin imagen seleccionada", detail=label)
                return
            pixmap = self._cached_pixmap(media_url)
            if pixmap is not None:
                media.set_state("image", pixmap=pixmap)
                return
            media.set_state("loading", title="Cargando imagen…", detail=label)
            self._media_handle = get_media_loader().fetch(media_url)
            self._media_handle.finished.connect(
                lambda path, rid=request_id: self._on_media_ready(rid, path, media_url, label)
            )
            self._media_handle.failed.connect(
                lambda error, rid=request_id: self._on_media_failed(rid, error, media_url, label)
            )
            return
        if media_format == "VIDEO":
            media.set_state("video", title=label or "Video")
            return
        if media_format == "DOCUMENT":
            extension = Path(label or media_url).suffix.lstrip(".").lower()
            media.set_state("document", title=label or "Documento", detail=extension)
            return
        media.set_state("missing", title=media_format.title(), detail=label)

    def _cached_pixmap(self, url: str) -> Optional[QPixmap]:
        pixmap = self._pixmaps.get(url)
        if pixmap is not None:
            self._pixmaps.move_to_end(url)
            return pixmap
        cached = get_media_loader().cached_path(url)
        if cached is None:
            return None
        pixmap = QPixmap(str(cached))
        if pixmap.isNull():
            return None
        self._remember_pixmap(url, pixmap)
        return pixmap

    def _remember_pixmap(self, url: str, pixmap: QPixmap) -> None:
        self._pixmaps[url] = pixmap
        self._pixmaps.move_to_end(url)
        while len(self._pixmaps) > self._PIXMAP_CACHE_SIZE:
            self._pixmaps.popitem(last=False)

    def _on_media_ready(self, request_id: int, path: str, media_url: str, label: str) -> None:
        if request_id != self._media_request_seq:
            return  # a newer preview replaced this request
        pixmap = QPixmap(path)
        if pixmap.isNull():
            logger.warning("Preview de plantilla: formato de imagen no soportado (%s)", media_url)
            self._card.media.set_state("failed", title="Formato de imagen no soportado", detail=label)
        else:
            self._remember_pixmap(media_url, pixmap)
            self._card.media.set_state("image", pixmap=pixmap)
        self._relayout()

    def _on_media_failed(self, request_id: int, error: str, media_url: str, label: str) -> None:
        if request_id != self._media_request_seq:
            return
        logger.warning("Preview de plantilla: no se pudo descargar %s: %s", media_url, error)
        self._card.media.set_state("failed", title="No se pudo cargar la imagen", detail=label)
        self._relayout()

    def _render_carousel(self, cards: List[Dict[str, Any]], request_id: int) -> None:
        for card in self._carousel_cards:
            self._carousel_row.removeWidget(card)
            card.hide()  # deleteLater() only runs once control is back in the event loop
            card.deleteLater()
        self._carousel_cards = []
        self._carousel_handles = []
        self._carousel.setVisible(bool(cards))
        for index, data in enumerate(cards, start=1):
            card = CarouselCard(self._pal)
            body = str(data.get("body") or "").strip()
            card.set_body(
                message_html(body, self._pal, highlight_variables=True)
                if body
                else f'<span style="color:{self._pal.text_secondary};"><i>Tarjeta {index}</i></span>'
            )
            media_format = str(data.get("media_format") or "IMAGE").upper()
            url = str(data.get("media_url") or "").strip()
            name = str(data.get("media_name") or "")
            if media_format == "VIDEO":
                card.media.set_state("video", title=name or "Video")
            elif not url:
                card.media.set_state("missing", title="Sin media seleccionada")
            else:
                pixmap = self._cached_pixmap(url)
                if pixmap is not None:
                    card.media.set_state("image", pixmap=pixmap)
                else:
                    card.media.set_state("loading", title="Cargando imagen…")
                    handle = get_media_loader().fetch(url)
                    handle.finished.connect(
                        lambda path, rid=request_id, c=card, u=url: self._on_card_media_ready(rid, c, path, u)
                    )
                    handle.failed.connect(
                        lambda error, rid=request_id, c=card, n=name: self._on_card_media_failed(rid, c, n)
                    )
                    self._carousel_handles.append(handle)
            self._carousel_row.insertWidget(self._carousel_row.count() - 1, card)
            self._carousel_cards.append(card)

    def _on_card_media_ready(self, request_id: int, card: CarouselCard, path: str, url: str) -> None:
        if request_id != self._media_request_seq or card not in self._carousel_cards:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            card.media.set_state("failed", title="Formato no soportado")
        else:
            self._remember_pixmap(url, pixmap)
            card.media.set_state("image", pixmap=pixmap)
        self._relayout()

    def _on_card_media_failed(self, request_id: int, card: CarouselCard, name: str) -> None:
        if request_id != self._media_request_seq or card not in self._carousel_cards:
            return
        card.media.set_state("failed", title="No se pudo cargar", detail=name)
        self._relayout()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _relayout(self) -> None:
        viewport_width = self._scroll.viewport().width()
        if viewport_width <= 1:
            viewport_width = max(240, self.width() - 2)
        left, _top, right, _bottom = self._THREAD_MARGINS
        available = viewport_width - left - right
        full_width = max(180, min(self._MAX_BUBBLE_WIDTH, available - 16))

        self._notice.setMaximumWidth(max(160, int(available * 0.9)))
        if not self._card.isHidden():
            if self._card.has_rich_content():
                width = full_width
            else:
                width = max(150, min(full_width, self._card.natural_width()))
            self._card.set_bubble_width(width)

        if self._carousel_cards:
            card_width = max(160, min(250, int(available * 0.74)))
            media_height = max(
                (
                    card.media.height_for(card_width - 2 * CarouselCard.INSET, max_ratio=1.0)
                    for card in self._carousel_cards
                ),
                default=0,
            )
            for card in self._carousel_cards:
                card.set_card_width(card_width, media_height)
            tallest = max(card.height() for card in self._carousel_cards)
            self._carousel.setFixedHeight(tallest + 14)

        for bubble in self._reply_widgets:
            bubble.set_bubble_width(max(180, min(300, int(available * 0.8))))

    def eventFilter(self, watched, event):  # noqa: N802 (Qt override)
        if watched is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._relayout()
            self._update_scroll_down()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._close_sheet()
        self._relayout()

    def _update_scroll_down(self, *_args) -> None:
        bar = self._scroll.verticalScrollBar()
        visible = bar.maximum() > 0 and bar.value() < bar.maximum() - 8
        if visible:
            button = self._scroll_down
            x = self._screen.width() - 10 - button.width()
            y = self._composer.geometry().top() - 6 - button.height()
            button.move(x, y)
            button.raise_()
        self._scroll_down.setVisible(visible)

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------
    def _toggle_appearance(self) -> None:
        preview_prefs().set_appearance("light" if self._pal.mode == "dark" else "dark")

    def _apply_appearance(self, mode: str) -> None:
        self._pal = palette_for(mode)
        self._close_sheet()
        self._screen.set_palette(self._pal)
        self._chat_header.set_palette(self._pal)
        self._composer.set_palette(self._pal)
        self._scroll_down.set_palette(self._pal)
        self._card.set_palette(self._pal)
        self._style_chips()
        if self._state is not None:
            self._render()
        else:
            self._relayout()

    def _style_chips(self) -> None:
        self._day_chip.setStyleSheet(day_chip_qss(self._pal))
        self._notice.setStyleSheet(notice_qss(self._pal))

    # ------------------------------------------------------------------
    # Interaction: what tapping each button does on the member's phone
    # ------------------------------------------------------------------
    def _on_button_activated(self, button: Dict[str, Any]) -> None:
        btype = button_type(button)
        if btype == "SEE_ALL":
            self._open_sheet()
        elif btype == "QUICK_REPLY":
            self._send_quick_reply(button)
        elif btype == "COPY_CODE" and button_code(button):
            code = button_code(button)
            QGuiApplication.clipboard().setText(code)
            QToolTip.showText(QCursor.pos(), f"Código «{code}» copiado", self)
        else:
            QToolTip.showText(QCursor.pos(), button_hint(button), self)

    def _send_quick_reply(self, button: Dict[str, Any]) -> None:
        self._replies.append((button_label(button), clock_text()))
        self._replies = self._replies[-self._MAX_REPLIES:]
        self._rebuild_replies()
        self._relayout()
        self._chat_header.show_typing()
        QTimer.singleShot(40, self._scroll_to_bottom)

    def _rebuild_replies(self) -> None:
        for bubble in self._reply_widgets:
            self._replies_layout.removeWidget(bubble)
            bubble.hide()
            bubble.deleteLater()
        self._reply_widgets = []
        if not self._replies:
            return
        quote_title = self._chat_header.display_name()
        quote_text = self._quote_text()
        thumbnail = self._card.media.pixmap()
        for text, time_text in self._replies:
            bubble = OutgoingBubble(
                text,
                quote_title=quote_title,
                quote_text=quote_text,
                quote_thumbnail=thumbnail,
                time_text=time_text,
                pal=self._pal,
            )
            self._replies_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
            self._reply_widgets.append(bubble)

    def _quote_text(self) -> str:
        state = self._state or {}
        prefix = {"IMAGE": "📷", "VIDEO": "🎥", "DOCUMENT": "📄"}.get(state.get("media_format") or "", "")
        if state.get("location") is not None:
            prefix = "📍"
        return quote_snippet(state.get("header_text") or state.get("body") or "", prefix)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(bar.maximum())
        self._scroll_animation.start()

    def _open_sheet(self) -> None:
        self._close_sheet()
        self._sheet = OptionsSheet(
            self._card.all_buttons(), self._pal, corner=PhoneScreen.RADIUS, parent=self._screen
        )
        self._sheet.option_chosen.connect(self._on_button_activated)

    def _close_sheet(self) -> None:
        sheet, self._sheet = self._sheet, None
        if sheet is None:
            return
        try:
            sheet.deleteLater()
        except RuntimeError:
            pass  # already gone (it deletes itself after its closing animation)
