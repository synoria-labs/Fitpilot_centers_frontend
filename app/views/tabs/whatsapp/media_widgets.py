"""Media widgets for chat bubbles (image, sticker, audio, video, document).

Files are fetched through the shared :mod:`media_loader` (async + disk cache).
Rendering states:

- backend still downloading -> :class:`PendingMediaWidget` (swapped via the
  ``messageUpdated`` subscription when the download finishes)
- backend download failed   -> :class:`FailedMediaWidget` (retry button)
- image/sticker             -> inline thumbnail, click to open a viewer
- audio                     -> inline player (system-player fallback on codec errors)
- video/document            -> file card, click downloads and opens externally
"""
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....core.logging import get_logger
from ....models.chat import ChatMessage
from ....services.media_loader import get_media_loader
from . import theme

logger = get_logger(__name__)

try:  # QtMultimedia may be missing in trimmed installs; degrade to file cards.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    _MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    _MULTIMEDIA_AVAILABLE = False

_IMAGE_MAX = 320
_STICKER_MAX = 160

_FILE_ICONS = {
    "video": "fa5s.file-video",
    "document": "fa5s.file-alt",
    "audio": "fa5s.file-audio",
}
_MIME_ICONS = {
    "application/pdf": "fa5s.file-pdf",
    "application/msword": "fa5s.file-word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "fa5s.file-word",
    "application/vnd.ms-excel": "fa5s.file-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "fa5s.file-excel",
    "application/vnd.ms-powerpoint": "fa5s.file-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "fa5s.file-powerpoint",
    "text/csv": "fa5s.file-csv",
}


def _webp_supported() -> bool:
    return b"webp" in [bytes(f) for f in QImageReader.supportedImageFormats()]


def _human_size(num: Optional[int]) -> str:
    if not num or num <= 0:
        return ""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def _media_type_label(media_type: str) -> str:
    return theme.MEDIA_LABELS.get(media_type, media_type or "archivo")


def create_media_widget(message: ChatMessage, parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Build the widget for a message attachment, or None for plain text."""
    if not message.is_media:
        return None

    media_type = message.media.media_type if message.media else message.message_type

    if message.media_failed:
        return FailedMediaWidget(message.id, media_type, parent)
    if message.media_pending or not (message.media and message.media.absolute_url):
        return PendingMediaWidget(media_type, parent)

    if media_type in ("image", "sticker"):
        if media_type == "sticker" and not _webp_supported():
            # Frozen builds may miss the qwebp image plugin.
            return FileCardWidget(message, parent)
        return ImageMediaWidget(message, parent)
    if media_type == "audio":
        if not _MULTIMEDIA_AVAILABLE:
            return FileCardWidget(message, parent)
        return AudioMediaWidget(message, parent)
    return FileCardWidget(message, parent)


class PendingMediaWidget(QFrame):
    """Placeholder while the backend is still downloading the attachment."""

    def __init__(self, media_type: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon("fa5s.clock", color=theme.TEXT_SECONDARY).pixmap(QSize(18, 18))
        )
        layout.addWidget(icon_label)

        label_text = _media_type_label(media_type).split(" ", 1)[-1].lower()
        text = QLabel(f"Recibiendo {label_text}...")
        text.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(text)
        layout.addStretch()


class FailedMediaWidget(QFrame):
    """Shown when the backend could not download the file; offers a retry."""

    retry_requested = Signal(int)  # message id

    def __init__(self, message_id: int, media_type: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon("fa5s.exclamation-triangle", color="#E9A23B").pixmap(QSize(18, 18))
        )
        layout.addWidget(icon_label)

        label_text = _media_type_label(media_type).split(" ", 1)[-1].lower()
        text = QLabel(f"No se pudo descargar el {label_text}.")
        text.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(text)

        retry = QPushButton("Reintentar")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.setStyleSheet(
            f"QPushButton {{ color: {theme.ACCENT}; background: transparent;"
            f" border: 1px solid {theme.ACCENT}; border-radius: 4px; padding: 2px 10px; }}"
            f"QPushButton:hover {{ background-color: {theme.ITEM_SELECTED}; }}"
        )
        retry.clicked.connect(lambda: self.retry_requested.emit(message_id))
        layout.addWidget(retry)
        layout.addStretch()


class ImageMediaWidget(QLabel):
    """Inline thumbnail for images/stickers; click opens a full-size viewer."""

    def __init__(self, message: ChatMessage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._media = message.media
        self._pixmap: Optional[QPixmap] = None
        self._max_side = _STICKER_MAX if self._media.media_type == "sticker" else _IMAGE_MAX

        self.setText("Cargando imagen...")
        self.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px; padding: 12px;")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self._handle = get_media_loader().fetch(self._media.absolute_url)
        self._handle.finished.connect(self._on_file_ready)
        self._handle.failed.connect(self._on_failed)

    def _on_file_ready(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._on_failed("Formato de imagen no soportado.")
            return
        self._pixmap = pixmap
        scaled = pixmap.scaled(
            self._max_side,
            self._max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setStyleSheet("padding: 0;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clic para ampliar")

    def _on_failed(self, error: str) -> None:
        logger.warning("No se pudo mostrar la imagen %s: %s", self._media.absolute_url, error)
        self.setText("No se pudo cargar la imagen.")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._pixmap is not None and event.button() == Qt.MouseButton.LeftButton:
            ImageViewerDialog(self._pixmap, self._media.filename or "Imagen", self.window()).exec()
        super().mousePressEvent(event)


class ImageViewerDialog(QDialog):
    """Full-size image viewer (scaled to the available screen)."""

    def __init__(self, pixmap: QPixmap, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(f"background-color: {theme.THREAD_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        screen = self.screen() or (parent.screen() if parent else None)
        if screen is not None:
            available = screen.availableGeometry().size() * 0.9
        else:
            available = QSize(1024, 768)
        if pixmap.width() > available.width() or pixmap.height() > available.height():
            pixmap = pixmap.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.accept()
        super().mousePressEvent(event)


class AudioMediaWidget(QFrame):
    """Inline audio player (voice notes). Falls back to the system player when
    the platform backend cannot decode the codec (e.g. ogg/opus on WMF)."""

    def __init__(self, message: ChatMessage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._media = message.media
        self._path: Optional[str] = None
        self._player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None
        self._duration_ms = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(8)

        self._play_button = QToolButton()
        self._play_button.setIcon(qta.icon("fa5s.play", color=theme.TEXT_PRIMARY))
        self._play_button.setIconSize(QSize(16, 16))
        self._play_button.setFixedSize(32, 32)
        self._play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_button.setEnabled(False)
        self._play_button.setStyleSheet(
            f"QToolButton {{ background-color: {theme.ITEM_SELECTED}; border-radius: 16px; }}"
        )
        self._play_button.clicked.connect(self._toggle_playback)
        layout.addWidget(self._play_button)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimumWidth(150)
        self._slider.setEnabled(False)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._slider, 1)

        self._time_label = QLabel("--:--")
        self._time_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self._time_label)

        self._fallback_button = QPushButton("Abrir con el reproductor del sistema")
        self._fallback_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fallback_button.setStyleSheet(
            f"QPushButton {{ color: {theme.ACCENT}; background: transparent; border: none; }}"
        )
        self._fallback_button.clicked.connect(self._open_externally)
        self._fallback_button.hide()
        layout.addWidget(self._fallback_button)

        self._handle = get_media_loader().fetch(self._media.absolute_url)
        self._handle.finished.connect(self._on_file_ready)
        self._handle.failed.connect(self._on_failed)

    # ------------------------------------------------------------------
    def _on_file_ready(self, path: str) -> None:
        self._path = path
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._play_button.setEnabled(True)
        self._slider.setEnabled(True)

    def _on_failed(self, error: str) -> None:
        logger.warning("No se pudo descargar el audio %s: %s", self._media.absolute_url, error)
        self._time_label.setText("Audio no disponible")

    def _toggle_playback(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        icon = "fa5s.pause" if playing else "fa5s.play"
        self._play_button.setIcon(qta.icon(icon, color=theme.TEXT_PRIMARY))

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = max(0, duration)
        self._slider.setRange(0, self._duration_ms)
        self._time_label.setText(self._fmt_ms(self._duration_ms))

    def _on_position_changed(self, position: int) -> None:
        if not self._slider.isSliderDown():
            self._slider.setValue(position)
        remaining = self._duration_ms - position if self._duration_ms else position
        self._time_label.setText(self._fmt_ms(remaining))

    def _on_slider_moved(self, value: int) -> None:
        if self._player is not None:
            self._player.setPosition(value)

    def _on_player_error(self, _error, error_string: str = "") -> None:
        logger.warning(
            "QMediaPlayer no pudo reproducir %s: %s", self._path, error_string
        )
        # Codec not supported by the platform backend: degrade to external player.
        self._play_button.hide()
        self._slider.hide()
        self._time_label.hide()
        self._fallback_button.show()
        if self._player is not None:
            self._player.stop()

    def _open_externally(self) -> None:
        if self._path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        seconds = max(0, int(ms / 1000))
        return f"{seconds // 60}:{seconds % 60:02d}"


class FileCardWidget(QFrame):
    """Card for videos/documents: icon + name + size; click opens externally.

    The file is only downloaded on the first click (videos/documents can be
    large), with the card itself reflecting the download state.
    """

    def __init__(self, message: ChatMessage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._media = message.media
        self._downloading = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"FileCardWidget {{ background-color: {theme.ITEM_SELECTED}; border-radius: 6px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icon_name = _MIME_ICONS.get(
            (self._media.mime_type or "").lower(),
            _FILE_ICONS.get(self._media.media_type, "fa5s.file"),
        )
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=theme.TEXT_PRIMARY).pixmap(QSize(26, 26)))
        layout.addWidget(icon_label)

        text_column = QVBoxLayout()
        text_column.setSpacing(1)

        name = self._media.filename or _media_type_label(self._media.media_type)
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 12px;")
        name_label.setWordWrap(True)
        text_column.addWidget(name_label)

        self._status_label = QLabel(_human_size(self._media.file_size) or "Clic para abrir")
        self._status_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        text_column.addWidget(self._status_label)
        layout.addLayout(text_column, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and not self._downloading:
            self._open()
        super().mousePressEvent(event)

    def _open(self) -> None:
        loader = get_media_loader()
        cached = loader.cached_path(self._media.absolute_url or "")
        if cached is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(cached)))
            return

        self._downloading = True
        self._status_label.setText("Descargando...")
        self._handle = loader.fetch(self._media.absolute_url)
        self._handle.finished.connect(self._on_file_ready)
        self._handle.failed.connect(self._on_failed)

    def _on_file_ready(self, path: str) -> None:
        self._downloading = False
        self._status_label.setText(_human_size(self._media.file_size) or "Clic para abrir")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_failed(self, error: str) -> None:
        self._downloading = False
        logger.warning("No se pudo descargar %s: %s", self._media.absolute_url, error)
        self._status_label.setText("No se pudo descargar. Clic para reintentar.")
