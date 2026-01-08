"""
ClassTypeFilter - Widget for filtering classes by type
"""
from typing import Optional, List, Dict
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel
from PySide6.QtCore import Signal


class ClassTypeFilter(QWidget):
    """
    Widget for selecting a class type from available options.

    Features:
    - Dropdown with all available class types
    - Can be populated dynamically from service
    - Emits signal when selection changes
    - Default selection support
    """

    # Signal emitted when the selected class type changes
    # Parameters: (class_type_id: int, class_type_code: str, class_type_name: str)
    class_type_changed = Signal(int, str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize ClassTypeFilter.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.class_types: List[Dict] = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Label
        label = QLabel("Tipo de Clase:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        # ComboBox
        self.combo_class_type = QComboBox()
        self.combo_class_type.setMinimumWidth(150)
        self.combo_class_type.currentIndexChanged.connect(self._on_selection_changed)

        layout.addWidget(self.combo_class_type)
        layout.addStretch()

    def populate_class_types(self, class_types: List[Dict], default_code: str = 'spinning'):
        """
        Populate the dropdown with available class types.

        Args:
            class_types: List of class type dictionaries with keys: id, code, name
                Example: [{'id': 1, 'code': 'spinning', 'name': 'Spinning'}, ...]
            default_code: Code of the class type to select by default
        """
        self.class_types = class_types
        self.combo_class_type.clear()

        default_index = 0

        for i, class_type in enumerate(class_types):
            # Add to combobox: display name, store full dict as user data
            self.combo_class_type.addItem(class_type['name'], class_type)

            # Track default index
            if class_type['code'] == default_code:
                default_index = i

        # Set default selection
        if class_types:
            self.combo_class_type.setCurrentIndex(default_index)

    def _on_selection_changed(self, index: int):
        """Handle selection change"""
        if index >= 0:
            class_type = self.combo_class_type.itemData(index)
            if class_type:
                self.class_type_changed.emit(
                    class_type['id'],
                    class_type['code'],
                    class_type['name']
                )

    def get_selected_class_type(self) -> Optional[Dict]:
        """
        Get the currently selected class type.

        Returns:
            Dictionary with class type info or None if nothing selected
        """
        index = self.combo_class_type.currentIndex()
        if index >= 0:
            return self.combo_class_type.itemData(index)
        return None

    def set_selected_class_type(self, code: str):
        """
        Set the selected class type by code.

        Args:
            code: Class type code (e.g., 'spinning', 'yoga')
        """
        for i in range(self.combo_class_type.count()):
            class_type = self.combo_class_type.itemData(i)
            if class_type and class_type['code'] == code:
                self.combo_class_type.setCurrentIndex(i)
                break

    def set_enabled(self, enabled: bool):
        """
        Enable or disable the filter.

        Args:
            enabled: True to enable, False to disable
        """
        self.combo_class_type.setEnabled(enabled)


# Example usage and testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QTextEdit
    import sys

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("ClassTypeFilter Test")
    layout = QVBoxLayout(window)

    # Add class type filter
    filter_widget = ClassTypeFilter()
    layout.addWidget(filter_widget)

    # Sample data
    sample_types = [
        {'id': 1, 'code': 'spinning', 'name': 'Spinning'},
        {'id': 2, 'code': 'yoga', 'name': 'Yoga'},
        {'id': 3, 'code': 'pilates', 'name': 'Pilates'},
        {'id': 4, 'code': 'zumba', 'name': 'Zumba'},
    ]
    filter_widget.populate_class_types(sample_types, default_code='spinning')

    # Add log area
    log = QTextEdit()
    log.setReadOnly(True)
    layout.addWidget(log)

    def on_class_type_changed(class_type_id, code, name):
        log.append(f"Class type changed: ID={class_type_id}, Code={code}, Name={name}")

    filter_widget.class_type_changed.connect(on_class_type_changed)

    window.resize(500, 300)
    window.show()

    sys.exit(app.exec())
