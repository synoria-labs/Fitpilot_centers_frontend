"""Shared QSS for the WhatsApp management screens (Plantillas, Notificaciones, ...).

A single source of truth so those screens stay visually consistent with each other and with
the Chat screen (all read their colors from :mod:`theme`). ``screen_qss(prefix)`` returns the
stylesheet for a screen whose widgets use ``{prefix}``-prefixed object names — e.g. the
templates tab uses ``tplHeader`` / ``tplGroup`` / ``tplPrimaryButton`` and the notifications tab
uses ``notifHeader`` / ``notifGroup`` / ``notifPrimaryButton``. Each tab applies this on itself
via ``setStyleSheet`` so the unprefixed input rules (QComboBox/QLineEdit/QCheckBox) only affect
that tab's own widget tree and never leak across screens.

Object-name suffixes a screen can use: ``Tab`` (root), ``Header``, ``Title``, ``Hint``,
``ListPane``, ``ConfigPane``, ``ConfigScroll``, ``PreviewRail``, ``PreviewRailTitle``,
``PanelTitle``, ``ItemTitle``, ``List``, ``Group``, ``Card``, ``Table``, ``ActionButton``,
``PrimaryButton``.
"""
from __future__ import annotations

from . import theme


def screen_qss(prefix: str) -> str:
    """Return the shared screen stylesheet for object names prefixed with ``prefix``."""
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
QListWidget#{prefix}List::item:selected {{
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
QComboBox, QLineEdit {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    min-height: 34px;
    padding: 0 10px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}}
QComboBox:focus, QLineEdit:focus {{
    border: 1px solid {accent};
}}
QComboBox:disabled, QLineEdit:disabled {{
    background-color: palette(window);
    color: palette(mid);
    border: 1px solid palette(mid);
}}
QComboBox QAbstractItemView {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    selection-background-color: palette(alternate-base);
    selection-color: palette(text);
    outline: 0;
}}
QTextEdit#{prefix}BodyEditor {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}}
QTextEdit#{prefix}BodyEditor:focus {{
    border: 1px solid {accent};
}}
QTableWidget#{prefix}Table {{
    background-color: palette(base);
    alternate-background-color: palette(alternate-base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    gridline-color: palette(mid);
    outline: 0;
}}
QTableWidget#{prefix}Table QHeaderView::section {{
    background-color: palette(window);
    color: {secondary};
    border: none;
    border-bottom: 1px solid palette(mid);
    padding: 4px 8px;
    font-weight: 600;
}}
QCheckBox {{
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
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}
QCheckBox:disabled {{
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
    background-color: {accent};
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
}}
QPushButton#{prefix}PrimaryButton:hover {{
    background-color: #06c191;
}}
QPushButton#{prefix}PrimaryButton:disabled {{
    background-color: palette(mid);
    color: palette(window);
}}
"""
