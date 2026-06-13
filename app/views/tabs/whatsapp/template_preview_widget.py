"""Reusable WhatsApp template preview with optional media header.

Header images load through the shared MediaLoader (async download + disk
cache), so the UI thread never blocks and repeated previews of the same asset
are served from cache. Failures fall back to a text card and are logged
(the previous urllib-based loader downloaded synchronously on the UI thread
and swallowed every error).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QTextEdit, QVBoxLayout, QWidget

from ....core.logging import get_logger
from ....services.media_loader import get_media_loader
from . import theme

logger = get_logger(__name__)


class TemplatePreviewWidget(QWidget):
    """Dark WhatsApp-like preview for template body/footer and media header."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("templatePreview")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Discards async media results that belong to an older set_preview call
        # (the tabs re-render the preview on every keystroke).
        self._media_request_seq = 0

        self._bubble = QFrame()
        self._bubble.setObjectName("templatePreviewBubble")
        bubble_layout = QVBoxLayout(self._bubble)
        bubble_layout.setContentsMargins(10, 10, 10, 8)
        bubble_layout.setSpacing(8)

        self._media = QLabel()
        self._media.setObjectName("templatePreviewMedia")
        self._media.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._media.setMinimumHeight(0)
        self._media.setVisible(False)
        bubble_layout.addWidget(self._media)

        self._body = QTextEdit()
        self._body.setObjectName("templatePreviewText")
        self._body.setReadOnly(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setMinimumHeight(90)
        self._body.setMaximumHeight(170)
        bubble_layout.addWidget(self._body)

        self._footer = QLabel()
        self._footer.setObjectName("templatePreviewFooter")
        self._footer.setWordWrap(True)
        self._footer.setVisible(False)
        bubble_layout.addWidget(self._footer)

        root.addWidget(self._bubble)
        self.setStyleSheet(
            f"""
            QWidget#templatePreview {{
                background-color: {theme.THREAD_BG};
                border: 1px solid {theme.DIVIDER};
                border-radius: 8px;
            }}
            QFrame#templatePreviewBubble {{
                background-color: {theme.BUBBLE_IN};
                border-radius: 8px;
            }}
            QLabel#templatePreviewMedia {{
                background-color: {theme.INPUT_BG};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.DIVIDER};
                border-radius: 7px;
                padding: 8px;
                font-size: 12px;
            }}
            QTextEdit#templatePreviewText {{
                background: transparent;
                color: {theme.TEXT_PRIMARY};
                border: none;
                font-size: 13px;
                selection-background-color: {theme.ACCENT};
                selection-color: #ffffff;
            }}
            QLabel#templatePreviewFooter {{
                color: {theme.TEXT_SECONDARY};
                background: transparent;
                font-size: 12px;
            }}
            """
        )

    def set_preview(
        self,
        *,
        body: str,
        footer: Optional[str] = None,
        media_format: Optional[str] = None,
        media_url: Optional[str] = None,
        media_name: Optional[str] = None,
    ) -> None:
        self._body.setPlainText(body or "")
        footer = (footer or "").strip()
        self._footer.setText(footer)
        self._footer.setVisible(bool(footer))
        self._render_media(media_format, media_url, media_name)

    def _render_media(
        self,
        media_format: Optional[str],
        media_url: Optional[str],
        media_name: Optional[str],
    ) -> None:
        self._media_request_seq += 1
        media_format = (media_format or "").upper()
        media_url = (media_url or "").strip()
        if not media_format:
            self._media.clear()
            self._media.setVisible(False)
            return

        if media_format == "IMAGE" and media_url:
            cached = get_media_loader().cached_path(media_url)
            if cached is not None:
                pixmap = QPixmap(str(cached))
                if not pixmap.isNull():
                    self._show_image(pixmap)
                    return

            # Async fetch; only the latest request may update the label.
            request_id = self._media_request_seq
            self._media.setPixmap(QPixmap())
            self._media.setText("Cargando imagen...")
            self._media.setMinimumHeight(74)
            self._media.setVisible(True)

            self._media_handle = get_media_loader().fetch(media_url)
            self._media_handle.finished.connect(
                lambda path, rid=request_id: self._on_media_ready(rid, path, media_format, media_url, media_name)
            )
            self._media_handle.failed.connect(
                lambda error, rid=request_id: self._on_media_failed(rid, error, media_format, media_url, media_name)
            )
            return

        self._show_text_card(media_format, media_url, media_name)

    def _on_media_ready(
        self, request_id: int, path: str, media_format: str, media_url: str, media_name: Optional[str]
    ) -> None:
        if request_id != self._media_request_seq:
            return  # a newer preview replaced this request
        pixmap = QPixmap(path)
        if pixmap.isNull():
            logger.warning("Preview de plantilla: formato de imagen no soportado (%s)", media_url)
            self._show_text_card(media_format, media_url, media_name)
            return
        self._show_image(pixmap)

    def _on_media_failed(
        self, request_id: int, error: str, media_format: str, media_url: str, media_name: Optional[str]
    ) -> None:
        if request_id != self._media_request_seq:
            return
        logger.warning("Preview de plantilla: no se pudo descargar %s: %s", media_url, error)
        self._show_text_card(media_format, media_url, media_name)

    def _show_image(self, pixmap: QPixmap) -> None:
        self._media.setText("")
        self._media.setPixmap(
            pixmap.scaled(
                520,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._media.setMinimumHeight(120)
        self._media.setVisible(True)

    def _show_text_card(
        self, media_format: str, media_url: str, media_name: Optional[str]
    ) -> None:
        label = media_name or Path(media_url).name or "Archivo multimedia"
        self._media.setPixmap(QPixmap())
        self._media.setText(f"{media_format}\n{label}\n{media_url}")
        self._media.setMinimumHeight(74)
        self._media.setVisible(True)
