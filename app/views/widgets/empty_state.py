"""
Empty state widget for displaying placeholder content.

Provides a consistent UI component for showing empty states
with icons, messages, and optional action buttons.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class EmptyStateWidget(QWidget):
    """
    Widget for displaying empty/placeholder states.

    Shows an icon, message, and optional action button in a centered layout.
    Useful for lists with no data, error states, or onboarding flows.

    Example:
        empty = EmptyStateWidget(
            icon="📭",
            message="No hay miembros registrados",
            action_text="Agregar Miembro",
            action_callback=lambda: print("Add member clicked")
        )
    """

    def __init__(
        self,
        icon: str = "📋",
        message: str = "No hay datos disponibles",
        submessage: Optional[str] = None,
        action_text: Optional[str] = None,
        action_callback: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        """
        Initialize the empty state widget.

        Args:
            icon: Emoji or icon to display
            message: Main message text
            submessage: Optional secondary message
            action_text: Optional button text
            action_callback: Optional callback when button is clicked
            parent: Parent widget
        """
        super().__init__(parent)
        self._icon = icon
        self._message = message
        self._submessage = submessage
        self._action_text = action_text
        self._action_callback = action_callback

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the empty state UI."""
        # Main layout - centered vertically and horizontally
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setSpacing(16)

        # Icon
        icon_label = QLabel(self._icon)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont("Arial", 64)
        icon_label.setFont(icon_font)
        icon_label.setStyleSheet("color: #bdc3c7;")
        main_layout.addWidget(icon_label)

        # Main message
        self._message_label = QLabel(self._message)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        message_font = QFont("Arial", 16, QFont.Weight.Bold)
        self._message_label.setFont(message_font)
        self._message_label.setStyleSheet("color: #7f8c8d; margin: 10px;")
        main_layout.addWidget(self._message_label)

        # Submessage (optional)
        if self._submessage:
            self._submessage_label = QLabel(self._submessage)
            self._submessage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._submessage_label.setWordWrap(True)
            submessage_font = QFont("Arial", 12)
            self._submessage_label.setFont(submessage_font)
            self._submessage_label.setStyleSheet("color: #95a5a6; margin-bottom: 10px;")
            main_layout.addWidget(self._submessage_label)

        # Action button (optional)
        if self._action_text and self._action_callback:
            self._action_button = QPushButton(self._action_text)
            self._action_button.clicked.connect(self._action_callback)
            self._action_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 12px 24px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #21618c;
                }
            """
            )
            self._action_button.setCursor(Qt.CursorShape.PointingHandCursor)

            # Center the button
            button_container = QWidget()
            button_layout = QVBoxLayout(button_container)
            button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            button_layout.addWidget(self._action_button)

            main_layout.addWidget(button_container)

        # Add stretch to keep content centered
        main_layout.addStretch()

    def update_message(self, message: str, submessage: Optional[str] = None) -> None:
        """
        Update the displayed message.

        Args:
            message: New main message
            submessage: Optional new submessage
        """
        self._message = message
        self._message_label.setText(message)

        if submessage and hasattr(self, "_submessage_label"):
            self._submessage = submessage
            self._submessage_label.setText(submessage)

    def update_icon(self, icon: str) -> None:
        """
        Update the displayed icon.

        Args:
            icon: New icon/emoji
        """
        self._icon = icon
        # Icon is in the first child of layout
        if self.layout().count() > 0:
            icon_label = self.layout().itemAt(0).widget()
            if isinstance(icon_label, QLabel):
                icon_label.setText(icon)

    def set_action_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the action button.

        Args:
            enabled: True to enable, False to disable
        """
        if hasattr(self, "_action_button"):
            self._action_button.setEnabled(enabled)


class LoadingStateWidget(QWidget):
    """
    Widget for displaying loading states.

    Shows a spinner animation and optional message.
    """

    def __init__(self, message: str = "Cargando...", parent=None):
        """
        Initialize the loading state widget.

        Args:
            message: Loading message to display
            parent: Parent widget
        """
        super().__init__(parent)
        self._message = message
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the loading state UI."""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        # Loading icon (spinner emoji as placeholder)
        icon_label = QLabel("⏳")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont("Arial", 48)
        icon_label.setFont(icon_font)
        layout.addWidget(icon_label)

        # Loading message
        message_label = QLabel(self._message)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_font = QFont("Arial", 14)
        message_label.setFont(message_font)
        message_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(message_label)

        layout.addStretch()

    def update_message(self, message: str) -> None:
        """
        Update the loading message.

        Args:
            message: New loading message
        """
        self._message = message
        if self.layout().count() > 1:
            message_label = self.layout().itemAt(1).widget()
            if isinstance(message_label, QLabel):
                message_label.setText(message)
