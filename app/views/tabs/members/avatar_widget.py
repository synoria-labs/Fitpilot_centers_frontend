"""Avatar widget for member profile pictures."""

import os
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QRect, QSize, Qt, Signal, QPoint, QRectF
from PySide6.QtGui import (
    QAction, QBrush, QColor, QIcon, QPainter, QPainterPath,
    QPixmap, QPen, QFont, QCursor
)
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMenu,
    QWidget, QVBoxLayout, QHBoxLayout
)
from ....utils.dialog_helpers import show_confirmation, show_warning


class AvatarWidget(QWidget):
    """Circular avatar widget with upload/delete functionality."""

    image_changed = Signal(str)  # Emits new image path
    image_removed = Signal()  # Emits when image is removed
    clicked = Signal()  # Emits when avatar is clicked

    def __init__(
        self,
        size: int = 80,
        editable: bool = True,
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._editable = editable
        self._image_path: Optional[str] = None
        self._pixmap: Optional[QPixmap] = None
        self._initials: str = "?"
        self._hover = False

        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor if editable else Qt.CursorShape.ArrowCursor)
        self.setToolTip("Click para cambiar foto" if editable else "")

        # Context menu actions
        if editable:
            self.change_action = QAction("Cambiar foto", self)
            self.change_action.triggered.connect(self._on_change_image)

            self.remove_action = QAction("Eliminar foto", self)
            self.remove_action.triggered.connect(self._on_remove_image)

            self.view_action = QAction("Ver en tamaño completo", self)
            self.view_action.triggered.connect(self._on_view_image)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_image_from_url(self, url: Optional[str]) -> None:
        """Set image from a URL or file path."""
        if not url:
            self._clear_image()
            return

        # For now, assume it's a file path or URL
        # In production, you'd download from URL if needed
        self._image_path = url
        self._load_image()

    def set_image_from_file(self, file_path: str) -> None:
        """Set image from a local file path."""
        if not file_path or not os.path.exists(file_path):
            self._clear_image()
            return

        self._image_path = file_path
        self._load_image()

    def set_initials(self, name: str) -> None:
        """Set initials to display when no image is present."""
        if not name or name == "-":
            self._initials = "?"
        else:
            parts = name.strip().split()
            if len(parts) >= 2:
                self._initials = (parts[0][0] + parts[-1][0]).upper()
            elif parts:
                self._initials = parts[0][:2].upper()
            else:
                self._initials = "?"
        self.update()

    def clear_image(self) -> None:
        """Clear the current image."""
        self._clear_image()

    def has_image(self) -> bool:
        """Check if an image is currently set."""
        return self._pixmap is not None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        """Custom paint event to draw circular avatar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Create circular clip path
        path = QPainterPath()
        path.addEllipse(0, 0, self._size, self._size)
        painter.setClipPath(path)

        # Draw background
        bg_color = QColor("#f0f0f0")
        painter.fillRect(0, 0, self._size, self._size, bg_color)

        if self._pixmap:
            # Draw image
            scaled_pixmap = self._pixmap.scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # Center the image
            x = (self._size - scaled_pixmap.width()) // 2
            y = (self._size - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # Draw initials
            painter.setPen(QPen(QColor("#666666")))
            font = QFont()
            font.setPointSize(self._size // 3)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRect(0, 0, self._size, self._size),
                Qt.AlignmentFlag.AlignCenter,
                self._initials
            )

        # Draw border
        painter.setClipping(False)
        pen = QPen(QColor("#cccccc"), 2)
        if self._hover and self._editable:
            pen.setColor(QColor("#1976d2"))
            pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(1, 1, self._size - 2, self._size - 2)

        # Draw edit overlay on hover
        if self._hover and self._editable:
            painter.setClipPath(path)
            overlay = QColor(0, 0, 0, 100)
            painter.fillRect(0, 0, self._size, self._size, overlay)

            # Draw camera icon
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            font = QFont()
            font.setPointSize(self._size // 5)
            painter.setFont(font)
            painter.drawText(
                QRect(0, 0, self._size, self._size),
                Qt.AlignmentFlag.AlignCenter,
                "📷"
            )

    def enterEvent(self, event) -> None:
        """Handle mouse enter event."""
        if self._editable:
            self._hover = True
            self.update()

    def leaveEvent(self, event) -> None:
        """Handle mouse leave event."""
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._editable:
                self.clicked.emit()
                self._show_context_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Handle context menu event."""
        if self._editable:
            self._show_context_menu(event.globalPos())

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------
    def _load_image(self) -> None:
        """Load image from the current path."""
        if not self._image_path:
            self._pixmap = None
            self.update()
            return

        try:
            pixmap = QPixmap(self._image_path)
            if not pixmap.isNull():
                self._pixmap = pixmap
            else:
                self._pixmap = None
        except Exception as e:
            print(f"Error loading image: {e}")
            self._pixmap = None

        self.update()

    def _clear_image(self) -> None:
        """Clear the current image."""
        self._image_path = None
        self._pixmap = None
        self.update()

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show context menu for avatar actions."""
        if not self._editable:
            return

        menu = QMenu(self)
        menu.addAction(self.change_action)

        if self._pixmap:
            menu.addAction(self.view_action)
            menu.addSeparator()
            menu.addAction(self.remove_action)

        menu.exec(pos)

    def _on_change_image(self) -> None:
        """Handle change image action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar foto de perfil",
            "",
            "Imágenes (*.png *.jpg *.jpeg);;Todos los archivos (*.*)"
        )

        if file_path:
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > 5 * 1024 * 1024:  # 5MB limit
                show_warning(
                    self,
                    "El archivo seleccionado es muy grande. "
                    "Por favor selecciona una imagen menor a 5MB.",
                    title="Archivo muy grande",
                )
                return

            self.set_image_from_file(file_path)
            self.image_changed.emit(file_path)

    def _on_remove_image(self) -> None:
        """Handle remove image action."""
        if show_confirmation(
            self,
            "¿Estás seguro de que quieres eliminar la foto de perfil?",
            title="Eliminar foto",
            ok_text="Sí",
            cancel_text="No",
        ):
            self._clear_image()
            self.image_removed.emit()

    def _on_view_image(self) -> None:
        """Handle view image action."""
        if not self._pixmap:
            return

        # Create a simple dialog to show full image
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle("Foto de perfil")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        label = QLabel()

        # Scale image to reasonable size for viewing
        max_size = 500
        scaled_pixmap = self._pixmap.scaled(
            max_size, max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)
        layout.addWidget(label)

        dialog.exec()
