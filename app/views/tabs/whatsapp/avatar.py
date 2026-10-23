"""Circular avatar with initials (or a generic glyph for phone-only contacts)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from .theme import avatar_pixmap


class Avatar(QLabel):
    def __init__(self, name: str, size: int = 44, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_name(name, size)

    def set_name(self, name: str, size: int = 44) -> None:
        self.setFixedSize(size, size)
        self.setPixmap(avatar_pixmap(name, size))
