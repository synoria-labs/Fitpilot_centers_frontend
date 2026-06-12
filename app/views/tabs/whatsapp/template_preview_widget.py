"""Reusable WhatsApp template preview with optional media header."""
from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QTextEdit, QVBoxLayout, QWidget

from . import theme


class TemplatePreviewWidget(QWidget):
    """Dark WhatsApp-like preview for template body/footer and media header."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("templatePreview")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

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
        media_format = (media_format or "").upper()
        media_url = (media_url or "").strip()
        if not media_format:
            self._media.clear()
            self._media.setVisible(False)
            return

        if media_format == "IMAGE" and media_url:
            pixmap = self._load_pixmap(media_url)
            if not pixmap.isNull():
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
                return

        label = media_name or Path(media_url).name or "Archivo multimedia"
        self._media.setPixmap(QPixmap())
        self._media.setText(f"{media_format}\n{label}\n{media_url}")
        self._media.setMinimumHeight(74)
        self._media.setVisible(True)

    @staticmethod
    def _load_pixmap(source: str) -> QPixmap:
        pixmap = QPixmap()
        try:
            if source.startswith("http://") or source.startswith("https://"):
                with urllib.request.urlopen(source, timeout=5) as response:
                    pixmap.loadFromData(response.read())
            else:
                pixmap.load(source)
        except Exception:
            return QPixmap()
        return pixmap
