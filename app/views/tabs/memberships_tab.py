"""
Vista de la pestaña de Membresías - Gestión de paquetes.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QLabel, QDialog,
    QHeaderView, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from ...core import get_logger
from ...utils.dialog_helpers import show_confirmation
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)

class MembershipsTab(QWidget):
    """Vista para gestión de paquetes/membresías."""
    
    # Señales
    create_membership_requested = Signal(dict)
    update_membership_requested = Signal(int, dict)
    delete_membership_requested = Signal(int)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.load_memberships()
    
    def setup_ui(self):
        """Configura la interfaz de usuario."""
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Catálogo de Membresías")
        title_font = QFont("Arial", 14, QFont.Weight.Bold)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Botones de acción
        self.new_btn = QPushButton("+ Nueva Membresía")
        self.new_btn.setObjectName("primaryButton")
        self.new_btn.clicked.connect(self.on_new_clicked)
        header_layout.addWidget(self.new_btn)

        self.edit_btn = QPushButton("Editar")
        self.edit_btn.setObjectName("actionButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.on_edit_clicked)
        header_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Eliminar")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        header_layout.addWidget(self.delete_btn)
        
        layout.addLayout(header_layout)
        
        # Tabla de membresías
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nombre", "Precio", "Duración", "Tipo", "Descripción"
        ])
        
        # Configurar tabla
        configure_table_widget(self.table)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        
        # Conectar señales
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellDoubleClicked.connect(self.on_edit_clicked)
        
        layout.addWidget(self.table)
        
        # Resumen
        summary_layout = QHBoxLayout()
        self.summary_label = QLabel("0 membresías registradas")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()
        layout.addLayout(summary_layout)
    
    def load_memberships(self):
        """Carga las membresias/paquetes disponibles."""
        # Datos mock basados en la BD
        memberships = [
            (1, "Clase Suelta", 70.00, 1, "día", "Una clase individual"),
            (2, "Mensual 8 Clases", 400.00, 30, "días", "8 clases en 30 días"),
            (3, "Mensual 12 Clases", 550.00, 30, "días", "12 clases en 30 días"),
            (4, "Mensual Libre", 700.00, 30, "días", "Clases ilimitadas por 30 días"),
            (5, "Trimestral", 1800.00, 90, "días", "Clases ilimitadas por 3 meses"),
            (6, "Semestral", 3300.00, 180, "días", "Clases ilimitadas por 6 meses"),
            (7, "Anual", 6000.00, 365, "días", "Clases ilimitadas por 1 año"),
        ]
        
        self.table.setRowCount(len(memberships))
        
        for row, membership in enumerate(memberships):
            for col, value in enumerate(membership):
                if col == 2:  # Precio
                    item = QTableWidgetItem(f"${value:,.2f}")
                elif col == 3:  # Duración
                    item = QTableWidgetItem(f"{value} {membership[4]}")
                elif col == 4:  # Tipo (no mostrar, ya se incluye en duración)
                    continue
                else:
                    item = QTableWidgetItem(str(value))
                
                self.table.setItem(row, col, item)
        
        self.table.resizeColumnsToContents()
        self.update_summary()
    
    def on_selection_changed(self):
        """Maneja el cambio de selección."""
        has_selection = len(self.table.selectedItems()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
    
    def on_new_clicked(self):
        """Abre el diálogo para crear nueva membresía."""
        dialog = MembersDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.create_membership_requested.emit(data)
            
            # Agregar a la tabla localmente
            self.add_membership_to_table(data)
    
    def on_edit_clicked(self):
        """Abre el diálogo para editar membresía."""
        row = self.table.currentRow()
        if row < 0:
            return
        
        # Obtener datos actuales
        id_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        price_item = self.table.item(row, 2)
        duration_item = self.table.item(row, 3)
        description_item = self.table.item(row, 5)

        if not all([id_item, name_item, price_item, duration_item]):
            return

        # En este punto sabemos que todos los elementos existen
        assert id_item is not None
        assert name_item is not None
        assert price_item is not None
        assert duration_item is not None

        current_data = {
            'id': int(id_item.text()),
            'name': name_item.text(),
            'price': float(price_item.text().replace('$', '').replace(',', '')),
            'duration': duration_item.text(),
            'description': description_item.text() if description_item else ""
        }
        
        dialog = MembersDialog(self, current_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.update_membership_requested.emit(current_data['id'], data)
            
            # Actualizar tabla localmente
            self.update_membership_in_table(row, data)
    
    def on_delete_clicked(self):
        """Maneja la eliminación de una membresía."""
        row = self.table.currentRow()
        if row < 0:
            return
        
        id_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)

        if not id_item or not name_item:
            return

        memberships_id = int(id_item.text())
        memberships_name = name_item.text()
        
        # Confirmar eliminación
        if show_confirmation(
            self,
            f"¿Está seguro de eliminar la membresía '{memberships_name}'?",
            title="Confirmar Eliminación",
            ok_text="Sí",
            cancel_text="No",
        ):
            self.delete_membership_requested.emit(memberships_id)
            self.table.removeRow(row)
            self.update_summary()
    
    def add_membership_to_table(self, data: dict):
        """Agrega una membresia a la tabla."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # ID temporal
        self.table.setItem(row, 0, QTableWidgetItem(str(row + 100)))
        self.table.setItem(row, 1, QTableWidgetItem(data['name']))
        self.table.setItem(row, 2, QTableWidgetItem(f"${data['price']:,.2f}"))
        self.table.setItem(row, 3, QTableWidgetItem(f"{data['duration']} {data['duration_type']}"))
        self.table.setItem(row, 4, QTableWidgetItem(data['duration_type']))
        self.table.setItem(row, 5, QTableWidgetItem(data.get('description', '')))
        
        self.update_summary()
    
    def update_membership_in_table(self, row: int, data: dict):
        """Actualiza una membresia en la tabla."""
        name_item = self.table.item(row, 1)
        price_item = self.table.item(row, 2)
        duration_item = self.table.item(row, 3)
        description_item = self.table.item(row, 5)

        if name_item:
            name_item.setText(data['name'])
        if price_item:
            price_item.setText(f"${data['price']:,.2f}")
        if duration_item:
            duration_item.setText(f"{data['duration']} {data['duration_type']}")
        if description_item:
            description_item.setText(data.get('description', ''))
    
    def update_summary(self):
        """Actualiza el resumen."""
        count = self.table.rowCount()
        self.summary_label.setText(f"{count} membresías registradas")


class MembersDialog(QDialog):
    """Diálogo para crear/editar membresías."""
    
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data
        self.setup_ui()
        
        if data:
            self.load_data(data)
    
    def setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Nueva Membresía" if not self.data else "Editar Membresía")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Formulario
        form_layout = QFormLayout()
        
        # Nombre
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: Mensual Libre")
        form_layout.addRow("Nombre:", self.name_input)
        
        # Precio
        self.price_input = QSpinBox()
        self.price_input.setMinimum(0)
        self.price_input.setMaximum(99999)
        self.price_input.setPrefix("$ ")
        self.price_input.setSuffix(" MXN")
        form_layout.addRow("Precio:", self.price_input)
        
        # Duración
        duration_layout = QHBoxLayout()
        
        self.duration_input = QSpinBox()
        self.duration_input.setMinimum(1)
        self.duration_input.setMaximum(999)
        duration_layout.addWidget(self.duration_input)
        
        self.duration_type = QComboBox()
        self.duration_type.addItems(["días", "semanas", "meses", "clases"])
        duration_layout.addWidget(self.duration_type)
        
        form_layout.addRow("Duración:", duration_layout)
        
        # Descripción
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        self.description_input.setPlaceholderText("Descripción opcional...")
        form_layout.addRow("Descripción:", self.description_input)
        
        layout.addLayout(form_layout)
        
        # Botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_data(self, data: dict):
        """Carga los datos en el formulario."""
        self.name_input.setText(data.get('name', ''))
        self.price_input.setValue(int(data.get('price', 0)))
        
        # Parsear duración
        duration_str = data.get('duration', '30 días')
        parts = duration_str.split()
        if len(parts) >= 2:
            self.duration_input.setValue(int(parts[0]))
            self.duration_type.setCurrentText(parts[1])
        
        self.description_input.setPlainText(data.get('description', ''))
    
    def get_data(self) -> dict:
        """Obtiene los datos del formulario."""
        return {
            'name': self.name_input.text(),
            'price': self.price_input.value(),
            'duration': self.duration_input.value(),
            'duration_type': self.duration_type.currentText(),
            'description': self.description_input.toPlainText()
        }
