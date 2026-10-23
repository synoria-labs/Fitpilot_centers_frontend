"""Full-bleed chat wallpaper painted behind the thread + composer.

Drawn on the conversation pane so the message bubbles and the input pill appear
to float over a single, continuous, fixed image. The scroll area, its viewport,
the thread container and the composer are made transparent elsewhere so this
paint shows through them; the header stays opaque and hides the image behind it.
The wallpaper (and its tint per scheme) is the template preview's own.
"""
from typing import Optional

from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import theme
from .theme import WaPalette
from .wa_mockup import ChatWallpaper


class ChatBackgroundWidget(QWidget):
    """A widget that paints the WhatsApp wallpaper of its scheme, cover-scaled."""

    def __init__(self, parent=None, *, pal: Optional[WaPalette] = None) -> None:
        super().__init__(parent)
        self._pal = pal or theme.app_palette()
        self._wallpaper = ChatWallpaper()

    def paintEvent(self, event) -> None:
        self._wallpaper.paint(QPainter(self), self, self._pal)
