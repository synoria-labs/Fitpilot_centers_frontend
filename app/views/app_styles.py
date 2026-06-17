"""Global Qt stylesheet snippets for the FitPilot desktop app."""
from __future__ import annotations

from pathlib import Path

from .tabs.whatsapp import theme

_CHEVRON_DOWN_ICON = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "chevron-down.svg"
).as_posix()


def _rgba(hex_color: str, alpha: int) -> str:
    color = hex_color.lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def app_qss() -> str:
    """Return global QSS shared by the whole application."""
    return "\n".join(
        (
            _selectable_item_states_qss(),
            _text_input_qss(),
            _button_qss(),
            _dropdown_qss(),
            _table_qss(),
            _scrollbar_qss(),
        )
    )


def _selectable_item_states_qss() -> str:
    return """
QListView::item,
QListWidget::item {
    border-radius: 8px;
    color: palette(text);
}

QListView::item:hover,
QListWidget::item:hover,
QListView::item:selected,
QListWidget::item:selected,
QListView::item:selected:active,
QListWidget::item:selected:active,
QListView::item:selected:!active,
QListWidget::item:selected:!active {
    background-color: palette(alternate-base);
    color: palette(text);
}
"""


def _text_input_qss() -> str:
    hover = _rgba(theme.ACCENT, 28)
    focus = theme.ACCENT
    selected = theme.ACCENT
    return f"""
QLineEdit,
QTextEdit,
QPlainTextEdit,
QAbstractSpinBox {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    selection-background-color: {selected};
    selection-color: #0b141a;
}}

QLineEdit,
QAbstractSpinBox {{
    min-height: 34px;
    padding: 0 10px;
}}

QTextEdit,
QPlainTextEdit {{
    padding: 6px 10px;
}}

QLineEdit:hover,
QTextEdit:hover,
QPlainTextEdit:hover,
QAbstractSpinBox:hover {{
    border: 1px solid {hover};
}}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QAbstractSpinBox:focus {{
    border: 1px solid {focus};
}}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled,
QAbstractSpinBox:disabled {{
    background-color: palette(window);
    color: palette(mid);
    border: 1px solid palette(mid);
}}
"""


def _button_qss() -> str:
    """Variantes de boton globales (object names sin prefijo).

    Replican el lenguaje visual canonico de ``screen_qss`` para que cualquier
    boton de la app pueda adoptarlo con solo ``setObjectName``.
    """
    danger = theme.DANGER
    danger_hover = _rgba(theme.DANGER, 36)
    return f"""
QPushButton#primaryButton {{
    background-color: {theme.ACCENT_STRONG};
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{
    background-color: {theme.ACCENT_STRONG_HOVER};
}}
QPushButton#primaryButton:pressed {{
    background-color: {theme.ACCENT_STRONG_PRESSED};
}}
QPushButton#primaryButton:disabled {{
    background-color: palette(mid);
    color: palette(window);
}}

QPushButton#actionButton {{
    background-color: transparent;
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton#actionButton:hover {{
    background-color: palette(alternate-base);
}}
QPushButton#actionButton:disabled {{
    color: palette(mid);
}}

QPushButton#dangerButton {{
    background-color: transparent;
    color: {danger};
    border: 1px solid {danger};
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton#dangerButton:hover {{
    background-color: {danger_hover};
}}
QPushButton#dangerButton:disabled {{
    color: palette(mid);
    border: 1px solid palette(mid);
}}
"""


def _dropdown_qss() -> str:
    hover = _rgba(theme.ACCENT, 36)
    popup_border = _rgba(theme.ACCENT, 86)
    selected = theme.ACCENT
    return f"""
QComboBox {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    min-height: 34px;
    padding: 0 34px 0 10px;
    selection-background-color: {selected};
    selection-color: #0b141a;
}}

QComboBox:hover {{
    border: 1px solid {hover};
}}

QComboBox:focus,
QComboBox:on {{
    border: 1px solid {theme.ACCENT};
}}

QComboBox:disabled {{
    background-color: palette(window);
    color: palette(mid);
    border: 1px solid palette(mid);
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: transparent;
}}

QComboBox::drop-down:hover {{
    background-color: {hover};
}}

QComboBox::down-arrow {{
    image: url({_CHEVRON_DOWN_ICON});
    width: 12px;
    height: 12px;
}}

QComboBox QLineEdit {{
    background-color: transparent;
    border: none;
    padding: 0;
    selection-background-color: {selected};
    selection-color: #0b141a;
}}

QComboBox QAbstractItemView {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid {popup_border};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: palette(alternate-base);
    selection-color: palette(text);
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 5px 9px;
    border-radius: 6px;
    color: palette(text);
}}

QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:selected:active,
QComboBox QAbstractItemView::item:selected:!active {{
    background-color: palette(alternate-base);
    color: palette(text);
}}
"""


def _table_qss() -> str:
    hover = _rgba(theme.ACCENT, 26)
    selected = _rgba(theme.ACCENT, 56)
    selected_active = _rgba(theme.ACCENT, 72)
    border = _rgba(theme.ACCENT, 92)
    return f"""
QTableWidget {{
    background-color: palette(base);
    alternate-background-color: palette(alternate-base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 8px;
    gridline-color: palette(mid);
    outline: 0;
    selection-background-color: {selected};
    selection-color: palette(text);
}}

QTableWidget::viewport {{
    background-color: transparent;
    border: none;
}}

QTableWidget:focus {{
    border: 1px solid palette(mid);
}}

QTableWidget::item {{
    color: palette(text);
    padding: 4px 8px;
}}

QTableWidget::item:hover {{
    background-color: {hover};
}}

QTableWidget::item:selected,
QTableWidget::item:selected:!active {{
    background-color: {selected};
    color: palette(text);
}}

QTableWidget::item:selected:active {{
    background-color: {selected_active};
    color: palette(text);
}}

QTableWidget QHeaderView::section {{
    background-color: palette(window);
    color: palette(text);
    border: none;
    border-right: 1px solid palette(mid);
    border-bottom: 1px solid {border};
    padding: 6px 8px;
    font-weight: 600;
}}

QTableWidget QHeaderView::section:hover {{
    background-color: {hover};
}}

QTableCornerButton::section {{
    background-color: palette(window);
    border: none;
    border-right: 1px solid palette(mid);
    border-bottom: 1px solid {border};
}}
"""


def _scrollbar_qss() -> str:
    return """
QScrollBar:vertical {
    background: transparent;
    border: none;
    margin: 0;
    width: 10px;
}

QScrollBar::handle:vertical {
    background-color: rgba(102, 102, 102, 210);
    border-radius: 5px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background-color: rgba(154, 154, 154, 230);
}

QScrollBar::handle:vertical:pressed {
    background-color: rgba(179, 179, 179, 245);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    border: none;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: rgba(102, 102, 102, 210);
    border-radius: 5px;
    min-width: 32px;
}

QScrollBar::handle:horizontal:hover {
    background-color: rgba(154, 154, 154, 230);
}

QScrollBar::handle:horizontal:pressed {
    background-color: rgba(179, 179, 179, 245);
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""
