"""WhatsApp-style emoji picker popup for the chat composer.

A frameless ``Popup`` (same pattern as ``ReactionPicker``) with a category nav
row and a scrollable grid of curated emojis. Emits ``emoji_selected`` on each
click and stays open so several emojis can be inserted in a row; it closes when
the user clicks outside (native ``Popup`` behaviour).
"""
from __future__ import annotations

from typing import List, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme

# Curated emoji set per category: (qtawesome icon, label, emojis). Not the full
# Unicode set — a practical, common subset like the official app's first page.
EMOJI_CATEGORIES: List[Tuple[str, str, str]] = [
    (
        "fa5s.smile", "Caras y emociones",
        "😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗😚😙😋😛😜🤪😝🤑🤗🤭🤫🤔"
        "🤐🤨😐😑😶😏😒🙄😬😌😔😪🤤😴😷🤒🤕🤢🤮🥵🥶🥴😵🤯🥳😎🤓🧐😕"
        "🙁☹️😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬😈👿💀💩🤡👻👽",
    ),
    (
        "fa5s.hand-paper", "Personas y gestos",
        "👋🤚🖐✋🖖👌🤌🤏✌️🤞🤟🤘🤙👈👉👆👇☝️👍👎✊👊🤛🤜👏🙌👐🤲🙏✍️"
        "💅🤳💪🦾👀👁👅👄🧠🦷🦴👶🧒👦👧🧑👨👩🧓👴👵🙅🙆💁🙋🙇🤦🤷",
    ),
    (
        "fa5s.heart", "Corazones y símbolos",
        "❤️🧡💛💚💙💜🖤🤍🤎💔❣️💕💞💓💗💖💘💝💟☮️✝️☪️🕉☸️✡️🔯🕎☯️"
        "✅❌⭕🛑⛔🚫💯💢♨️❗❓❕❔‼️⁉️⚠️🔱⚜️🔰♻️🆗🆕🆒🔝🎵🎶➕➖✖️➗💲💱",
    ),
    (
        "fa5s.leaf", "Animales y naturaleza",
        "🐶🐱🐭🐹🐰🦊🐻🐼🐨🐯🦁🐮🐷🐸🐵🐔🐧🐦🐤🦆🦅🦉🦇🐺🐗🐴🦄🐝🐛🦋"
        "🐌🐞🐜🐢🐍🦎🐙🦑🦀🐠🐟🐬🐳🐋🦈🐊🐅🐘🦒🐎🐖🌵🎄🌲🌳🌴🌱🌿☘️🍀"
        "🍃🍂🍁🌺🌸🌼🌻🌹🌷💐🌞🌝🌚🌙⭐🌟✨⚡🔥💥☄️☀️🌈☁️🌧⛈❄️⛄💧🌊",
    ),
    (
        "fa5s.utensils", "Comida y bebida",
        "🍏🍎🍐🍊🍋🍌🍉🍇🍓🫐🍒🍑🥭🍍🥥🥝🍅🥑🥦🥬🥒🌶🌽🥕🧄🧅🥔🥐🥯🍞"
        "🥖🧀🥚🍳🥓🥩🍗🍖🌭🍔🍟🍕🥪🌮🌯🥗🍝🍜🍲🍣🍱🍚🍛🍢🍡🍧🍨🍦🥧🍰"
        "🎂🍮🍭🍬🍫🍿🍩🍪☕🍵🥤🧋🍺🍻🥂🍷🥃🍸🍹🍾🧉",
    ),
    (
        "fa5s.futbol", "Actividades",
        "⚽🏀🏈⚾🥎🎾🏐🏉🥏🎱🏓🏸🥅🏒🏑🏏⛳🏹🎣🥊🥋🎽⛸🥌🎿⛷🏂🏋️🤼🤸"
        "⛹️🤺🤾🏌️🏇🧘🏄🏊🤽🚣🧗🚵🚴🏆🥇🥈🥉🏅🎖🎬🎤🎧🎼🎹🥁🎷🎺🎸🎻🎲"
        "🎯🎳🎮🎰🧩🎨🎭🎪🎟🎫",
    ),
    (
        "fa5s.plane", "Viajes y lugares",
        "🚗🚕🚙🚌🚎🏎🚓🚑🚒🚐🚚🚛🚜🛴🚲🛵🏍🚨🚘🚖✈️🛫🛬🚀🛸🚁⛵🚤🛥🛳"
        "⚓🚉🚂🚆🚇🚊🗺🗿🗽🗼🏰🏯🎡🎢🎠⛲🏖🏝🏔⛰🌋🏕⛺🏠🏡🏢🏬🏣🏥🏦"
        "🏨🏪🏫💒🏛⛪🕌🌅🌄🎇🌆🌇🌉🌌",
    ),
    (
        "fa5s.lightbulb", "Objetos",
        "⌚📱💻⌨️🖥🖨🖱💽💾💿📀📷📸📹🎥📞☎️📟📠📺📻🎙⏱⏰🕰⏳📡🔋🔌💡🔦"
        "🕯💸💵💴💶💷💰💳🧾💎⚖️🔧🔨⚒🛠⛏🔩⚙️🔗⛓🧰🧲🔫💣🔪🗡🛡🚬⚰️🔮"
        "📿🧿💈⚗️🔭🔬💊💉🩹🩺🚪🛏🛋🚽🚿🛁🧴🧷🧹🧺🧻🧼🧽🛒🚬📌📎🖇📏📐✂️"
        "🗃🗑🔒🔓🔏🔐🔑🗝📝✏️🖊🖋📁📂📅📆📇📈📉📊📋📖📚",
    ),
    (
        "fa5s.flag", "Banderas",
        "🏳️🏴🏁🚩🏳️‍🌈🇲🇽🇺🇸🇨🇦🇪🇸🇦🇷🇧🇷🇨🇴🇨🇱🇵🇪🇻🇪🇬🇧🇫🇷🇩🇪🇮🇹🇵🇹🇯🇵🇰🇷🇨🇳🇮🇳🇷🇺🇦🇺",
    ),
]

_COLUMNS = 8


def _grapheme_split(text: str) -> List[str]:
    """Split a string of emojis into individual glyphs, keeping ZWJ sequences,
    variation/keycap/skin-tone modifiers, and flags (regional-indicator pairs)
    together as one selectable item."""
    ZWJ = "‍"

    def is_regional(ch: str) -> bool:
        return 0x1F1E6 <= ord(ch) <= 0x1F1FF

    out: List[str] = []
    for ch in text:
        code = ord(ch)
        if is_regional(ch):
            # Flags are two regional indicators; pair with a lone leading one.
            if out and len(out[-1]) == 1 and is_regional(out[-1]):
                out[-1] += ch
            else:
                out.append(ch)
            continue
        is_joiner = (
            ch == ZWJ
            or code == 0xFE0F  # variation selector-16
            or code == 0x20E3  # combining enclosing keycap
            or 0x1F3FB <= code <= 0x1F3FF  # skin-tone modifiers
        )
        if out and (is_joiner or out[-1].endswith(ZWJ)):
            out[-1] += ch
        else:
            out.append(ch)
    return out


class EmojiPicker(QFrame):
    """Frameless popup emoji grid; emits ``emoji_selected`` per click."""

    emoji_selected = Signal(str)

    _WIDTH = 360
    _HEIGHT = 320

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("emojiPicker")
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setStyleSheet(
            f"""
            #emojiPicker {{
                background-color: {theme.BG_PANEL};
                border: 1px solid {theme.DIVIDER};
                border-radius: 12px;
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#emojiCanvas {{ background: transparent; }}
            QLabel#emojiCategoryTitle {{
                color: {theme.TEXT_SECONDARY};
                font-size: 11px;
                padding: 6px 2px 2px 4px;
            }}
            QToolButton#emojiButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                font-size: 18px;
            }}
            QToolButton#emojiButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
            QToolButton#emojiNav {{
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 5px;
            }}
            QToolButton#emojiNav:hover {{ background-color: {theme.ITEM_HOVER}; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Scroll area with all category sections stacked vertically.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        canvas = QWidget()
        canvas.setObjectName("emojiCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(2)

        self._sections: List[QWidget] = []
        for icon_name, label, emojis in EMOJI_CATEGORIES:
            section = self._build_section(label, emojis)
            self._sections.append(section)
            canvas_layout.addWidget(section)
        canvas_layout.addStretch(1)

        self._scroll.setWidget(canvas)

        # Category navigation row.
        nav = QHBoxLayout()
        nav.setContentsMargins(2, 0, 2, 0)
        nav.setSpacing(0)
        for index, (icon_name, label, _emojis) in enumerate(EMOJI_CATEGORIES):
            button = QToolButton()
            button.setObjectName("emojiNav")
            button.setIcon(qta.icon(icon_name, color=theme.TEXT_SECONDARY))
            button.setToolTip(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, i=index: self._scroll_to(i))
            nav.addWidget(button)
        nav.addStretch(1)

        root.addLayout(nav)
        root.addWidget(self._scroll, 1)

    def _build_section(self, label: str, emojis: str) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel(label)
        title.setObjectName("emojiCategoryTitle")
        layout.addWidget(title)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for i, emoji in enumerate(_grapheme_split(emojis)):
            button = QToolButton()
            button.setObjectName("emojiButton")
            button.setText(emoji)
            button.setFixedSize(38, 36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, e=emoji: self.emoji_selected.emit(e))
            grid.addWidget(button, i // _COLUMNS, i % _COLUMNS)
        layout.addWidget(grid_host)
        return section

    def _scroll_to(self, index: int) -> None:
        if 0 <= index < len(self._sections):
            section = self._sections[index]
            self._scroll.verticalScrollBar().setValue(section.y())
