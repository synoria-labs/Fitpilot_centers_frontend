"""
Metric card widget for displaying key metrics in dashboards.

Provides a consistent, reusable card component for displaying metrics
with icons, values, and optional trend indicators.
"""

from typing import Optional
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class MetricCard(QFrame):
    """
    A card widget for displaying metrics with icon, title, value, and trend.

    Features:
    - Customizable color and icon
    - Large value display
    - Optional trend indicator
    - Click signal for interactivity

    Example:
        card = MetricCard(
            title="Miembros Activos",
            initial_value="156",
            icon="👥",
            color="#3498db"
        )
        card.update_value("162", trend="+6 esta semana")
        card.clicked.connect(lambda: print("Card clicked!"))
    """

    clicked = Signal()  # Emitted when card is clicked

    def __init__(
        self,
        title: str,
        initial_value: str = "0",
        icon: str = "📊",
        color: str = "#3498db",
        parent=None,
    ):
        """
        Initialize the metric card.

        Args:
            title: Title/label for the metric
            initial_value: Initial value to display
            icon: Emoji or icon character
            color: Color for borders and accents (hex format)
            parent: Parent widget
        """
        super().__init__(parent)
        self._title = title
        self._color = color
        self._icon = icon

        self._setup_ui()
        self._apply_styles()
        self.update_value(initial_value)

    def _setup_ui(self) -> None:
        """Set up the card UI structure."""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Header: Icon + Title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self._icon_label = QLabel(self._icon)
        self._icon_label.setStyleSheet(
            f"font-size: 24px; color: {self._color}; border: none;"
        )
        header_layout.addWidget(self._icon_label)

        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet(
            "color: #7f8c8d; font-size: 12px; font-weight: 500; border: none;"
        )
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Value
        self._value_label = QLabel("0")
        value_font = QFont("Arial", 28, QFont.Weight.Bold)
        self._value_label.setFont(value_font)
        self._value_label.setStyleSheet(f"color: {self._color}; border: none;")
        main_layout.addWidget(self._value_label)

        # Trend (optional)
        self._trend_label = QLabel()
        self._trend_label.setStyleSheet(
            "color: #95a5a6; font-size: 11px; border: none;"
        )
        self._trend_label.setVisible(False)
        main_layout.addWidget(self._trend_label)

        main_layout.addStretch()

    def _apply_styles(self) -> None:
        """Apply CSS styles to the card."""
        self.setStyleSheet(
            f"""
            MetricCard {{
                background-color: white;
                border: 2px solid {self._color};
                border-radius: 10px;
            }}
            MetricCard:hover {{
                background-color: #f8f9fa;
                border: 2px solid {self._color};
            }}
        """
        )

    def update_value(self, value: str, trend: Optional[str] = None) -> None:
        """
        Update the card's value and optional trend.

        Args:
            value: New value to display
            trend: Optional trend text (e.g., "↑ +10% vs mes anterior")
        """
        self._value_label.setText(str(value))

        if trend:
            self._trend_label.setText(trend)
            self._trend_label.setVisible(True)

            # Color based on trend direction
            if "↑" in trend or "+" in trend:
                self._trend_label.setStyleSheet(
                    "color: #27ae60; font-size: 11px; border: none;"
                )
            elif "↓" in trend or "-" in trend:
                self._trend_label.setStyleSheet(
                    "color: #e74c3c; font-size: 11px; border: none;"
                )
            else:
                self._trend_label.setStyleSheet(
                    "color: #95a5a6; font-size: 11px; border: none;"
                )
        else:
            self._trend_label.setVisible(False)

    def set_icon(self, icon: str) -> None:
        """
        Change the card's icon.

        Args:
            icon: New icon/emoji to display
        """
        self._icon = icon
        self._icon_label.setText(icon)

    def set_color(self, color: str) -> None:
        """
        Change the card's accent color.

        Args:
            color: New color in hex format (e.g., "#3498db")
        """
        self._color = color
        self._apply_styles()
        self._icon_label.setStyleSheet(
            f"font-size: 24px; color: {color}; border: none;"
        )
        self._value_label.setStyleSheet(f"color: {color}; border: none;")

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to emit clicked signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    @property
    def title(self) -> str:
        """Get the card title."""
        return self._title

    @property
    def value(self) -> str:
        """Get the current displayed value."""
        return self._value_label.text()
