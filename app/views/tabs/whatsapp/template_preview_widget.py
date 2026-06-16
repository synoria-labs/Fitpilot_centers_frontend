"""Reusable WhatsApp template preview with optional media header.

Header images load through the shared MediaLoader (async download + disk
cache), so the UI thread never blocks and repeated previews of the same asset
are served from cache. Failures fall back to a text card and are logged
(the previous urllib-based loader downloaded synchronously on the UI thread
and swallowed every error).
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....core.logging import get_logger
from ....services.media_loader import get_media_loader
from . import theme

logger = get_logger(__name__)


def _render_whatsapp_markup(text: str) -> str:
    """Render a small, safe subset of WhatsApp formatting for previews."""
    escaped = html.escape(text or "")
    code_blocks: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1))
        return f"\uE000CODE{len(code_blocks) - 1}\uE001"

    rendered = re.sub(r"```(.+?)```", stash_code, escaped, flags=re.DOTALL)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"~([^~\n]+?)~", r"<s>\1</s>", rendered)

    for index, code in enumerate(code_blocks):
        rendered = rendered.replace(
            f"\uE000CODE{index}\uE001",
            f'<code style="font-family: Consolas, monospace;">{code}</code>',
        )

    return rendered.replace("\n", "<br>")


class TemplatePreviewWidget(QWidget):
    """Dark WhatsApp-like preview for template body/footer and media header."""

    _MAX_BUBBLE_WIDTH = 620
    _MAX_IMAGE_HEIGHT = 260
    _MEDIA_VERTICAL_PADDING = 18
    _BODY_MIN_HEIGHT = 48

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("templatePreview")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Discards async media results that belong to an older set_preview call
        # (the tabs re-render the preview on every keystroke).
        self._media_request_seq = 0
        self._original_pixmap: Optional[QPixmap] = None

        self._scroll = QScrollArea()
        self._scroll.setObjectName("templatePreviewScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().setObjectName("templatePreviewViewport")

        self._thread = QWidget()
        self._thread.setObjectName("templatePreviewThread")
        thread_layout = QVBoxLayout(self._thread)
        thread_layout.setContentsMargins(10, 10, 10, 10)
        thread_layout.setSpacing(0)

        self._bubble = QFrame()
        self._bubble.setObjectName("templatePreviewBubble")
        self._bubble.setMaximumWidth(self._MAX_BUBBLE_WIDTH)
        self._bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        bubble_layout = QVBoxLayout(self._bubble)
        bubble_layout.setContentsMargins(8, 8, 8, 8)
        bubble_layout.setSpacing(8)

        self._media = QLabel()
        self._media.setObjectName("templatePreviewMedia")
        self._media.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._media.setMinimumHeight(0)
        self._media.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._media.setVisible(False)
        bubble_layout.addWidget(self._media)

        self._body = QTextEdit()
        self._body.setObjectName("templatePreviewText")
        self._body.setReadOnly(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._body.setFixedHeight(self._BODY_MIN_HEIGHT)
        bubble_layout.addWidget(self._body)

        self._footer = QLabel()
        self._footer.setObjectName("templatePreviewFooter")
        self._footer.setWordWrap(True)
        self._footer.setVisible(False)
        bubble_layout.addWidget(self._footer)

        thread_layout.addWidget(
            self._bubble,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        thread_layout.addStretch(1)
        self._scroll.setWidget(self._thread)
        root.addWidget(self._scroll)
        self.setStyleSheet(
            f"""
            QWidget#templatePreview {{
                background-color: palette(window);
                border: 1px solid {theme.DIVIDER};
                border-radius: 8px;
            }}
            QScrollArea#templatePreviewScroll {{
                background-color: palette(window);
                border: none;
            }}
            QScrollArea#templatePreviewScroll > QWidget > QWidget {{
                background-color: palette(window);
            }}
            QWidget#templatePreviewViewport {{
                background-color: palette(window);
            }}
            QWidget#templatePreviewThread {{
                background-color: palette(window);
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
        self._body.setHtml(_render_whatsapp_markup(body or ""))
        footer = (footer or "").strip()
        self._footer.setTextFormat(Qt.TextFormat.RichText)
        self._footer.setText(_render_whatsapp_markup(footer))
        self._footer.setVisible(bool(footer))
        self._update_body_height()
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
            self._original_pixmap = None
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
            self._original_pixmap = None
            self._media.setPixmap(QPixmap())
            self._media.setText("Cargando imagen...")
            self._media.setFixedHeight(82)
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
        self._original_pixmap = pixmap
        self._media.setText("")
        self._media.setVisible(True)
        self._refresh_image_pixmap()

    def _show_text_card(
        self, media_format: str, media_url: str, media_name: Optional[str]
    ) -> None:
        self._original_pixmap = None
        label = media_name or Path(media_url).name or "Archivo multimedia"
        self._media.setPixmap(QPixmap())
        self._media.setText(f"{media_format}\n{label}\n{media_url}")
        self._media.setFixedHeight(90)
        self._media.setVisible(True)

    def _refresh_image_pixmap(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            return
        available_width = self._bubble.width() or min(self.width() - 20, self._MAX_BUBBLE_WIDTH)
        target_width = max(160, available_width - 18)
        scaled = self._original_pixmap.scaled(
            target_width,
            self._MAX_IMAGE_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._media.setPixmap(scaled)
        self._media.setFixedHeight(scaled.height() + self._MEDIA_VERTICAL_PADDING)

    def _update_body_height(self) -> None:
        viewport_width = max(160, self._body.viewport().width())
        self._body.document().setTextWidth(viewport_width)
        document_height = int(self._body.document().size().height()) + 14
        self._body.setFixedHeight(max(self._BODY_MIN_HEIGHT, document_height))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        available_width = max(240, self.width() - 20)
        self._bubble.setMaximumWidth(min(self._MAX_BUBBLE_WIDTH, available_width))
        self._refresh_image_pixmap()
        self._update_body_height()
