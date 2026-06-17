"""Full-bleed chat background image painted behind the thread + composer.

Drawn on the conversation pane so the message bubbles and the input pill appear
to float over a single, continuous, fixed image. The scroll area, its viewport,
the thread container and the composer are made transparent elsewhere so this
paint shows through them; the header stays opaque and hides the image behind it.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

# whatsapp -> tabs -> views -> app ; then /assets/chat-background.png
_BACKGROUND_PATH = Path(__file__).resolve().parents[3] / "assets" / "chat-background-3.png"


class ChatBackgroundWidget(QWidget):
    """A widget that paints a "cover"-scaled background image.

    The source pixmap is scaled to fill the widget while keeping its aspect
    ratio (cropping the overflow) and centered. The scaled result is cached and
    only recomputed when the widget size (or device pixel ratio) changes.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source = QPixmap(str(_BACKGROUND_PATH))
        self._scaled = QPixmap()

    def _ensure_scaled(self) -> None:
        if self._source.isNull():
            return
        dpr = self.devicePixelRatioF()  # HiDPI: scale to physical pixels for sharpness
        target = self.size() * dpr
        if not self._scaled.isNull() and self._scaled.size() == target:
            return
        self._scaled = self._source.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,  # "cover"
            Qt.TransformationMode.SmoothTransformation,
        )
        self._scaled.setDevicePixelRatio(dpr)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._source.isNull():  # fallback if the image is missing/unreadable
            painter.fillRect(self.rect(), self.palette().window())
            return
        self._ensure_scaled()
        # Center-crop the cover-scaled pixmap onto our rect (logical coordinates).
        pw = self._scaled.width() / self._scaled.devicePixelRatio()
        ph = self._scaled.height() / self._scaled.devicePixelRatio()
        painter.drawPixmap(
            int((self.width() - pw) / 2),
            int((self.height() - ph) / 2),
            self._scaled,
        )
