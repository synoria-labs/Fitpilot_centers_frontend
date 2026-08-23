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
/* Pill chips: activity selection, quick groupings, mode segmented control.
   The fill uses ACCENT with BRAND_NAVY text on top. ACCENT is deliberately light — the
   theme module documents that it fails contrast against white — so chips read dark-on-light
   and ACCENT_STRONG stays reserved for the primary buttons. */
QPushButton#{prefix}Chip {{
    background-color: transparent;
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 14px;
    padding: 5px 14px;
    font-weight: 600;
}}
QPushButton#{prefix}Chip:hover {{
    border-color: {accent};
}}
QPushButton#{prefix}Chip:checked {{
    background-color: {accent};
    border-color: {accent};
    color: {theme.BRAND_NAVY};
}}
QPushButton#{prefix}Chip:disabled {{
    color: palette(mid);
    border-color: palette(mid);
}}

/* Schedule grid. Row and column headers are buttons because clicking them selects the whole
   row or column — the gesture that replaces ticking one box per weekday. */
QPushButton#{prefix}GridHeader {{
    background-color: transparent;
    color: {secondary};
    border: none;
    padding: 3px 6px;
    font-weight: 700;
    font-size: 11px;
}}
QPushButton#{prefix}GridHeader:hover {{
    color: {accent};
}}
QPushButton#{prefix}GridCell {{
    background-color: palette(base);
    border: 1px solid palette(mid);
    border-radius: 6px;
}}
QPushButton#{prefix}GridCell:hover {{
    border-color: {accent};
}}
QPushButton#{prefix}GridCell:checked {{
    background-color: {accent};
    border-color: {accent};
    image: url({_CHECKMARK_ICON});
}}
/* Where the gym runs no class. Kept visible but muted so the grid still communicates the
   shape of the week at a glance. */
QLabel#{prefix}GridBlank {{
    color: palette(mid);
    background: transparent;
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
