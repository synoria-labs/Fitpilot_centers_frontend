"""Circular avatar with initials (or a generic glyph for phone-only contacts)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from .theme import avatar_color, avatar_initials


class Avatar(QLabel):
    def __init__(self, name: str, size: int = 44, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_name(name, size)

    def set_name(self, name: str, size: int = 44) -> None:
        initials = avatar_initials(name)
        color = avatar_color(name)
        self.setText(initials)
        font_px = max(12, size // 2 - 4)
        self.setStyleSheet(
            f"background-color: {color}; color: white; border-radius: {size // 2}px; "
            f"font-weight: bold; font-size: {font_px}px;"
        )
