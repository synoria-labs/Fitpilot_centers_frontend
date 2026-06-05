"""Shared WhatsApp-style palette and small helpers for the chat UI."""

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
