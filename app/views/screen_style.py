"""Shared QSS for administration screens.

``screen_qss(prefix)`` returns the stylesheet for a screen whose widgets use
``{prefix}``-prefixed object names. The same visual language is shared by the
WhatsApp management screens, Chatbot configuration, and Campaigns.
"""
from __future__ import annotations

from pathlib import Path

from .tabs.whatsapp import theme

_CHECKMARK_ICON = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "checkmark.svg"
).as_posix()


def screen_qss(prefix: str) -> str:
    """Return the shared screen stylesheet for prefixed object names."""
    secondary = theme.secondary_text_hex()
    accent = theme.ACCENT
    return f"""
#{prefix}Tab {{ background-color: palette(window); }}
#{prefix}Tab QSplitter::handle {{ background-color: palette(mid); width: 1px; }}
#{prefix}Header {{
    background-color: palette(window);
    border-bottom: 1px solid palette(mid);
}}
QLabel#{prefix}Title {{
    color: palette(text);
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}}
QLabel#{prefix}Hint {{
    color: {secondary};
    font-size: 12px;
    background: transparent;
}}
QWidget#{prefix}ListPane, QWidget#{prefix}ConfigPane {{
    background-color: palette(window);
}}
QScrollArea#{prefix}ConfigScroll {{
    background-color: palette(window);
    border: none;
}}
QScrollArea#{prefix}ConfigScroll > QWidget > QWidget {{
    background-color: palette(window);
}}
QFrame#{prefix}PreviewRail {{
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 6px;
}}
QLabel#{prefix}PreviewRailTitle {{
    color: palette(text);
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}}
QLabel#{prefix}PanelTitle {{
    color: palette(text);
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}}
QLabel#{prefix}ItemTitle {{
    color: palette(text);
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}}
QListWidget#{prefix}List {{
    background-color: palette(window);
    border: none;
    outline: 0;
}}
QListWidget#{prefix}List::item {{
    min-height: 34px;
    padding: 7px 12px;
    border-bottom: 1px solid palette(mid);
    border-radius: 8px;
    color: palette(text);
}}
QListWidget#{prefix}List::item:hover {{
    background-color: palette(alternate-base);
}}
QListWidget#{prefix}List::item:selected,
QListWidget#{prefix}List::item:selected:active,
QListWidget#{prefix}List::item:selected:!active {{
    background-color: palette(alternate-base);
    color: palette(text);
}}
QGroupBox#{prefix}Group {{
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px;
    color: palette(text);
    font-weight: 600;
}}
QGroupBox#{prefix}Group::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {secondary};
}}
QFrame#{prefix}Card {{
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
}}
QCheckBox, QRadioButton {{
    color: palette(text);
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background-color: palette(base);
}}
QCheckBox::indicator:hover {{
    border-color: {accent};
}}
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
    image: url({_CHECKMARK_ICON});
}}
QCheckBox::indicator:checked:hover {{
    background-color: {theme.ACCENT_STRONG_HOVER};
    border-color: {theme.ACCENT_STRONG_HOVER};
}}
QCheckBox::indicator:disabled {{
    background-color: palette(window);
    border-color: palette(mid);
}}
QCheckBox::indicator:checked:disabled {{
    background-color: palette(mid);
    border-color: palette(mid);
    image: url({_CHECKMARK_ICON});
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: palette(mid);
}}
QPushButton#{prefix}ActionButton {{
    background-color: transparent;
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton#{prefix}ActionButton:hover {{
    background-color: palette(alternate-base);
}}
QPushButton#{prefix}ActionButton:disabled {{
    color: palette(mid);
}}
QPushButton#{prefix}PrimaryButton {{
    background-color: {theme.ACCENT_STRONG};
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
}}
QPushButton#{prefix}PrimaryButton:hover {{
    background-color: {theme.ACCENT_STRONG_HOVER};
}}
QPushButton#{prefix}PrimaryButton:disabled {{
    background-color: palette(mid);
    color: palette(window);
}}
"""
