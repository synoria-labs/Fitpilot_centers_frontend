"""Confirmation dialog shown before sending an attachment.

Shows a thumbnail (images) or a file card, lets the user type a caption, and
validates the size locally against the WhatsApp Cloud API limits so oversized
files are rejected before the upload starts.
"""
import mimetypes
from pathlib import Path
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme

# Mirror of backend whatsapp_media_assets_service.MAX_BYTES (WhatsApp limits).
_MAX_BYTES = {
    "image": 5 * 1024 * 1024,
    "video": 16 * 1024 * 1024,
    "audio": 16 * 1024 * 1024,
    "document": 100 * 1024 * 1024,
}

_PREVIEW_MAX = 280

FILE_DIALOG_FILTER = (
    "Multimedia (*.jpg *.jpeg *.png *.mp4 *.3gp *.mp3 *.aac *.amr *.ogg *.pdf"
    " *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.txt *.csv);;Todos los archivos (*.*)"
)


def _media_kind_for_path(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = (mime or "").lower()
    for prefix, kind in (("image/", "image"), ("audio/", "audio"), ("video/", "video")):
        if mime.startswith(prefix):
            return kind
    return "document"


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


class AttachmentPreviewDialog(QDialog):
    """Preview + caption + local size validation for an attachment."""

    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = Path(file_path)
        self._kind = _media_kind_for_path(self._path)

        self.setWindowTitle("Enviar archivo")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(self._build_preview())

        self.caption_input = QLineEdit()
        self.caption_input.setPlaceholderText(
            "Añade un comentario..." if self._kind != "audio" else "El audio se envía sin comentario"
        )
        self.caption_input.setEnabled(self._kind != "audio")
        layout.addWidget(self.caption_input)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #E9A23B; font-size: 12px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Enviar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._send_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._validate()

    @property
    def caption(self) -> str:
        return self.caption_input.text().strip()

    @property
    def file_path(self) -> str:
        return str(self._path)

    # ------------------------------------------------------------------
    def _build_preview(self) -> QWidget:
        if self._kind == "image":
            pixmap = QPixmap(str(self._path))
            if not pixmap.isNull():
                label = QLabel()
                label.setPixmap(
                    pixmap.scaled(
                        _PREVIEW_MAX,
                        _PREVIEW_MAX,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                return label

        card = QWidget()
        row = QHBoxLayout(card)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        icons = {"video": "fa5s.file-video", "audio": "fa5s.file-audio"}
        icon_label = QLabel()
        icon_label.setPixmap(
            qta.icon(icons.get(self._kind, "fa5s.file-alt"), color=theme.TEXT_PRIMARY)
            .pixmap(QSize(32, 32))
        )
        row.addWidget(icon_label)

        column = QVBoxLayout()
        column.setSpacing(1)
        name_label = QLabel(self._path.name)
        name_label.setWordWrap(True)
        column.addWidget(name_label)
        try:
            size_text = _human_size(self._path.stat().st_size)
        except OSError:
            size_text = ""
        size_label = QLabel(size_text)
        size_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        column.addWidget(size_label)
        row.addLayout(column, 1)
        return card

    def _validate(self) -> None:
        try:
            size = self._path.stat().st_size
        except OSError:
            self._show_error("No se pudo leer el archivo.")
            return
        limit = _MAX_BYTES[self._kind]
        if size > limit:
            mb = limit // (1024 * 1024)
            kind_names = {
                "image": "imágenes",
                "video": "videos",
                "audio": "audios",
                "document": "documentos",
            }
            self._show_error(
                f"El archivo pesa {_human_size(size)}; el límite de WhatsApp para "
                f"{kind_names[self._kind]} es {mb} MB."
            )

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
        self._send_button.setEnabled(False)
