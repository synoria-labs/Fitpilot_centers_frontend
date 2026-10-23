"""Shared WhatsApp-style palette and small helpers for the chat UI."""
from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem


# ----------------------------------------------------------------------------
# WhatsApp color schemes (chat tab + template preview)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class WaPalette:
    """One WhatsApp color scheme. Colors with alpha use Qt's ``#AARRGGBB`` form."""

    mode: str
    wallpaper: str
    wallpaper_overlay: str
    header_bg: str
    header_text: str
    header_icon: str
    bubble_in: str
    bubble_out: str
    text: str
    text_secondary: str
    meta_out: str
    link: str
    divider: str
    hover: str
    chip_bg: str
    chip_text: str
    notice_bg: str
    notice_text: str
    composer_bg: str
    composer_icon: str
    green: str
    read_check: str
    quote_bg: str
    quote_in_bg: str
    quote_name: str
    media_bg: str
    doc_bg: str
    sheet_bg: str
    dim: str
    shadow: str
    var_bg: str
    var_text: str


# Sampled from WhatsApp's own schemes: the chat and the preview look like the member's phone.
DARK = WaPalette(
    mode="dark",
    wallpaper="#0B141A",
    wallpaper_overlay="#760B141A",
    header_bg="#202C33",
    header_text="#E9EDEF",
    header_icon="#AEBAC1",
    bubble_in="#202C33",
    bubble_out="#005C4B",
    text="#E9EDEF",
    text_secondary="#8696A0",
    meta_out="#99E9EDEF",
    link="#53BDEB",
    divider="#2F3C43",
    hover="#10FFFFFF",
    chip_bg="#182229",
    chip_text="#8696A0",
    notice_bg="#182229",
    notice_text="#FFD279",
    composer_bg="#202C33",
    composer_icon="#8696A0",
    green="#00A884",
    read_check="#53BDEB",
    quote_bg="#025144",
    quote_in_bg="#1A2328",
    quote_name="#06CF9C",
    media_bg="#2A3942",
    doc_bg="#1B252B",
    sheet_bg="#233138",
    dim="#73000000",
    shadow="#40000000",
    var_bg="#2B4C5B",
    var_text="#7DD3F7",
)

LIGHT = WaPalette(
    mode="light",
    wallpaper="#EFEAE2",
    wallpaper_overlay="#00000000",
    header_bg="#F0F2F5",
    header_text="#111B21",
    header_icon="#54656F",
    bubble_in="#FFFFFF",
    bubble_out="#D9FDD3",
    text="#111B21",
    text_secondary="#667781",
    meta_out="#667781",
    link="#027EB5",
    divider="#E9EDEF",
    hover="#0B000000",
    chip_bg="#FFFFFF",
    chip_text="#54656F",
    notice_bg="#FFEECD",
    notice_text="#54656F",
    composer_bg="#FFFFFF",
    composer_icon="#54656F",
    green="#00A884",
    read_check="#53BDEB",
    quote_bg="#CFF1C9",
    quote_in_bg="#F5F6F6",
    quote_name="#1FA855",
    media_bg="#E9EDEF",
    doc_bg="#F5F6F6",
    sheet_bg="#FFFFFF",
    dim="#5C000000",
    shadow="#21000000",
    var_bg="#DDEFF8",
    var_text="#027EB5",
)


def palette_for(mode: str) -> WaPalette:
    return LIGHT if mode == "light" else DARK


def app_palette() -> WaPalette:
    """The chat tab's scheme: WhatsApp's bubbles and text, dark or light like the app, on the
    app's own neutral chrome — the wallpaper's base (left untinted), the header, the composer
    and the day chips take the app palette's colors. The template preview keeps WhatsApp's
    chrome and its own dark/light toggle: it shows the member's phone."""
    app = QApplication.instance()
    palette = app.palette() if app else QPalette()
    window = palette.color(QPalette.ColorRole.Window)
    surface = palette.color(QPalette.ColorRole.Base).name()
    return replace(
        LIGHT if window.lightnessF() > 0.5 else DARK,
        wallpaper=window.name(),
        wallpaper_overlay="#00000000",
        header_bg=window.name(),
        composer_bg=surface,
        chip_bg=surface,
    )


# WhatsApp dark palette (flat names kept for the widgets that are always dark)
BG_APP = "#111B21"
BG_PANEL = DARK.header_bg   # headers / search bar
BG_LIST = "#111B21"
ITEM_HOVER = "#202C33"
ITEM_SELECTED = "#2A3942"
THREAD_BG = DARK.wallpaper
BUBBLE_IN = DARK.bubble_in
BUBBLE_OUT = DARK.bubble_out
TEXT_PRIMARY = DARK.text
TEXT_SECONDARY = DARK.text_secondary

# Brand accent (FitPilot blue, from the logo). Used for highlights, focus rings,
# active indicators, icons and badges that paint dark text on top.
ACCENT = "#67b6df"
# Stronger blue for *fills behind white text/icons* (the light ACCENT fails WCAG
# contrast against white). Use these for primary buttons.
ACCENT_STRONG = "#2E86C1"
ACCENT_STRONG_HOVER = "#3A93D0"
ACCENT_STRONG_PRESSED = "#256FA0"
# Soft red for destructive/danger actions (delete, logout). Same tone as the
# sidebar logout button.
DANGER = "#E57373"
# Deep brand navy (logo) and dark splash background, for brand surfaces.
BRAND_NAVY = "#182f50"
SPLASH_BG = "#121212"

INPUT_BG = "#2A3942"
DIVIDER = "#222D34"

# Deterministic avatar background colors
_AVATAR_COLORS = [
    "#6BCBEF", "#FFB300", "#A4C639", "#FF8A65",
    "#BA68C8", "#4DB6AC", "#F06292", "#7986CB",
    "#4FC3F7", "#9CCC65", "#FFD54F", "#E57373",
]

# Emoji placeholders for non-text messages
MEDIA_LABELS = {
    "image": "📷 Imagen",
    "audio": "🎤 Audio",
    "video": "🎬 Video",
    "document": "📎 Documento",
    "sticker": "🟢 Sticker",
}


def palette_hex(role: QPalette.ColorRole = QPalette.ColorRole.Text) -> str:
    app = QApplication.instance()
    palette = app.palette() if app else QPalette()
    return palette.color(role).name()


def secondary_text_hex(
    *,
    foreground_role: QPalette.ColorRole = QPalette.ColorRole.Text,
    background_role: QPalette.ColorRole = QPalette.ColorRole.Window,
    foreground_weight: float = 0.68,
    palette: Optional[QPalette] = None,
) -> str:
    """Secondary text: the text color blended into the background (the app palette's,
    unless a widget's own ``palette`` is given)."""
    if palette is None:
        app = QApplication.instance()
        palette = app.palette() if app else QPalette()
    foreground = palette.color(foreground_role)
    background = palette.color(background_role)
    weight = max(0.0, min(1.0, foreground_weight))

    def channel(getter) -> int:
        return round(getter(background) * (1.0 - weight) + getter(foreground) * weight)

    return QColor(
        channel(lambda color: color.red()),
        channel(lambda color: color.green()),
        channel(lambda color: color.blue()),
    ).name()


def avatar_color(key: str) -> str:
    key = key or ""
    return _AVATAR_COLORS[sum(ord(c) for c in key) % len(_AVATAR_COLORS)]


def avatar_initials(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "👤"
    compact = name.replace(" ", "")
    digit_ratio = (sum(c.isdigit() for c in compact) / len(compact)) if compact else 1
    if digit_ratio >= 0.6:
        return "👤"  # phone-number-only contact
    parts = [p for p in name.split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()


def paint_avatar(painter: QPainter, rect: QRectF, name: str) -> None:
    """Round contact avatar: deterministic color with the initials (or a person glyph)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(avatar_color(name)))
    painter.drawEllipse(rect)
    font = QFont(painter.font())
    font.setPixelSize(max(12, int(rect.width()) // 2 - 4))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, avatar_initials(name))
    painter.restore()


def paint_row_highlight(painter: QPainter, rect: QRectF, option: QStyleOptionViewItem) -> None:
    """Hover/selection of a list row (templates, chats): a rounded fill and, on the
    selected row, the FitPilot accent bar at its left edge."""
    selected = bool(option.state & QStyle.StateFlag.State_Selected)
    if not (selected or option.state & QStyle.StateFlag.State_MouseOver):
        return
    fill = QColor(option.palette.color(QPalette.ColorRole.AlternateBase))
    if not selected:
        fill.setAlpha(150)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, 10, 10)
    if selected:
        painter.setBrush(QColor(ACCENT))
        painter.drawRoundedRect(QRectF(rect.left() + 1, rect.top() + 12, 3, rect.height() - 24), 1.5, 1.5)
    painter.restore()


def avatar_pixmap(name: str, size: int, device_pixel_ratio: float = 2.0) -> QPixmap:
    """:func:`paint_avatar` rendered to a transparent pixmap (sharp on HiDPI screens)."""
    pixmap = QPixmap(round(size * device_pixel_ratio), round(size * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_avatar(painter, QRectF(0, 0, size, size), name)
    painter.end()
    return pixmap
