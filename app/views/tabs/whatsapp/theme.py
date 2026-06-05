"""Shared WhatsApp-style palette and small helpers for the chat UI."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# WhatsApp dark palette
BG_APP = "#111B21"
BG_PANEL = "#202C33"        # headers / search bar
BG_LIST = "#111B21"
ITEM_HOVER = "#202C33"
ITEM_SELECTED = "#2A3942"
THREAD_BG = "#0B141A"
BUBBLE_IN = "#202C33"
BUBBLE_OUT = "#005C4B"
TEXT_PRIMARY = "#E9EDEF"
TEXT_SECONDARY = "#8696A0"
ACCENT = "#00A884"
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
) -> str:
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
