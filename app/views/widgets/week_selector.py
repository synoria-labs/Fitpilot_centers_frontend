"""
WeekSelector - Widget for navigating between weeks
"""
from datetime import date, timedelta
from typing import Optional
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt


class WeekSelector(QWidget):
    """
    Widget for selecting and navigating between weeks.

    Features:
    - Previous/Next week buttons
    - Display current week range
    - "Hoy" (Today) button to jump to current week
    - Emits signal when week changes
    """

    # Signal emitted when the selected week changes
    # Parameters: (start_date, end_date)
    week_changed = Signal(date, date)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize WeekSelector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Initialize with current week
        self.current_start_date = self._get_week_start(date.today())
        self.current_end_date = self.current_start_date + timedelta(days=6)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Previous week button
        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.setFixedWidth(100)
        self.btn_prev.clicked.connect(self._go_to_previous_week)
        layout.addWidget(self.btn_prev)

        # Week range label
        self.label_week = QLabel()
        self.label_week.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_week.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                padding: 5px 15px;
            }
        """)
        self._update_week_label()
        layout.addWidget(self.label_week, 1)

        # Next week button
        self.btn_next = QPushButton("Siguiente ▶")
        self.btn_next.setFixedWidth(100)
        self.btn_next.clicked.connect(self._go_to_next_week)
        layout.addWidget(self.btn_next)

        # Today button
        self.btn_today = QPushButton("Hoy")
        self.btn_today.setFixedWidth(70)
        self.btn_today.clicked.connect(self._go_to_current_week)
        layout.addWidget(self.btn_today)

    def _get_week_start(self, target_date: date) -> date:
        """
        Get the Monday of the week containing the target date.

        Args:
            target_date: The date to find the week start for

        Returns:
            Date of Monday for that week
        """
        # weekday() returns 0 for Monday, 6 for Sunday
        days_since_monday = target_date.weekday()
        return target_date - timedelta(days=days_since_monday)

    def _update_week_label(self):
        """Update the week range label"""
        # Format: "Semana 4-10 Nov 2025"
        start_str = self.current_start_date.strftime("%d")
        end_day = self.current_end_date.day
        month_year = self.current_end_date.strftime("%b %Y")

        # Get Spanish month name
        month_names = {
            'Jan': 'Ene', 'Feb': 'Feb', 'Mar': 'Mar', 'Apr': 'Abr',
            'May': 'May', 'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Ago',
            'Sep': 'Sep', 'Oct': 'Oct', 'Nov': 'Nov', 'Dec': 'Dic'
        }
        for en, es in month_names.items():
            month_year = month_year.replace(en, es)

        self.label_week.setText(f"Semana {start_str}-{end_day} {month_year}")

    def _go_to_previous_week(self):
        """Navigate to the previous week"""
        self.current_start_date -= timedelta(days=7)
        self.current_end_date -= timedelta(days=7)
        self._update_week_label()
        self.week_changed.emit(self.current_start_date, self.current_end_date)

    def _go_to_next_week(self):
        """Navigate to the next week"""
        self.current_start_date += timedelta(days=7)
        self.current_end_date += timedelta(days=7)
        self._update_week_label()
        self.week_changed.emit(self.current_start_date, self.current_end_date)

    def _go_to_current_week(self):
        """Jump to the week containing today"""
        today = date.today()
        new_start = self._get_week_start(today)
        new_end = new_start + timedelta(days=6)

        # Only emit if actually changing weeks
        if new_start != self.current_start_date:
            self.current_start_date = new_start
            self.current_end_date = new_end
            self._update_week_label()
            self.week_changed.emit(self.current_start_date, self.current_end_date)

    def get_current_week(self) -> tuple[date, date]:
        """
        Get the currently selected week range.

        Returns:
            Tuple of (start_date, end_date)
        """
        return (self.current_start_date, self.current_end_date)

    def set_week(self, target_date: date):
        """
        Set the week to display based on a target date.

        Args:
            target_date: Any date within the desired week
        """
        new_start = self._get_week_start(target_date)
        new_end = new_start + timedelta(days=6)

        if new_start != self.current_start_date:
            self.current_start_date = new_start
            self.current_end_date = new_end
            self._update_week_label()
            self.week_changed.emit(self.current_start_date, self.current_end_date)


# Example usage and testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QTextEdit
    import sys

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("WeekSelector Test")
    layout = QVBoxLayout(window)

    # Add week selector
    week_selector = WeekSelector()
    layout.addWidget(week_selector)

    # Add log area
    log = QTextEdit()
    log.setReadOnly(True)
    layout.addWidget(log)

    def on_week_changed(start, end):
        log.append(f"Week changed: {start} to {end}")

    week_selector.week_changed.connect(on_week_changed)

    window.resize(500, 300)
    window.show()

    sys.exit(app.exec())
