"""WhatsApp look-alike building blocks shared by the chat tab and the template preview.

These widgets and painters draw what WhatsApp draws: the chat wallpaper, the header, the
bubbles (with their tail on the first message of a run), the timestamp tucked into the
last line, quoted replies, day chips, the «jump to the end» button and the template buttons
— full-width rows attached under the message, split by hairlines, with a centered
link-colored icon + label, collapsing into «Ver todas las opciones» past three.

They hold no chat or template logic: ``MessageBubble`` / ``MessageThreadWidget`` and
``TemplatePreviewWidget`` feed them resolved content (HTML, pixmaps, button dicts). Colors
come from :class:`~.theme.WaPalette`, sampled from WhatsApp's own dark and light schemes,
except the composer's round button, which is FitPilot blue like the chat's own.
"""
from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import qtawesome as qta
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QTextDocument,
    QTransform,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from ...widgets.brand_logo import logo_mark_pixmap
from . import theme
from .theme import WaPalette


# ----------------------------------------------------------------------------
# Shared preferences of the template preview
# ----------------------------------------------------------------------------
_APPEARANCE_KEY = "whatsapp_preview/appearance"
_BUSINESS_NAME_KEY = "whatsapp_preview/business_name"


class PreviewPrefs(QObject):
    """Preview preferences shared by every preview on screen and persisted between runs:
    WhatsApp scheme (dark/light) and the business name shown in the mock chat header."""

    appearance_changed = Signal(str)
    business_name_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        settings = QSettings()
        appearance = str(settings.value(_APPEARANCE_KEY, "dark") or "dark")
        self._appearance = appearance if appearance in ("dark", "light") else "dark"
        self._business_name = str(settings.value(_BUSINESS_NAME_KEY, "") or "")

    def appearance(self) -> str:
        return self._appearance

    def set_appearance(self, mode: str) -> None:
        mode = "light" if mode == "light" else "dark"
        if mode == self._appearance:
            return
        self._appearance = mode
        QSettings().setValue(_APPEARANCE_KEY, mode)
        self.appearance_changed.emit(mode)

    def business_name(self) -> str:
        return self._business_name

    def set_business_name(self, name: str) -> None:
        name = (name or "").strip()
        if name == self._business_name:
            return
        self._business_name = name
        QSettings().setValue(_BUSINESS_NAME_KEY, name)
        self.business_name_changed.emit(name)


_prefs: Optional[PreviewPrefs] = None


def preview_prefs() -> PreviewPrefs:
    global _prefs
    if _prefs is None:
        _prefs = PreviewPrefs()
    return _prefs


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
_icon_cache: Dict[Tuple[str, str], Any] = {}


def wa_icon(name: str, color: str):
    """qtawesome icon cached per (name, color): the mockup repaints often."""
    key = (name, color)
    icon = _icon_cache.get(key)
    if icon is None:
        icon = qta.icon(name, color=color)
        _icon_cache[key] = icon
    return icon


def _font(base: QFont, pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(base)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def day_chip_qss(pal: WaPalette) -> str:
    """Rounded day chip («Hoy», «Ayer»…) floating over the wallpaper."""
    return (
        f"QLabel {{ background-color: {pal.chip_bg}; color: {pal.chip_text}; border-radius: 8px;"
        " padding: 5px 12px; font-size: 12px; font-weight: 600; }"
    )


def notice_qss(pal: WaPalette) -> str:
    """WhatsApp's centered system notice (yellow text on the chip color in dark mode)."""
    return (
        f"QLabel {{ background-color: {pal.notice_bg}; color: {pal.notice_text}; border-radius: 9px;"
        " padding: 8px 12px; font-size: 12px; }"
    )


def time_spacer_html(time_text: str, color: str, extra: int = 0) -> str:
    """Invisible run (painted in the bubble color) that reserves room for the timestamp
    overlaid at the bubble's bottom-right — WhatsApp's own trick, so the time sits at the
    end of the last line when it fits and drops to its own line when it doesn't."""
    if not time_text:
        return ""
    hidden = "&nbsp;" * (2 + extra) + html.escape(time_text).replace(" ", "&nbsp;")
    # The leading plain space is the only break opportunity: the run wraps as a whole
    # instead of dragging the message's last word (or emoji) down with it.
    return f' <span style="font-size:11px; color:{color};">{hidden}</span>'


def rounded_path(
    rect: QRectF, tl: float = 0.0, tr: float = 0.0, br: float = 0.0, bl: float = 0.0
) -> QPainterPath:
    """Rectangle path with an independent radius per corner."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    path = QPainterPath()
    path.moveTo(x + tl, y)
    path.lineTo(x + w - tr, y)
    if tr:
        path.arcTo(QRectF(x + w - 2 * tr, y, 2 * tr, 2 * tr), 90, -90)
    path.lineTo(x + w, y + h - br)
    if br:
        path.arcTo(QRectF(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br), 0, -90)
    path.lineTo(x + bl, y + h)
    if bl:
        path.arcTo(QRectF(x, y + h - 2 * bl, 2 * bl, 2 * bl), 270, -90)
    path.lineTo(x, y + tl)
    if tl:
        path.arcTo(QRectF(x, y, 2 * tl, 2 * tl), 180, -90)
    path.closeSubpath()
    return path


def tail_path(x: float, y: float, size: float, *, left: bool) -> QPainterPath:
    """WhatsApp's bubble tail, anchored at the bubble's square top corner ``(x, y)``."""
    d = -1.0 if left else 1.0
    path = QPainterPath()
    path.moveTo(x - d, y)  # 1px into the bubble so the seam never shows
    path.lineTo(x + d * (size - 2.0), y)
    path.quadTo(x + d * (size + 0.6), y, x + d * (size - 1.2), y + 2.4)
    path.lineTo(x - d, y + size * 1.5)
    path.closeSubpath()
    return path


def cover_pixmap(source: QPixmap, size: QSize) -> QPixmap:
    """Scale ``source`` to fill ``size`` (device pixels), center-cropping the overflow."""
    scaled = source.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    cropped = scaled.copy(x, y, size.width(), size.height())
    cropped.setDevicePixelRatio(1.0)
    return cropped


def paint_pixmap_rounded(
    painter: QPainter, pixmap: QPixmap, rect: QRectF, radii: Tuple[float, float, float, float], dpr: float
) -> None:
    """Paint ``pixmap`` (already cover-scaled to ``rect`` in device pixels) clipped to a
    rounded shape with anti-aliased edges (a texture brush, not a hard clip)."""
    brush = QBrush(pixmap)
    transform = QTransform()
    transform.translate(rect.x(), rect.y())
    transform.scale(1.0 / dpr, 1.0 / dpr)
    brush.setTransform(transform)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawPath(rounded_path(rect, *radii))


BUBBLE_RADIUS = 7.5
BUBBLE_TAIL = 8


def paint_bubble(
    painter: QPainter, body: QRectF, color: str, shadow: str, *, tail: Optional[str] = None
) -> None:
    """A WhatsApp bubble: the rounded body over a 1px drop shadow and, on the first message
    of a run, the tail at the top corner of its side (``"left"`` incoming, ``"right"``
    outgoing). The tail is drawn outside ``body``, so callers leave it room."""
    radius = BUBBLE_RADIUS
    shape = rounded_path(
        body, 0.0 if tail == "left" else radius, 0.0 if tail == "right" else radius, radius, radius
    )
    painter.fillPath(shape.translated(0, 1), QColor(shadow))
    fill = QColor(color)
    painter.fillPath(shape, fill)
    if tail == "left":
        painter.fillPath(tail_path(body.left(), body.top(), BUBBLE_TAIL, left=True), fill)
    elif tail == "right":
        painter.fillPath(tail_path(body.right(), body.top(), BUBBLE_TAIL, left=False), fill)


class BubbleMeta(QWidget):
    """A bubble's timestamp — and the double check of outgoing messages — overlaid at its
    bottom-right corner. The text underneath reserves the room with :meth:`spacer_html`."""

    _CHECK = 16
    _GAP = 3
    _HEIGHT = 16

    def __init__(
        self,
        pal: WaPalette,
        *,
        outgoing: bool = False,
        checks_color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._pal = pal
        self._outgoing = outgoing
        self._checks_color = checks_color
        self._text = ""
        self._font = _font(self.font(), 11)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.update()

    def set_text(self, text: str) -> None:
        self._text = text or ""
        self.resize(self.sizeHint())
        self.update()

    def spacer_html(self, bubble_color: str) -> str:
        """Invisible run for the end of the bubble text, as wide as this overlay."""
        return time_spacer_html(self._text, bubble_color, extra=4 if self._checks_color else 0)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        width = math.ceil(QFontMetricsF(self._font).horizontalAdvance(self._text))
        if self._checks_color:
            width += self._GAP + self._CHECK
        return QSize(width, self._HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        checks_width = self._CHECK + self._GAP if self._checks_color else 0
        painter.setFont(self._font)
        painter.setPen(QColor(self._pal.meta_out if self._outgoing else self._pal.text_secondary))
        painter.drawText(
            QRectF(0, 0, self.width() - checks_width, self.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._text,
        )
        if self._checks_color:
            wa_icon("mdi6.check-all", self._checks_color).paint(
                painter, QRect(self.width() - self._CHECK, 0, self._CHECK, self._CHECK)
            )


class QuoteBox(QWidget):
    """Quoted message at the top of a reply: colored bar, author, a one-line excerpt and the
    media thumbnail when there is one."""

    HEIGHT = 54
    _MAX_WIDTH = 320

    def __init__(
        self,
        title: str,
        text: str,
        thumbnail: Optional[QPixmap],
        pal: WaPalette,
        parent: Optional[QWidget] = None,
        *,
        background: Optional[str] = None,
        accent: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._text = text
        self._thumbnail = thumbnail
        self._pal = pal
        self._background = background or pal.quote_bg
        self._accent = accent or pal.quote_name
        self.setFixedHeight(self.HEIGHT)
        self.setToolTip(text)

    def _fonts(self) -> Tuple[QFont, QFont]:
        return _font(self.font(), 13, QFont.Weight.DemiBold), _font(self.font(), 12)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        title_font, text_font = self._fonts()
        widest = max(
            QFontMetricsF(title_font).horizontalAdvance(self._title),
            QFontMetricsF(text_font).horizontalAdvance(self._text),
        )
        thumb = self.HEIGHT if self._thumbnail is not None else 0
        return QSize(min(self._MAX_WIDTH, math.ceil(widest) + 26 + thumb), self.HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(120, self.HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        pal = self._pal
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        painter.fillPath(rounded_path(rect, 6, 6, 6, 6), QColor(self._background))
        painter.fillPath(rounded_path(QRectF(0, 0, 4, rect.height()), 6, 0, 0, 6), QColor(self._accent))
        thumb_width = 0.0
        if self._thumbnail is not None and not self._thumbnail.isNull():
            thumb_width = rect.height()
            dpr = self.devicePixelRatioF()
            size = QSize(round(thumb_width * dpr), round(rect.height() * dpr))
            thumb_rect = QRectF(rect.right() - thumb_width, 0, thumb_width, rect.height())
            paint_pixmap_rounded(painter, cover_pixmap(self._thumbnail, size), thumb_rect, (0, 6, 6, 0), dpr)
        text_width = max(10.0, rect.width() - 14 - thumb_width - 8)
        title_font, text_font = self._fonts()
        painter.setFont(title_font)
        painter.setPen(QColor(self._accent))
        painter.drawText(
            QRectF(12, 7, text_width, 18),
            Qt.AlignmentFlag.AlignLeft,
            QFontMetricsF(title_font).elidedText(self._title, Qt.TextElideMode.ElideRight, text_width),
        )
        painter.setFont(text_font)
        painter.setPen(QColor(pal.text_secondary if pal.mode == "light" else "#B3E9EDEF"))
        painter.drawText(
            QRectF(12, 28, text_width, 18),
            Qt.AlignmentFlag.AlignLeft,
            QFontMetricsF(text_font).elidedText(self._text, Qt.TextElideMode.ElideRight, text_width),
        )


# ----------------------------------------------------------------------------
# Buttons: labels, icons and what tapping them does
# ----------------------------------------------------------------------------
SEE_ALL_BUTTON: Dict[str, Any] = {"type": "SEE_ALL", "text": "Ver todas las opciones"}

_BUTTON_ICONS = {
    "QUICK_REPLY": "mdi6.reply",
    "URL": "mdi6.open-in-new",
    "PHONE_NUMBER": "mdi6.phone",
    "VOICE_CALL": "mdi6.phone",
    "COPY_CODE": "mdi6.content-copy",
    "OTP": "mdi6.content-copy",
    "REQUEST_CONTACT_INFO": "mdi6.card-account-details-outline",
    "CATALOG": "mdi6.store",
    "MPM": "mdi6.store",
    "SEE_ALL": "mdi6.format-list-bulleted",
}
_DEFAULT_BUTTON_LABELS = {
    "COPY_CODE": "Copiar código de oferta",
    "VOICE_CALL": "Llamar en WhatsApp",
    "REQUEST_CONTACT_INFO": "Compartir información de contacto",
    "SEE_ALL": "Ver todas las opciones",
}


def button_type(button: Dict[str, Any]) -> str:
    return str(button.get("type") or "").upper()


def button_label(button: Dict[str, Any]) -> str:
    text = str(button.get("text") or "").strip()
    return text or _DEFAULT_BUTTON_LABELS.get(button_type(button), "Botón")


def button_icon_name(button: Dict[str, Any]) -> str:
    return _BUTTON_ICONS.get(button_type(button), "mdi6.gesture-tap-button")


def _first_example(button: Dict[str, Any]) -> str:
    example = button.get("example")
    if isinstance(example, list):
        return str(example[0]) if example else ""
    return str(example or "")


def button_code(button: Dict[str, Any]) -> str:
    """Offer code of a COPY_CODE button, whichever shape the caller passed."""
    return str(button.get("offer_code") or button.get("value") or _first_example(button) or "")


def button_hint(button: Dict[str, Any]) -> str:
    """What tapping the button does for the member (tooltip / tap feedback)."""
    btype = button_type(button)
    if btype == "URL":
        url = str(button.get("url") or button.get("value") or "").strip()
        example = _first_example(button)
        if url and example and "{{" in url:
            return f"Abre {url}\n(ej. {example})"
        return f"Abre {url}" if url else "Abre un enlace"
    if btype == "PHONE_NUMBER":
        phone = str(button.get("phone_number") or button.get("value") or "").strip()
        return f"Llama al {phone}" if phone else "Llama al negocio"
    if btype in ("COPY_CODE", "OTP"):
        code = button_code(button)
        return f"Copia el código «{code}»" if code else "Copia un código"
    if btype == "QUICK_REPLY":
        return "Respuesta rápida: el socio te responde con este texto"
    if btype == "VOICE_CALL":
        return "Inicia una llamada de WhatsApp con el negocio"
    if btype == "REQUEST_CONTACT_INFO":
        return "El socio comparte sus datos de contacto"
    if btype == "SEE_ALL":
        return "Muestra todos los botones de la plantilla"
    return "Botón de la plantilla"


def collapse_buttons(buttons: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """WhatsApp shows up to three buttons; with more, the first two plus
    «Ver todas las opciones», which opens the full list."""
    buttons = list(buttons)
    if len(buttons) <= 3:
        return buttons
    return buttons[:2] + [dict(SEE_ALL_BUTTON)]


# ----------------------------------------------------------------------------
# Wallpaper + phone chrome
# ----------------------------------------------------------------------------
# whatsapp -> tabs -> views -> app ; then /assets/chat-background-3.png (same as the chat tab)
_WALLPAPER_PATH = Path(__file__).resolve().parents[3] / "assets" / "chat-background-3.png"
_wallpapers: Dict[Tuple[str, str, str], Optional[QImage]] = {}


def _wallpaper_key(pal: WaPalette) -> Tuple[str, str, str]:
    return (pal.mode, pal.wallpaper, pal.wallpaper_overlay)


def wallpaper_image(pal: WaPalette) -> Optional[QImage]:
    """The chat-tab doodle wallpaper, tinted for the scheme (cached per scheme colors)."""
    key = _wallpaper_key(pal)
    if key in _wallpapers:
        return _wallpapers[key]
    source = QImage(str(_WALLPAPER_PATH))
    if source.isNull():
        _wallpapers[key] = None
        return None
    image = QImage(source.size(), QImage.Format.Format_RGB32)
    image.fill(QColor(pal.wallpaper))
    painter = QPainter(image)
    if pal.mode == "light":
        # Dark doodles on WhatsApp's beige: invert the line art and lay it on faintly.
        doodles = source.convertToFormat(QImage.Format.Format_RGB32)
        doodles.invertPixels()
        painter.setOpacity(0.16)
        painter.drawImage(0, 0, doodles)
    else:
        painter.drawImage(0, 0, source)
        painter.fillRect(image.rect(), QColor(pal.wallpaper_overlay))
    painter.end()
    _wallpapers[key] = image
    return image


class ChatWallpaper:
    """Paints the wallpaper cover-scaled over a whole widget, cached per size, screen
    scale and scheme (the thread scrolls over it; the wallpaper stays put)."""

    def __init__(self) -> None:
        self._pixmap: Optional[QPixmap] = None
        self._key: Optional[tuple] = None

    def paint(self, painter: QPainter, widget: QWidget, pal: WaPalette) -> None:
        pixmap = self._scaled(widget, pal)
        if pixmap is None:
            painter.fillRect(widget.rect(), QColor(pal.wallpaper))
        else:
            painter.drawPixmap(0, 0, pixmap)

    def _scaled(self, widget: QWidget, pal: WaPalette) -> Optional[QPixmap]:
        image = wallpaper_image(pal)
        if image is None or widget.width() <= 0 or widget.height() <= 0:
            return None
        dpr = widget.devicePixelRatioF()
        key = (widget.width(), widget.height(), dpr, _wallpaper_key(pal))
        if self._pixmap is None or self._key != key:
            target = QSize(max(1, round(widget.width() * dpr)), max(1, round(widget.height() * dpr)))
            pixmap = cover_pixmap(QPixmap.fromImage(image), target)
            pixmap.setDevicePixelRatio(dpr)
            self._pixmap = pixmap
            self._key = key
        return self._pixmap


class PhoneScreen(QWidget):
    """Rounded phone screen: paints the wallpaper, the header strip and the outline.

    The header, the thread and the composer sit on top as transparent children, so the
    wallpaper stays put while the thread scrolls — like WhatsApp.
    """

    RADIUS = 18.0

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        self._header: Optional[QWidget] = None
        self._wallpaper = ChatWallpaper()

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.update()

    def set_header(self, header: QWidget) -> None:
        self._header = header

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)
        painter.save()
        painter.setClipPath(path)
        self._wallpaper.paint(painter, self, self._pal)
        if self._header is not None and not self._header.isHidden():
            header_bottom = self._header.geometry().bottom() + 1
            painter.fillRect(QRectF(0, 0, self.width(), header_bottom), QColor(self._pal.header_bg))
        painter.restore()
        # The anti-aliased outline also hides the hard clip's jaggies at the corners.
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


def _avatar_pixmap(name: str, size: int) -> QPixmap:
    """The business avatar: its initials, or the FitPilot mark while it has no name."""
    if name:
        return theme.avatar_pixmap(name, size)
    scale = 2.0
    pixmap = QPixmap(int(size * scale), int(size * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawEllipse(QRectF(0, 0, size, size))
    mark = logo_mark_pixmap(int(size * 0.58), scale)
    if mark is not None and not mark.isNull():
        mw = mark.width() / mark.devicePixelRatio()
        mh = mark.height() / mark.devicePixelRatio()
        painter.drawPixmap(QPointF((size - mw) / 2, (size - mh) / 2), mark)
    painter.end()
    return pixmap


class ChatHeader(QWidget):
    """WhatsApp chat header of the business account. The sun/moon button toggles the
    preview between WhatsApp's dark and light schemes; the rest is decoration."""

    appearance_toggle_requested = Signal()

    _FALLBACK_NAME = "FitPilot"

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        self._business_name = ""
        self._typing = False
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        self._back = QLabel()
        self._back.setFixedSize(20, 20)
        layout.addWidget(self._back)

        self._avatar = QLabel()
        self._avatar.setFixedSize(36, 36)
        layout.addWidget(self._avatar)

        names = QVBoxLayout()
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        self._name = QLabel()
        self._name.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
        self._subtitle = QLabel()
        self._subtitle.setFont(_font(self.font(), 11))
        names.addWidget(self._name)
        names.addWidget(self._subtitle)
        layout.addLayout(names, 1)

        self._video = QLabel()
        self._call = QLabel()
        for icon_label in (self._video, self._call):
            icon_label.setFixedSize(26, 26)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        self._toggle = QToolButton()
        self._toggle.setFixedSize(28, 28)
        self._toggle.setIconSize(QSize(18, 18))
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self.appearance_toggle_requested)
        layout.addWidget(self._toggle)

        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._stop_typing)

        self.set_palette(pal)

    def display_name(self) -> str:
        return self._business_name or self._FALLBACK_NAME

    def set_business_name(self, name: str) -> None:
        self._business_name = (name or "").strip()
        self._name.setText(self.display_name())
        self._avatar.setPixmap(_avatar_pixmap(self._business_name, 36))

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self._name.setStyleSheet(f"color: {pal.header_text}; background: transparent;")
        self._back.setPixmap(wa_icon("mdi6.arrow-left", pal.header_icon).pixmap(QSize(20, 20)))
        self._video.setPixmap(wa_icon("mdi6.video-outline", pal.header_icon).pixmap(QSize(21, 21)))
        self._call.setPixmap(wa_icon("mdi6.phone-outline", pal.header_icon).pixmap(QSize(19, 19)))
        dark = pal.mode == "dark"
        self._toggle.setIcon(
            wa_icon("mdi6.white-balance-sunny" if dark else "mdi6.weather-night", pal.header_icon)
        )
        self._toggle.setToolTip(
            "Ver cómo se ve en WhatsApp con tema claro"
            if dark
            else "Ver cómo se ve en WhatsApp con tema oscuro"
        )
        self._toggle.setStyleSheet(
            "QToolButton { border: none; border-radius: 14px; background: transparent; }"
            f"QToolButton:hover {{ background-color: {pal.hover}; }}"
        )
        self.set_business_name(self._business_name)
        self._refresh_subtitle()

    def show_typing(self, duration_ms: int = 1800) -> None:
        """«escribiendo…» for a moment, as when the business answers a quick reply."""
        self._typing = True
        self._refresh_subtitle()
        self._typing_timer.start(duration_ms)

    def _stop_typing(self) -> None:
        self._typing = False
        self._refresh_subtitle()

    def _refresh_subtitle(self) -> None:
        if self._typing:
            self._subtitle.setText("escribiendo…")
            color = self._pal.green
        else:
            self._subtitle.setText("Cuenta de empresa")
            color = self._pal.text_secondary
        self._subtitle.setStyleSheet(f"color: {color}; background: transparent;")


class ScrollDownButton(QWidget):
    """WhatsApp's round «jump to the end» button, shown while the chat is scrolled up (in
    the preview it tells that the message and its buttons continue below)."""

    clicked = Signal()

    _DIAMETER = 38.0

    def __init__(
        self, pal: WaPalette, parent: Optional[QWidget] = None, *, tooltip: str = "Ver el final del mensaje"
    ) -> None:
        super().__init__(parent)
        self._pal = pal
        self._hover = False
        self.setFixedSize(46, 48)  # room for the soft shadow
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.hide()

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QRectF(4, 3, self._DIAMETER, self._DIAMETER)
        painter.setPen(Qt.PenStyle.NoPen)
        for grow, alpha in ((3.0, 16), (1.6, 34), (0.6, 52)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawEllipse(circle.adjusted(-grow, -grow + 2, grow, grow + 2))
        fill = QColor(self._pal.composer_bg)
        if self._hover:
            fill = fill.lighter(118) if self._pal.mode == "dark" else fill.darker(104)
        painter.setBrush(fill)
        painter.drawEllipse(circle)
        wa_icon("mdi6.chevron-down", self._pal.header_icon).paint(
            painter, circle.adjusted(8, 9, -8, -7).toRect()
        )

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()


class ComposerBar(QWidget):
    """Decorative WhatsApp composer: emoji, «Mensaje», clip, camera and the round mic —
    in FitPilot blue, like the chat's own composer button."""

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        self.setFixedHeight(54)

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        pal = self._pal
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad, mic, height = 7.0, 40.0, 40.0
        pill = QRectF(pad, (self.height() - height) / 2 - 1, self.width() - 3 * pad - mic, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(pal.composer_bg))
        painter.drawRoundedRect(pill, height / 2, height / 2)

        cy = pill.center().y()
        wa_icon("mdi6.emoticon-outline", pal.composer_icon).paint(
            painter, QRect(int(pill.left() + 11), int(cy - 11), 22, 22)
        )
        painter.setFont(_font(self.font(), 14))
        painter.setPen(QColor(pal.text_secondary))
        painter.drawText(
            QRectF(pill.left() + 42, pill.top(), max(0.0, pill.width() - 110), pill.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Mensaje",
        )
        wa_icon("mdi6.paperclip", pal.composer_icon).paint(
            painter, QRect(int(pill.right() - 64), int(cy - 10), 20, 20)
        )
        wa_icon("mdi6.camera", pal.composer_icon).paint(
            painter, QRect(int(pill.right() - 34), int(cy - 10), 20, 20)
        )
        circle = QRectF(self.width() - pad - mic, pill.center().y() - mic / 2, mic, mic)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT_STRONG))
        painter.drawEllipse(circle)
        wa_icon("mdi6.microphone", "#FFFFFF").paint(painter, circle.adjusted(10, 10, -10, -10).toRect())


# ----------------------------------------------------------------------------
# Header media
# ----------------------------------------------------------------------------
_DOC_ICONS = {
    "pdf": ("mdi6.file-pdf-box", "#F15C6D"),
    "doc": ("mdi6.file-word-box", "#4F8EF7"),
    "docx": ("mdi6.file-word-box", "#4F8EF7"),
    "xls": ("mdi6.file-excel-box", "#21A366"),
    "xlsx": ("mdi6.file-excel-box", "#21A366"),
    "csv": ("mdi6.file-excel-box", "#21A366"),
    "ppt": ("mdi6.file-powerpoint-box", "#F2873F"),
    "pptx": ("mdi6.file-powerpoint-box", "#F2873F"),
}


class MediaView(QWidget):
    """Header media inside a bubble: the photo itself, or a WhatsApp-like stand-in for
    video, document and location headers and for the loading/missing/failed states.

    ``kind`` is one of: image, loading, missing, failed, video, document, location.
    """

    RADIUS = 6.0
    _DOC_HEIGHT = 62

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        self._kind: Optional[str] = None
        self._pixmap: Optional[QPixmap] = None
        self._title = ""
        self._detail = ""
        self._radii = (self.RADIUS,) * 4
        self._cover: Optional[QPixmap] = None
        self._cover_key: Optional[tuple] = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVisible(False)

    @property
    def kind(self) -> Optional[str]:
        return self._kind

    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap if self._kind == "image" else None

    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.update()

    def set_state(
        self, kind: Optional[str], *, pixmap: Optional[QPixmap] = None, title: str = "", detail: str = ""
    ) -> None:
        self._kind = kind
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        if kind == "image" and self._pixmap is None:
            self._kind = "missing"
        self._title = title or ""
        self._detail = detail or ""
        self._cover = None
        self.setVisible(kind is not None)
        self.update()

    def height_for(self, width: int, *, max_ratio: float = 1.25) -> int:
        if self._kind == "document":
            return self._DOC_HEIGHT
        if self._kind == "image" and self._pixmap is not None:
            ratio = self._pixmap.height() / max(1, self._pixmap.width())
            ratio = min(max_ratio, max(0.52, ratio))
        elif self._kind == "video":
            ratio = 9 / 16
        else:
            ratio = 0.52  # Meta's recommended 1.91:1 header
        return max(64, round(width * ratio))

    # -- painting -------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._kind is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        if self._kind == "image" and self._pixmap is not None:
            self._paint_photo(painter, rect)
        elif self._kind == "video":
            self._paint_video(painter, rect)
        elif self._kind == "document":
            self._paint_document(painter, rect)
        elif self._kind == "location":
            self._paint_map(painter, rect)
        else:
            self._paint_placeholder(painter, rect)

    def _shape(self, rect: QRectF) -> QPainterPath:
        return rounded_path(rect, *self._radii)

    def _paint_photo(self, painter: QPainter, rect: QRectF) -> None:
        dpr = self.devicePixelRatioF()
        target = QSize(max(1, round(rect.width() * dpr)), max(1, round(rect.height() * dpr)))
        key = (target.width(), target.height(), self._pixmap.cacheKey())
        if self._cover is None or self._cover_key != key:
            self._cover = cover_pixmap(self._pixmap, target)
            self._cover_key = key
        paint_pixmap_rounded(painter, self._cover, rect, self._radii, dpr)

    def _paint_placeholder(self, painter: QPainter, rect: QRectF) -> None:
        pal = self._pal
        shape = self._shape(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.fillPath(shape, QColor(pal.media_bg))
        if self._kind == "missing":
            outline = QColor(pal.text_secondary)
            outline.setAlpha(150)
            painter.setPen(QPen(outline, 1.2, Qt.PenStyle.DashLine))
            painter.drawPath(shape)
        icon = "mdi6.alert-outline" if self._kind == "failed" else "mdi6.image-outline"
        cx, cy = rect.center().x(), rect.center().y()
        wa_icon(icon, pal.text_secondary).paint(painter, QRect(int(cx - 16), int(cy - 30), 32, 32))
        painter.setPen(QColor(pal.text_secondary))
        title_font = _font(self.font(), 12, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        metrics = QFontMetricsF(title_font)
        title = metrics.elidedText(self._title, Qt.TextElideMode.ElideRight, rect.width() - 24)
        painter.drawText(
            QRectF(rect.left() + 12, cy + 6, rect.width() - 24, 18), Qt.AlignmentFlag.AlignHCenter, title
        )
        if self._detail:
            detail_font = _font(self.font(), 11)
            painter.setFont(detail_font)
            detail = QFontMetricsF(detail_font).elidedText(
                self._detail, Qt.TextElideMode.ElideMiddle, rect.width() - 24
            )
            painter.drawText(
                QRectF(rect.left() + 12, cy + 24, rect.width() - 24, 16), Qt.AlignmentFlag.AlignHCenter, detail
            )

    def _paint_video(self, painter: QPainter, rect: QRectF) -> None:
        dark = self._pal.mode == "dark"
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor("#33444D" if dark else "#C3CDD2"))
        gradient.setColorAt(1.0, QColor("#0F171C" if dark else "#7F8D95"))
        painter.fillPath(self._shape(rect), QBrush(gradient))
        diameter = 54.0
        circle = QRectF(rect.center().x() - diameter / 2, rect.center().y() - diameter / 2, diameter, diameter)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawEllipse(circle)
        wa_icon("mdi6.play", "#FFFFFF").paint(painter, circle.adjusted(12, 12, -12, -12).toRect())
        wa_icon("mdi6.video", "#FFFFFF").paint(painter, QRect(int(rect.left() + 9), int(rect.bottom() - 23), 18, 18))
        painter.setFont(_font(self.font(), 11, QFont.Weight.DemiBold))
        painter.setPen(QColor("#FFFFFF"))
        label = QFontMetricsF(painter.font()).elidedText(
            self._title or "Video", Qt.TextElideMode.ElideMiddle, rect.width() - 44
        )
        painter.drawText(
            QRectF(rect.left() + 32, rect.bottom() - 24, rect.width() - 40, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )

    def _paint_document(self, painter: QPainter, rect: QRectF) -> None:
        pal = self._pal
        painter.fillPath(self._shape(rect), QColor(pal.doc_bg))
        ext = (self._detail or "").lower()
        icon, color = _DOC_ICONS.get(ext, ("mdi6.file-document", pal.text_secondary))
        wa_icon(icon, color).paint(painter, QRect(int(rect.left() + 8), int(rect.center().y() - 19), 36, 38))
        text_left = rect.left() + 50
        text_width = max(10.0, rect.width() - (text_left - rect.left()) - 46)
        title_font = _font(self.font(), 13, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(pal.text))
        title = QFontMetricsF(title_font).elidedText(
            self._title or "Documento", Qt.TextElideMode.ElideMiddle, text_width
        )
        painter.drawText(QRectF(text_left, rect.top() + 12, text_width, 20), Qt.AlignmentFlag.AlignLeft, title)
        painter.setFont(_font(self.font(), 11))
        painter.setPen(QColor(pal.text_secondary))
        meta = f"{ext.upper()} · Documento" if ext else "Documento"
        painter.drawText(QRectF(text_left, rect.top() + 33, text_width, 16), Qt.AlignmentFlag.AlignLeft, meta)
        diameter = 30.0
        circle = QRectF(rect.right() - 10 - diameter, rect.center().y() - diameter / 2, diameter, diameter)
        painter.setPen(QPen(QColor(pal.text_secondary), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle)
        wa_icon("mdi6.download", pal.text_secondary).paint(painter, circle.adjusted(6, 6, -6, -6).toRect())

    def _paint_map(self, painter: QPainter, rect: QRectF) -> None:
        """A stylized street map with a pin (no map tiles: the preview stays offline)."""
        dark = self._pal.mode == "dark"
        base = QColor("#1D2A30" if dark else "#E9E5DD")
        block = QColor("#24343B" if dark else "#F4F1EB")
        road = QColor("#3A4C55" if dark else "#FFFFFF")
        park = QColor("#21392C" if dark else "#CFE7C4")
        water = QColor("#16374A" if dark else "#AED8F2")
        shape = self._shape(rect)
        painter.save()
        painter.setClipPath(shape)
        painter.fillRect(rect, base)
        x0, y0, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(block)
        for fx, fy, fw, fh in (
            (0.04, 0.06, 0.24, 0.32), (0.38, 0.05, 0.19, 0.31), (0.68, 0.08, 0.28, 0.28),
            (0.06, 0.58, 0.21, 0.24), (0.66, 0.56, 0.3, 0.22),
        ):
            painter.drawRoundedRect(QRectF(x0 + fx * w, y0 + fy * h, fw * w, fh * h), 3, 3)
        painter.setBrush(park)
        painter.drawRoundedRect(QRectF(x0 + 0.37 * w, y0 + 0.56 * h, 0.2 * w, 0.26 * h), 6, 6)
        river = QPainterPath()
        river.moveTo(x0 - 6, y0 + 0.9 * h)
        river.cubicTo(x0 + 0.3 * w, y0 + 0.74 * h, x0 + 0.62 * w, y0 + 1.06 * h, x0 + w + 6, y0 + 0.86 * h)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(water, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(river)
        painter.setPen(QPen(road, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x0 - 4, y0 + 0.47 * h), QPointF(x0 + w + 4, y0 + 0.44 * h))
        painter.drawLine(QPointF(x0 + 0.33 * w, y0 - 4), QPointF(x0 + 0.31 * w, y0 + h + 4))
        painter.setPen(QPen(road, 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x0 + 0.63 * w, y0 - 4), QPointF(x0 + 0.61 * w, y0 + h + 4))
        painter.drawLine(QPointF(x0 - 4, y0 + 0.2 * h), QPointF(x0 + 0.33 * w, y0 + 0.22 * h))
        painter.restore()
        cx, cy = rect.center().x(), rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawEllipse(QRectF(cx - 7, cy + 2, 14, 5))
        wa_icon("mdi6.map-marker", "#F15C6D").paint(painter, QRect(int(cx - 19), int(cy - 34), 38, 38))


# ----------------------------------------------------------------------------
# Buttons, bubbles and the «Ver todas las opciones» sheet
# ----------------------------------------------------------------------------
class ButtonRow(QWidget):
    """One template button as WhatsApp draws it: a full-width tappable row with a hairline
    on top and a centered, link-colored icon + label (left-aligned inside the sheet)."""

    activated = Signal(object)  # the button dict

    def __init__(
        self,
        button: Dict[str, Any],
        pal: WaPalette,
        *,
        last: bool = False,
        corner: float = 0.0,
        centered: bool = True,
        text_color: Optional[str] = None,
        height: int = 42,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._button = dict(button)
        self._pal = pal
        self._last = last
        self._corner = corner
        self._centered = centered
        self._text_color = text_color
        self._hover = False
        self._pressed = False
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(button_hint(button))

    def button(self) -> Dict[str, Any]:
        return dict(self._button)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        pal = self._pal
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self._hover or self._pressed:
            corner = self._corner if self._last else 0.0
            tint = QColor(pal.hover)
            if self._pressed:
                tint.setAlpha(min(255, tint.alpha() * 2))
            painter.fillPath(rounded_path(rect, 0, 0, corner, corner), tint)
        painter.setPen(QPen(QColor(pal.divider), 1.0))
        painter.drawLine(QPointF(0, 0.5), QPointF(rect.width(), 0.5))

        font = _font(self.font(), 14 if self._centered else 15, QFont.Weight.DemiBold if self._centered else QFont.Weight.Normal)
        metrics = QFontMetricsF(font)
        icon_size, gap, pad = 18, 8, 16
        available = max(10.0, rect.width() - 2 * pad - icon_size - gap)
        text = metrics.elidedText(button_label(self._button), Qt.TextElideMode.ElideRight, available)
        text_width = metrics.horizontalAdvance(text)
        x = (rect.width() - (icon_size + gap + text_width)) / 2 if self._centered else pad + 2
        wa_icon(button_icon_name(self._button), pal.link).paint(
            painter, QRect(round(x), round((rect.height() - icon_size) / 2), icon_size, icon_size)
        )
        painter.setFont(font)
        painter.setPen(QColor(self._text_color or pal.link))
        painter.drawText(
            QRectF(x + icon_size + gap, 0, text_width + 4, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        was_pressed = self._pressed
        self._pressed = False
        self.update()
        if (
            was_pressed
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.activated.emit(dict(self._button))


def _bubble_label(parent: QWidget, pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QLabel:
    label = QLabel(parent)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    label.setFont(_font(label.font(), pixel_size, weight))
    label.setVisible(False)
    return label


def _fit_label_height(label: QLabel, width: int) -> int:
    """Pin ``label`` to the height its text needs at ``width`` and return it."""
    label.setMinimumHeight(0)  # heightForWidth() never answers below the current minimum
    height = label.heightForWidth(width)
    label.setFixedHeight(height)
    return height


def ideal_text_width(label: QLabel) -> int:
    """Unwrapped width of a rich-text label, measured with a document set up like the
    label's own (default document margin), plus the label's contents margins."""
    document = QTextDocument()
    document.setDefaultFont(label.font())
    document.setHtml(label.text())
    margins = label.contentsMargins()
    return math.ceil(document.idealWidth() + 2 * document.documentMargin()) + margins.left() + margins.right()


class MessageCard(QWidget):
    """Incoming template bubble (tail at the top-left): header media or text, body, footer,
    timestamp and the attached button rows."""

    button_activated = Signal(object)

    TAIL = BUBBLE_TAIL
    RADIUS = BUBBLE_RADIUS
    INSET = 3       # media inset from the bubble edge
    TEXT_INSET = 6  # on top of INSET: text sits 9px from the edge, like WhatsApp
    _CONTENT_BOTTOM = 7

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        self._width = 280
        self._buttons: List[Dict[str, Any]] = []
        self._rows: List[ButtonRow] = []
        self._rows_key: Optional[tuple] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.TAIL, 0, 0, 1)  # 1px below for the bubble shadow
        outer.setSpacing(0)

        self._content = QWidget(self)
        content = QVBoxLayout(self._content)
        content.setContentsMargins(self.INSET, self.INSET, self.INSET, self._CONTENT_BOTTOM)
        content.setSpacing(0)
        self.media = MediaView(pal, self._content)
        content.addWidget(self.media)
        self.caption_label = _bubble_label(self._content, 13)
        self.header_label = _bubble_label(self._content, 15, QFont.Weight.Bold)
        self.body_label = _bubble_label(self._content, 14)
        self.footer_label = _bubble_label(self._content, 13)
        for label, top in (
            (self.caption_label, 6),
            (self.header_label, 6),
            (self.body_label, 5),
            (self.footer_label, 4),
        ):
            label.setContentsMargins(self.TEXT_INSET, top, self.TEXT_INSET, 0)
            content.addWidget(label)
        outer.addWidget(self._content)

        self._buttons_box = QWidget(self)
        self._buttons_layout = QVBoxLayout(self._buttons_box)
        self._buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._buttons_layout.setSpacing(0)
        self._buttons_box.setVisible(False)
        outer.addWidget(self._buttons_box)

        self._meta = BubbleMeta(pal, parent=self)

        self.set_palette(pal)

    # -- content --------------------------------------------------------------
    def set_palette(self, pal: WaPalette) -> None:
        self._pal = pal
        self.media.set_palette(pal)
        self._meta.set_palette(pal)
        for label, color in (
            (self.caption_label, pal.text_secondary),
            (self.header_label, pal.text),
            (self.body_label, pal.text),
            (self.footer_label, pal.text_secondary),
        ):
            label.setStyleSheet(f"color: {color}; background: transparent;")
        self._rows_key = None  # rows paint with the palette: rebuild on the next set_content
        self.update()

    def set_content(
        self,
        *,
        header_text: str = "",
        body_html: str = "",
        footer_html: str = "",
        caption_html: str = "",
        time_text: str = "",
        buttons: Sequence[Dict[str, Any]] = (),
    ) -> None:
        self._meta.set_text(time_text)
        spacer = self._meta.spacer_html(self._pal.bubble_in)
        self.caption_label.setText(caption_html)
        self.caption_label.setVisible(bool(caption_html))
        self.header_label.setText(html.escape(header_text))
        self.header_label.setVisible(bool(header_text))
        has_footer = bool(footer_html)
        self.body_label.setText(body_html + ("" if has_footer else spacer))
        self.body_label.setVisible(True)
        self.footer_label.setText(footer_html + spacer if has_footer else "")
        self.footer_label.setVisible(has_footer)
        self._set_buttons(list(buttons))
        self._relayout()

    def all_buttons(self) -> List[Dict[str, Any]]:
        return [dict(button) for button in self._buttons]

    def has_rich_content(self) -> bool:
        """Media, a header or buttons make WhatsApp draw the bubble at full width."""
        return not self.media.isHidden() or not self.header_label.isHidden() or bool(self._buttons)

    def natural_width(self) -> int:
        """Width a plain text bubble needs before wrapping (WhatsApp hugs short texts)."""
        widest = max(
            (ideal_text_width(label) for label in (self.header_label, self.body_label, self.footer_label)
             if not label.isHidden()),
            default=0,
        )
        return widest + 2 * self.INSET + self.TAIL + 4

    def _set_buttons(self, buttons: List[Dict[str, Any]]) -> None:
        self._buttons = buttons
        shown = collapse_buttons(buttons)
        key = tuple((button_type(b), button_label(b), button_hint(b)) for b in shown)
        if key == self._rows_key:
            return
        self._rows_key = key
        for row in self._rows:
            self._buttons_layout.removeWidget(row)
            row.hide()  # deleteLater() only runs once control is back in the event loop
            row.deleteLater()
        self._rows = []
        for index, button in enumerate(shown):
            row = ButtonRow(
                button, self._pal, last=index == len(shown) - 1, corner=self.RADIUS, parent=self._buttons_box
            )
            row.activated.connect(self.button_activated)
            self._buttons_layout.addWidget(row)
            self._rows.append(row)
        self._buttons_box.setVisible(bool(shown))

    # -- geometry -------------------------------------------------------------
    def set_bubble_width(self, width: int) -> None:
        self._width = max(140, int(width))
        self._relayout()

    def _relayout(self) -> None:
        # Heights are summed here rather than read back from sizeHint(): the layouts'
        # cached hints only refresh on the next event-loop pass, and a stale one would
        # leave the bubble at the previous template's height.
        inner = self._width - self.TAIL - 2 * self.INSET
        content_height = self.INSET + self._CONTENT_BOTTOM
        if not self.media.isHidden():
            media_height = self.media.height_for(inner)
            self.media.setFixedHeight(media_height)
            content_height += media_height
        for label in (self.caption_label, self.header_label, self.body_label, self.footer_label):
            if not label.isHidden():
                content_height += _fit_label_height(label, inner)
        self._content.setFixedHeight(content_height)
        rows_height = sum(row.minimumHeight() for row in self._rows)
        self.setFixedSize(self._width, content_height + rows_height + 1)
        self._place_time(content_height)

    def _place_time(self, content_height: int) -> None:
        x = self._width - self.INSET - self.TEXT_INSET - self._meta.width()
        y = content_height - self._CONTENT_BOTTOM + 1 - self._meta.height()
        self._meta.move(int(x), int(y))
        self._meta.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.TAIL, 0, self.width() - self.TAIL, self.height() - 1)
        paint_bubble(painter, body, self._pal.bubble_in, self._pal.shadow, tail="left")


class OutgoingBubble(QWidget):
    """The member's reply — green bubble, tail at the top-right — quoting the template,
    which is how WhatsApp shows a quick-reply tap."""

    TAIL = BUBBLE_TAIL

    def __init__(
        self,
        text: str,
        *,
        quote_title: str,
        quote_text: str,
        quote_thumbnail: Optional[QPixmap],
        time_text: str,
        pal: WaPalette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._pal = pal
        self._width = 240
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, self.TAIL + 3, 1)
        layout.setSpacing(0)
        self._quote = QuoteBox(quote_title, quote_text, quote_thumbnail, pal, self)
        layout.addWidget(self._quote)
        self._meta = BubbleMeta(pal, outgoing=True, checks_color=pal.read_check, parent=self)
        self._meta.set_text(time_text)
        self._label = _bubble_label(self, 14)
        self._label.setContentsMargins(6, 5, 6, 7)
        self._label.setStyleSheet(f"color: {pal.text}; background: transparent;")
        self._label.setText(html.escape(text) + self._meta.spacer_html(pal.bubble_out))
        self._label.setVisible(True)
        layout.addWidget(self._label)

    def set_bubble_width(self, width: int) -> None:
        self._width = max(160, int(width))
        inner = self._width - self.TAIL - 6
        height = 3 + self._quote.minimumHeight() + _fit_label_height(self._label, inner) + 1
        self.setFixedSize(self._width, height)
        right = self._width - self.TAIL - 9
        self._meta.move(int(right - self._meta.width()), int(height - 7 - self._meta.height()))
        self._meta.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0, 0, self.width() - self.TAIL, self.height() - 1)
        paint_bubble(painter, body, self._pal.bubble_out, self._pal.shadow, tail="right")


class CarouselCard(QWidget):
    """One carousel card: a tail-less bubble with its media on top and its body below."""

    INSET = 3

    def __init__(self, pal: WaPalette, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pal = pal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.INSET, self.INSET, self.INSET, 9)
        layout.setSpacing(0)
        self.media = MediaView(pal, self)
        layout.addWidget(self.media)
        self.body_label = _bubble_label(self, 14)
        self.body_label.setContentsMargins(6, 6, 6, 0)
        self.body_label.setStyleSheet(f"color: {pal.text}; background: transparent;")
        self.body_label.setVisible(True)
        layout.addWidget(self.body_label)

    def set_body(self, body_html: str) -> None:
        self.body_label.setText(body_html)

    def set_card_width(self, width: int, media_height: Optional[int] = None) -> None:
        inner = width - 2 * self.INSET
        height = self.INSET + 9
        if not self.media.isHidden():
            media_height = media_height or self.media.height_for(inner, max_ratio=1.0)
            self.media.setFixedHeight(media_height)
            height += media_height
        self.setFixedSize(width, height + _fit_label_height(self.body_label, inner))

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_bubble(painter, QRectF(0, 0, self.width(), self.height() - 1), self._pal.bubble_in, self._pal.shadow)


class _SheetPanel(QWidget):
    def __init__(self, pal: WaPalette, corner: float, parent: QWidget) -> None:
        super().__init__(parent)
        self._pal = pal
        self._corner = corner

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0, -0.5, -0.5)
        painter.fillPath(rounded_path(rect, 16, 16, self._corner, self._corner), QColor(self._pal.sheet_bg))
        grip = QColor(self._pal.text_secondary)
        grip.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip)
        painter.drawRoundedRect(QRectF(rect.center().x() - 18, 7, 36, 4), 2, 2)


class OptionsSheet(QWidget):
    """WhatsApp's «Ver todas las opciones» bottom sheet, slid up over the phone screen."""

    option_chosen = Signal(object)

    def __init__(
        self, buttons: Sequence[Dict[str, Any]], pal: WaPalette, *, corner: float, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self._pal = pal
        self._corner = corner
        self._closing = False
        self.setGeometry(parent.rect())

        self._panel = _SheetPanel(pal, corner, self)
        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(0, 16, 0, 14)
        layout.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(8, 0, 14, 10)
        title_row.setSpacing(6)
        close = QToolButton()
        close.setIcon(wa_icon("mdi6.close", pal.header_icon))
        close.setIconSize(QSize(22, 22))
        close.setFixedSize(32, 32)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("Cerrar")
        close.setStyleSheet(
            "QToolButton { border: none; border-radius: 16px; background: transparent; }"
            f"QToolButton:hover {{ background-color: {pal.hover}; }}"
        )
        close.clicked.connect(self.dismiss)
        title = QLabel("Todas las opciones")
        title.setFont(_font(title.font(), 16, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {pal.text}; background: transparent;")
        title_row.addWidget(close)
        title_row.addWidget(title, 1)
        layout.addLayout(title_row)
        for button in buttons:
            row = ButtonRow(button, pal, centered=False, text_color=pal.text, height=48, parent=self._panel)
            row.activated.connect(self._choose)
            layout.addWidget(row)

        height = min(self._panel.sizeHint().height(), int(self.height() * 0.85))
        self._panel.setGeometry(0, self.height(), self.width(), height)
        self._anim = QPropertyAnimation(self._panel, b"pos", self)
        self._anim.setDuration(230)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(QPoint(0, self.height()))
        self._anim.setEndValue(QPoint(0, self.height() - height))
        self.show()
        self.raise_()
        self._anim.start()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._corner, self._corner)
        painter.fillPath(path, QColor(self._pal.dim))

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if not self._panel.geometry().contains(event.position().toPoint()):
            self.dismiss()

    def _choose(self, button: Dict[str, Any]) -> None:
        self.option_chosen.emit(button)
        self.dismiss()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._anim.stop()
        self._anim = QPropertyAnimation(self._panel, b"pos", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.setStartValue(self._panel.pos())
        self._anim.setEndValue(QPoint(0, self.height()))
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()
