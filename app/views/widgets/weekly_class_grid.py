"""
WeeklyClassGrid - Widget displaying a week view of class seats
"""
from typing import Optional, List, Dict
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, QVBoxLayout, QFrame
)
from PySide6.QtCore import Qt, Signal
from .class_seat_icon import ClassSeatIcon


class DayLabel(QLabel):
    """Clickable label used to select a day in the grid."""

    clicked = Signal(object)

    def __init__(self, day_date: date, text: str) -> None:
        super().__init__(text)
        self._day_date = day_date
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._day_date)
        super().mousePressEvent(event)


class WeeklyClassGrid(QWidget):
    """
    Widget that displays a weekly grid of class seats.

    Features:
    - Rows: 7 days (Monday - Sunday)
    - Columns: Variable number of seats (capacity)
    - Dynamic icons based on class type
    - Color-coded availability
    """

    # Spanish day names
    DAY_NAMES = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']

    # Month names in Spanish
    MONTH_NAMES = {
        1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
    }

    # Signal emitted when a day label is clicked
    day_selected = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize WeeklyClassGrid.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.week_start = None
        self.class_type_code = 'spinning'
        self.sessions_by_day: Dict[date, Dict] = {}  # date -> session data
        self.selected_date: Optional[date] = None


        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 10)  # Removed horizontal margins, let scroll handle it
        main_layout.setSpacing(5)

        # Scroll area for the grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Set viewport margins to prevent icon clipping at edges
        scroll.setViewportMargins(20, 0, 20, 0)
        # Style to ensure no additional clipping
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # Container for the grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(30, 15, 30, 15)  # Increased horizontal margins further

        scroll.setWidget(self.grid_container)
        main_layout.addWidget(scroll)

        # Empty state label
        self.empty_label = QLabel("No hay sesiones programadas para esta semana")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_label.setVisible(False)
        main_layout.addWidget(self.empty_label)

    def populate_grid(
        self,
        week_start: date,
        sessions_by_day: Dict[date, Dict],
        class_type_code: str = 'spinning'
    ):
        """
        Populate the grid with session data for a week.

        Args:
            week_start: Monday of the week to display
            sessions_by_day: Dictionary mapping dates to session data
                Each session should have: {
                    'id': int,
                    'capacity': int,
                    'seats': [
                        {
                            'seat_id': int,
                            'label': str,
                            'status': 'free' | 'occupied',
                            'occupant': {'person_id': int, 'full_name': str} | None,
                            'will_expire_soon': bool
                        },
                        ...
                    ]
                }
            class_type_code: Code for the class type (for icon selection)
        """
        self.week_start = week_start
        self.sessions_by_day = sessions_by_day
        self.class_type_code = class_type_code

        # Clear existing grid
        self._clear_grid()

        # Check if we have any sessions
        if not sessions_by_day or all(not v for v in sessions_by_day.values()):
            self.grid_container.setVisible(False)
            self.empty_label.setVisible(True)
            return

        self.grid_container.setVisible(True)
        self.empty_label.setVisible(False)

        # Determine max seats across all days
        max_seats = 0
        for session in sessions_by_day.values():
            if session and 'seats' in session:
                max_seats = max(max_seats, len(session['seats']))

        if max_seats == 0:
            self.grid_container.setVisible(False)
            self.empty_label.setVisible(True)
            return

        # Create header row (seat numbers)
        self._create_header_row(max_seats)

        # Create rows for each day
        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            self._create_day_row(day_offset, current_date, max_seats)

    def set_selected_date(self, selected_date: Optional[date]) -> None:
        """Store selected date and repaint the grid."""
        self.selected_date = selected_date
        if self.week_start is not None:
            self.populate_grid(self.week_start, self.sessions_by_day, self.class_type_code)

    def _create_header_row(self, num_seats: int):
        """Create the header row with seat numbers"""
        # Empty top-left corner
        corner_label = QLabel("")
        corner_label.setFixedHeight(30)
        corner_label.setStyleSheet("background-color: #2c3e50; border: 1px solid #34495e;")
        self.grid_layout.addWidget(corner_label, 0, 0)

        # Left spacer column to prevent first icon from being clipped
        left_spacer = QLabel("")
        left_spacer.setFixedWidth(15)
        left_spacer.setStyleSheet("background-color: transparent; border: none;")
        self.grid_layout.addWidget(left_spacer, 0, 1)

        # Seat number headers (shifted by 1 to account for left spacer)
        for seat_idx in range(num_seats):
            header_label = QLabel(str(seat_idx + 1))
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    color: #ecf0f1;
                    background-color: #2c3e50;
                    border: 1px solid #34495e;
                    padding: 5px;
                }
            """)
            self.grid_layout.addWidget(header_label, 0, seat_idx + 2)  # +2 for day column and left spacer

        # Right spacer column to prevent last icon from being clipped
        right_spacer = QLabel("")
        right_spacer.setFixedWidth(15)
        right_spacer.setStyleSheet("background-color: transparent; border: none;")
        self.grid_layout.addWidget(right_spacer, 0, num_seats + 2)

    def _create_day_row(self, row_idx: int, current_date: date, max_seats: int):
        """Create a row for a specific day"""
        grid_row = row_idx + 1  # +1 because row 0 is header

        # Day label (first column)
        day_label = self._create_day_label(current_date, row_idx)
        self.grid_layout.addWidget(day_label, grid_row, 0)

        # Left spacer column
        left_spacer = QLabel("")
        left_spacer.setFixedWidth(15)
        left_spacer.setStyleSheet("background-color: transparent; border: none;")
        self.grid_layout.addWidget(left_spacer, grid_row, 1)

        # Get session for this day
        session = self.sessions_by_day.get(current_date)

        if not session or 'seats' not in session:
            # No session - show free icons to keep row visible
            for seat_idx in range(max_seats):
                icon = ClassSeatIcon(
                    class_type_code=self.class_type_code,
                    status='free',
                    occupant_name=None,
                    will_expire_soon=False,
                    icon_size=100
                )
                self.grid_layout.addWidget(icon, grid_row, seat_idx + 2, Qt.AlignmentFlag.AlignCenter)
        else:
            # Create seat icons
            seats = session['seats']
            for seat_idx in range(max_seats):
                if seat_idx < len(seats):
                    seat_data = seats[seat_idx]

                    # Extract occupant name
                    occupant_name = None
                    if seat_data.get('occupant'):
                        occupant_name = seat_data['occupant'].get('fullName') or seat_data['occupant'].get('full_name')

                    # Create seat icon
                    icon = ClassSeatIcon(
                        class_type_code=self.class_type_code,
                        status=seat_data['status'],
                        occupant_name=occupant_name,
                        will_expire_soon=seat_data.get('will_expire_soon', False),
                        icon_size=100
                    )

                    # Add icon directly to grid with center alignment
                    self.grid_layout.addWidget(icon, grid_row, seat_idx + 2, Qt.AlignmentFlag.AlignCenter)
                else:
                    # Seat doesn't exist for this session
                    empty_label = QLabel("-")
                    empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    empty_label.setStyleSheet("color: #ccc;")
                    self.grid_layout.addWidget(empty_label, grid_row, seat_idx + 2)

        # Right spacer column
        right_spacer = QLabel("")
        right_spacer.setFixedWidth(15)
        right_spacer.setStyleSheet("background-color: transparent; border: none;")
        self.grid_layout.addWidget(right_spacer, grid_row, max_seats + 2)

    def _create_day_label(self, current_date: date, day_offset: int) -> QLabel:
        """Create a label for a day with name and date"""
        day_name = self.DAY_NAMES[day_offset]
        day_num = current_date.day
        month_name = self.MONTH_NAMES[current_date.month]

        label_text = f"{day_name}\n{day_num} {month_name}"

        label = DayLabel(current_date, label_text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        default_style = (
            "QLabel {"
            "font-weight: bold;"
            "color: #2c3e50;"
            "background-color: #ecf0f1;"
            "border: 1px solid #bdc3c7;"
            "padding: 10px 5px;"
            "min-width: 80px;"
            "}"
        )

        selected_style = (
            "QLabel {"
            "font-weight: bold;"
            "color: #7d6608;"
            "background-color: #fef5e7;"
            "border: 2px solid #f39c12;"
            "padding: 9px 4px;"
            "min-width: 80px;"
            "}"
        )

        today_style = (
            "QLabel {"
            "font-weight: bold;"
            "color: #ffffff;"
            "background-color: #3498db;"
            "border: 2px solid #2980b9;"
            "padding: 10px 5px;"
            "min-width: 80px;"
            "}"
        )

        selected_today_style = (
            "QLabel {"
            "font-weight: bold;"
            "color: #ffffff;"
            "background-color: #3498db;"
            "border: 3px solid #f39c12;"
            "padding: 9px 4px;"
            "min-width: 80px;"
            "}"
        )

        is_selected = self.selected_date == current_date
        is_today = current_date == date.today()

        if is_selected and is_today:
            label.setStyleSheet(selected_today_style)
        elif is_selected:
            label.setStyleSheet(selected_style)
        elif is_today:
            label.setStyleSheet(today_style)
        else:
            label.setStyleSheet(default_style)

        label.clicked.connect(self.day_selected.emit)

        return label

    def _clear_grid(self):
        """Clear all widgets from the grid"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_loading(self):
        """Show loading state"""
        self._clear_grid()
        self.grid_container.setVisible(False)
        self.empty_label.setText("Cargando...")
        self.empty_label.setVisible(True)

    def show_error(self, message: str = "Error al cargar las sesiones"):
        """Show error state"""
        self._clear_grid()
        self.grid_container.setVisible(False)
        self.empty_label.setText(message)
        self.empty_label.setStyleSheet("""
            QLabel {
                color: #d32f2f;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_label.setVisible(True)


# Example usage and testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from datetime import datetime
    import sys

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("WeeklyClassGrid Test")
    layout = QVBoxLayout(window)

    # Create grid
    grid = WeeklyClassGrid()
    layout.addWidget(grid)

    # Sample data
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Get Monday

    sample_sessions = {}
    for i in range(7):
        current_date = week_start + timedelta(days=i)

        # Create sample session with 14 seats
        if i not in [2, 5]:  # Skip Wednesday and Saturday for variety
            seats = []
            for j in range(14):
                # Alternate between free and occupied
                if j % 3 == 0:
                    status = 'free'
                    occupant = None
                    will_expire = False
                elif j % 3 == 1:
                    status = 'occupied'
                    occupant = {'person_id': j, 'full_name': f'Persona {j}'}
                    will_expire = False
                else:
                    status = 'occupied'
                    occupant = {'person_id': j, 'full_name': f'Usuario {j}'}
                    will_expire = True

                seats.append({
                    'seat_id': j + 1,
                    'label': str(j + 1),
                    'status': status,
                    'occupant': occupant,
                    'will_expire_soon': will_expire
                })

            sample_sessions[current_date] = {
                'id': i + 1,
                'capacity': 14,
                'seats': seats
            }

    grid.populate_grid(week_start, sample_sessions, 'spinning')

    window.resize(1000, 600)
    window.show()

    sys.exit(app.exec())
