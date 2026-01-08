"""
ClassSeatIcon - Widget for displaying class seat status with dynamic icons
"""
from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
import qtawesome as qta


class ClassSeatIcon(QWidget):
    """
    Widget that displays a seat's status with a dynamic icon based on class type.

    Features:
    - Dynamic icons: bicycle (spinning), spa (yoga), music (pilates/zumba)
    - Color-coded status: Green (available), Red (occupied), Yellow (expiring soon)
    - Tooltip showing occupant name or "Disponible"
    """

    # Icon mapping by class type code
    ICON_MAP = {
        'spinning': 'fa5s.bicycle',
        'yoga': 'fa5s.spa',
        'pilates': 'fa5s.music',
        'zumba': 'fa5s.music',
    }

    # Status colors
    COLOR_AVAILABLE = '#4CAF50'  # Green
    COLOR_OCCUPIED = '#F44336'   # Red
    COLOR_EXPIRING = '#FFC107'   # Yellow (membership expiring soon)

    def __init__(
        self,
        class_type_code: str = 'spinning',
        status: str = 'free',
        occupant_name: Optional[str] = None,
        will_expire_soon: bool = False,
        icon_size: int = 32,
        parent: Optional[QWidget] = None
    ):
        """
        Initialize ClassSeatIcon.

        Args:
            class_type_code: Code for class type ('spinning', 'yoga', 'pilates', 'zumba')
            status: Seat status ('free' or 'occupied')
            occupant_name: Name of person occupying the seat (if occupied)
            will_expire_soon: True if occupant's membership expires within 2 days
            icon_size: Size of the icon in pixels
            parent: Parent widget
        """
        super().__init__(parent)

        self.class_type_code = class_type_code
        self.status = status
        self.occupant_name = occupant_name
        self.will_expire_soon = will_expire_soon
        self.icon_size = icon_size

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        # Increased horizontal padding to prevent icon clipping at edges
        # The bicycle icon wheels extend beyond the center, so we need more space
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)

        # Create icon label
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Set minimum size to ensure icon has enough space
        min_size = int(self.icon_size * 0.6)
        self.icon_label.setMinimumSize(QSize(min_size, min_size))

        # Set icon and color
        self._update_icon()

        layout.addWidget(self.icon_label)

        # Set tooltip
        self._update_tooltip()

    def _update_icon(self):
        """Update the icon based on class type and status"""
        # Get icon name for this class type
        icon_name = self.ICON_MAP.get(
            self.class_type_code.lower(),
            'fa5s.bicycle'  # Default to bicycle
        )

        # Determine color based on status
        if self.status == 'free':
            color = self.COLOR_AVAILABLE
        elif self.will_expire_soon:
            color = self.COLOR_EXPIRING
        else:
            color = self.COLOR_OCCUPIED

        # Create and set the icon
        # Using 0.4 factor instead of 0.5 to give the bicycle wheels more space
        icon = qta.icon(icon_name, color=color)
        actual_size = int(self.icon_size * 0.4)
        pixmap = icon.pixmap(QSize(actual_size, actual_size))
        self.icon_label.setPixmap(pixmap)

    def _update_tooltip(self):
        """Update the tooltip based on occupancy status"""
        if self.status == 'free':
            tooltip = "Disponible"
        elif self.occupant_name:
            if self.will_expire_soon:
                tooltip = f"{self.occupant_name}\n(Membresía por vencer)"
            else:
                tooltip = self.occupant_name
        else:
            tooltip = "Ocupado"

        self.setToolTip(tooltip)

    def update_status(
        self,
        status: str,
        occupant_name: Optional[str] = None,
        will_expire_soon: bool = False
    ):
        """
        Update the seat status and refresh the display.

        Args:
            status: New seat status ('free' or 'occupied')
            occupant_name: Name of occupant (if occupied)
            will_expire_soon: True if membership expires soon
        """
        self.status = status
        self.occupant_name = occupant_name
        self.will_expire_soon = will_expire_soon

        self._update_icon()
        self._update_tooltip()

    def update_class_type(self, class_type_code: str):
        """
        Update the class type and refresh the icon.

        Args:
            class_type_code: New class type code
        """
        self.class_type_code = class_type_code
        self._update_icon()


# Example usage and testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QLabel
    import sys

    app = QApplication(sys.argv)

    # Create test window
    window = QWidget()
    window.setWindowTitle("ClassSeatIcon Test")
    main_layout = QVBoxLayout(window)

    # Test different class types
    for class_type in ['spinning', 'yoga', 'pilates', 'zumba']:
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel(f"{class_type.capitalize()}:"))

        # Available
        icon1 = ClassSeatIcon(class_type, 'free')
        row_layout.addWidget(icon1)

        # Occupied
        icon2 = ClassSeatIcon(class_type, 'occupied', 'Juan Pérez')
        row_layout.addWidget(icon2)

        # Expiring soon
        icon3 = ClassSeatIcon(class_type, 'occupied', 'María López', will_expire_soon=True)
        row_layout.addWidget(icon3)

        row_layout.addStretch()
        main_layout.addLayout(row_layout)

    main_layout.addStretch()

    window.resize(400, 300)
    window.show()

    sys.exit(app.exec())
