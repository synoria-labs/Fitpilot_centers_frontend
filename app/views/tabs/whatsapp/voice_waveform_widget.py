"""Voice-note waveforms: the live composer bars and the playback waveform."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme


class VoiceWaveformWidget(QWidget):
    """Paints compact rounded bars from live microphone levels."""

    def __init__(self, parent=None, *, bar_count: int = 34) -> None:
        super().__init__(parent)
        self._bar_count = max(12, int(bar_count))
        self._levels = [0.0] * self._bar_count
        self._paused = False
        self._processing = False
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(220, 28)

    def reset(self) -> None:
        self._levels = [0.0] * self._bar_count
        self._paused = False
        self._processing = False
        self.update()

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self.update()

    def set_processing(self, processing: bool) -> None:
        self._processing = bool(processing)
        self.update()

    def add_level(self, level: float) -> None:
        if self._paused or self._processing:
            return

        normalized = max(0.0, min(1.0, float(level)))
        previous = self._levels[-1] if self._levels else 0.0
        smoothed = (previous * 0.35) + (normalized * 0.65)
        self._levels = [*self._levels[1:], smoothed]
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        color = QColor(theme.ACCENT)
        if self._processing:
            color.setAlpha(95)
        elif self._paused:
            color.setAlpha(120)
        else:
            color.setAlpha(230)
        painter.setBrush(color)

        width = max(1, self.width())
        height = max(1, self.height())
        gap = 3.0
        bar_width = max(2.0, (width - gap * (self._bar_count - 1)) / self._bar_count)
        center_y = height / 2.0
        min_height = 4.0
        max_height = max(min_height, height - 4.0)

        for index, level in enumerate(self._levels):
            shaped = level ** 0.72 if level > 0 else 0.0
            bar_height = min_height + shaped * (max_height - min_height)
            x = index * (bar_width + gap)
            y = center_y - (bar_height / 2.0)
            radius = min(bar_width / 2.0, 3.0)
            painter.drawRoundedRect(x, y, bar_width, bar_height, radius, radius)


class PlaybackWaveformWidget(QWidget):
    """Static waveform for a chat audio bubble: real bars + a progress fill.

    The bars are the audio envelope (computed off-thread); the played portion is
    painted in the accent color and the rest stays muted. Clicking or dragging
    over the widget emits :attr:`seek_requested` with a 0..1 fraction.
    """

    seek_requested = Signal(float)

    def __init__(self, parent=None, *, bar_count: int = 48) -> None:
        super().__init__(parent)
        self._bar_count = max(8, int(bar_count))
        self._bars: List[float] = []
        self._progress = 0.0
        self.setMinimumHeight(30)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(200, 30)

    def set_bars(self, bars: List[float]) -> None:
        self._bars = [max(0.0, min(1.0, float(bar))) for bar in (bars or [])]
        self.update()

    def set_progress(self, fraction: float) -> None:
        clamped = max(0.0, min(1.0, float(fraction)))
        if clamped == self._progress:
            return
        self._progress = clamped
        self.update()

    # ------------------------------------------------------------------
    def _emit_seek(self, x: float) -> None:
        width = max(1, self.width())
        fraction = max(0.0, min(1.0, x / width))
        # Update locally for snappy feedback; the player echoes back via set_progress.
        self.set_progress(fraction)
        self.seek_requested.emit(fraction)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_seek(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit_seek(event.position().x())
        super().mouseMoveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        played_color = QColor(theme.ACCENT)
        played_color.setAlpha(235)
        idle_color = QColor(theme.TEXT_SECONDARY)
        idle_color.setAlpha(110)

        # Before the real envelope arrives, draw a flat skeleton so the bubble
        # still reads as a voice note.
        if self._bars:
            levels = self._bars
        else:
            levels = [0.16] * self._bar_count
        count = len(levels)

        width = max(1, self.width())
        height = max(1, self.height())
        gap = 3.0
        bar_width = max(2.0, (width - gap * (count - 1)) / count)
        center_y = height / 2.0
        min_height = 3.0
        max_height = max(min_height, height - 4.0)

        for index, level in enumerate(levels):
            bar_height = min_height + level * (max_height - min_height)
            x = index * (bar_width + gap)
            y = center_y - (bar_height / 2.0)
            radius = min(bar_width / 2.0, 3.0)
            # A bar counts as "played" once the progress line passes its center.
            bar_fraction = (index + 0.5) / count
            painter.setBrush(
                played_color if bar_fraction <= self._progress else idle_color
            )
            painter.drawRoundedRect(x, y, bar_width, bar_height, radius, radius)
