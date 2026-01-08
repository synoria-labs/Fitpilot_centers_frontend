"""
TimeSlotSelector - Widget for selecting a specific time slot when multiple exist
"""
from typing import Optional, List, Dict
from datetime import datetime
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel
from PySide6.QtCore import Signal


class TimeSlotSelector(QWidget):
    """
    Widget for selecting a specific time slot when multiple sessions exist in a day.

    Features:
    - Dropdown with available time slots
    - Shows time range and instructor
    - Only visible when multiple slots exist
    - Emits signal when selection changes
    """

    # Signal emitted when the selected time slot changes
    # Parameters: (session_id: int)
    time_slot_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize TimeSlotSelector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.sessions: List[Dict] = []
        self._setup_ui()

        # Initially hidden until slots are populated
        self.setVisible(False)

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Label
        label = QLabel("Horario:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        # ComboBox
        self.combo_time_slot = QComboBox()
        self.combo_time_slot.setMinimumWidth(200)
        self.combo_time_slot.currentIndexChanged.connect(self._on_selection_changed)

        layout.addWidget(self.combo_time_slot)
        layout.addStretch()

    def populate_time_slots(self, sessions: List[Dict]):
        """
        Populate the dropdown with available time slots.

        Args:
            sessions: List of session dictionaries with keys: id, start_at, end_at, instructor_name
                Example: [
                    {
                        'id': 123,
                        'start_at': datetime(...),
                        'end_at': datetime(...),
                        'instructor_name': 'Laura Torres'
                    },
                    ...
                ]
        """
        self.sessions = sessions
        self.combo_time_slot.blockSignals(True)
        self.combo_time_slot.clear()

        if not sessions:
            self.setVisible(False)
            self.combo_time_slot.blockSignals(False)
            return

        # Only show if there are multiple sessions
        if len(sessions) <= 1:
            self.setVisible(False)
            self.combo_time_slot.blockSignals(False)
            return

        self.setVisible(True)

        for session in sessions:
            # Format display text
            start_time = session['start_at'].strftime("%H:%M")
            end_time = session['end_at'].strftime("%H:%M")

            display_text = f"{start_time} - {end_time}"

            # Add instructor if available
            if session.get('instructor_name'):
                display_text += f" | {session['instructor_name']}"

            # Add to combobox
            self.combo_time_slot.addItem(display_text, session['id'])

        # Select first by default
        if sessions:
            self.combo_time_slot.setCurrentIndex(0)
        self.combo_time_slot.blockSignals(False)

    def _on_selection_changed(self, index: int):
        """Handle selection change"""
        if index >= 0:
            session_id = self.combo_time_slot.itemData(index)
            if session_id is not None:
                self.time_slot_changed.emit(session_id)

    def get_selected_session_id(self) -> Optional[int]:
        """
        Get the ID of the currently selected session.

        Returns:
            Session ID or None if nothing selected
        """
        index = self.combo_time_slot.currentIndex()
        if index >= 0:
            return self.combo_time_slot.itemData(index)
        return None

    def set_selected_session(self, session_id: int):
        """
        Set the selected session by ID.

        Args:
            session_id: ID of the session to select
        """
        self.combo_time_slot.blockSignals(True)
        for i in range(self.combo_time_slot.count()):
            if self.combo_time_slot.itemData(i) == session_id:
                self.combo_time_slot.setCurrentIndex(i)
                break
        self.combo_time_slot.blockSignals(False)

    def clear(self):
        """Clear all time slots and hide the widget"""
        self.sessions = []
        self.combo_time_slot.clear()
        self.setVisible(False)


# Example usage and testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QTextEdit, QPushButton
    import sys

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("TimeSlotSelector Test")
    layout = QVBoxLayout(window)

    # Add time slot selector
    selector = TimeSlotSelector()
    layout.addWidget(selector)

    # Sample data
    sample_sessions = [
        {
            'id': 1,
            'start_at': datetime(2025, 11, 6, 14, 0),
            'end_at': datetime(2025, 11, 6, 15, 0),
            'instructor_name': 'Laura Torres'
        },
        {
            'id': 2,
            'start_at': datetime(2025, 11, 6, 16, 0),
            'end_at': datetime(2025, 11, 6, 17, 0),
            'instructor_name': 'Carlos Méndez'
        },
        {
            'id': 3,
            'start_at': datetime(2025, 11, 6, 18, 0),
            'end_at': datetime(2025, 11, 6, 19, 0),
            'instructor_name': None
        },
    ]

    # Buttons to test
    btn_populate = QPushButton("Populate with 3 sessions")
    btn_populate.clicked.connect(lambda: selector.populate_time_slots(sample_sessions))
    layout.addWidget(btn_populate)

    btn_single = QPushButton("Populate with 1 session (should hide)")
    btn_single.clicked.connect(lambda: selector.populate_time_slots([sample_sessions[0]]))
    layout.addWidget(btn_single)

    btn_clear = QPushButton("Clear")
    btn_clear.clicked.connect(selector.clear)
    layout.addWidget(btn_clear)

    # Add log area
    log = QTextEdit()
    log.setReadOnly(True)
    layout.addWidget(log)

    def on_time_slot_changed(session_id):
        log.append(f"Time slot changed to session ID: {session_id}")

    selector.time_slot_changed.connect(on_time_slot_changed)

    window.resize(500, 400)
    window.show()

    sys.exit(app.exec())
