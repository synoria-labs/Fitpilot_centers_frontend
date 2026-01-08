"""
Vista de la pestaña WhatsApp - Gestión de plantillas.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QLabel, QTextEdit,
    QLineEdit, QGroupBox, QSplitter, QListWidget,
    QAbstractItemView, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from ...core import get_logger
from ...utils.dialog_helpers import show_confirmation

logger = get_logger(__name__)

class WhatsAppTab(QWidget):
    """Vista para gestión de plantillas de WhatsApp."""
    
    # Señales
    template_selected = Signal(int)
    create_template_requested = Signal(dict)
    update_template_requested = Signal(int, dict)
    delete_template_requested = Signal(int)
    send_message_requested = Signal(str, str)  # phone, message
    
    def __init__(self):
        super().__init__()
        self.current_template = None
        self.setup_ui()
        self.load_templates()
    
    def setup_ui(self):
        """Configura la interfaz de usuario."""
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Gestión de Plantillas WhatsApp")
        title_font = QFont("Arial", 14, QFont.Weight.Bold)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Botones de acción
        self.new_btn = QPushButton("+ Nueva Plantilla")
        self.new_btn.clicked.connect(self.on_new_template)
        header_layout.addWidget(self.new_btn)
        
        self.save_btn = QPushButton("💾 Guardar")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_template)
        header_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("🗑️ Eliminar")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.on_delete_template)
        header_layout.addWidget(self.delete_btn)
        
        layout.addLayout(header_layout)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Panel izquierdo - Lista de plantillas
        left_panel = QGroupBox("Plantillas")
        left_layout = QVBoxLayout(left_panel)
        
        self.templates_list = QListWidget()
        self.templates_list.itemClicked.connect(self.on_template_selected)
        left_layout.addWidget(self.templates_list)
        
        splitter.addWidget(left_panel)
        
        # Panel derecho - Editor de plantilla
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Información de plantilla
        info_group = QGroupBox("Información de Plantilla")
        info_layout = QVBoxLayout(info_group)
        
        # Nombre
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nombre:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: Bienvenida_Nuevo_Socio")
        self.name_input.textChanged.connect(self.on_template_changed)
        name_layout.addWidget(self.name_input)
        info_layout.addLayout(name_layout)
        
        # Estado
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Estado:"))
        self.status_label = QLabel("No guardado")
        self.status_label.setStyleSheet("color: orange;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        info_layout.addLayout(status_layout)
        
        right_layout.addWidget(info_group)
        
        # Editor de contenido
        content_group = QGroupBox("Contenido de la Plantilla")
        content_layout = QVBoxLayout(content_group)
        
        # Variables disponibles
        vars_label = QLabel("Variables disponibles: {{nombre}}, {{telefono}}, {{membresia}}, {{fecha}}")
        vars_label.setStyleSheet("color: #3498db; font-size: 11px;")
        content_layout.addWidget(vars_label)
        
        # Editor de texto
        self.content_editor = QTextEdit()
        self.content_editor.setPlaceholderText(
            "Hola {{nombre}}! 👋\n\n"
            "Bienvenido a FitPilot. Tu membresía {{membresia}} está activa.\n\n"
            "¡Nos vemos en el gym! 💪"
        )
        self.content_editor.textChanged.connect(self.on_template_changed)
        content_layout.addWidget(self.content_editor)
        
        # Vista previa
        preview_label = QLabel("Vista Previa:")
        preview_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(preview_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(100)
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
        content_layout.addWidget(self.preview_text)
        
        right_layout.addWidget(content_group)
        
        # Sección de prueba
        test_group = QGroupBox("Enviar Prueba")
        test_layout = QHBoxLayout(test_group)
        
        test_layout.addWidget(QLabel("Teléfono:"))
        self.test_phone = QLineEdit()
        self.test_phone.setPlaceholderText("+52 XXX XXX XXXX")
        test_layout.addWidget(self.test_phone)
        
        self.send_test_btn = QPushButton("📤 Enviar Prueba")
        self.send_test_btn.clicked.connect(self.on_send_test)
        test_layout.addWidget(self.send_test_btn)
        
        right_layout.addWidget(test_group)
        
        splitter.addWidget(right_panel)
        
        # Configurar proporciones del splitter
        splitter.setSizes([300, 700])
        
        layout.addWidget(splitter)
    
    def load_templates(self):
        """Carga las plantillas disponibles."""
        # Plantillas mock
        templates = [
            "Bienvenida_Nuevo_Socio",
            "Recordatorio_Pago",
            "Confirmacion_Reserva",
            "Cancelacion_Reserva",
            "Promocion_Mensual",
            "Membresia_Por_Vencer",
            "Felicitacion_Cumpleanos"
        ]
        
        self.templates_list.clear()
        for template in templates:
            self.templates_list.addItem(template)
        
        logger.info(f"Loaded {len(templates)} templates")
    
    def on_template_selected(self, item):
        """Maneja la selección de una plantilla."""
        template_name = item.text()
        
        # Cargar contenido mock
        self.name_input.setText(template_name)
        
        # Contenido de ejemplo según plantilla
        contents = {
            "Bienvenida_Nuevo_Socio": (
                "¡Hola {{nombre}}! 🎉\n\n"
                "¡Bienvenido a FitPilot! 💪\n\n"
                "Tu membresía {{membresia}} está activa desde hoy.\n"
                "Recuerda que puedes reservar tus clases desde nuestra app.\n\n"
                "¿Necesitas ayuda? Escríbenos por aquí.\n\n"
                "¡Nos vemos en el gym! 🏋️‍♀️"
            ),
            "Recordatorio_Pago": (
                "Hola {{nombre}} 👋\n\n"
                "Te recordamos que tu membresía vence el {{fecha}}.\n"
                "Para continuar disfrutando de nuestros servicios, "
                "puedes renovar en recepción o por este medio.\n\n"
                "¡Gracias por ser parte de FitPilot! 💙"
            ),
            "Confirmacion_Reserva": (
                "✅ Reserva Confirmada\n\n"
                "Hola {{nombre}}, tu reserva está lista:\n"
                "📅 Fecha: {{fecha}}\n"
                "⏰ Hora: {{hora}}\n"
                "🚴 Bicicleta: {{bicicleta}}\n\n"
                "¡Te esperamos!"
            )
        }
        
        content = contents.get(
            template_name,
            f"Plantilla: {template_name}\n\nContenido de ejemplo..."
        )
        
        self.content_editor.setPlainText(content)
        self.status_label.setText("Guardado")
        self.status_label.setStyleSheet("color: green;")
        
        # Habilitar botones
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        
        # Actualizar preview
        self.update_preview()
        
        # Guardar referencia
        self.current_template = template_name
        
        # Emitir señal
        self.template_selected.emit(self.templates_list.currentRow())
    
    def on_template_changed(self):
        """Maneja cambios en la plantilla."""
        if self.current_template:
            self.status_label.setText("Sin guardar")
            self.status_label.setStyleSheet("color: orange;")
            self.save_btn.setEnabled(True)
        
        self.update_preview()
    
    def update_preview(self):
        """Actualiza la vista previa con valores de ejemplo."""
        content = self.content_editor.toPlainText()
        
        # Reemplazar variables con valores de ejemplo
        preview = content.replace("{{nombre}}", "Juan Pérez")
        preview = preview.replace("{{telefono}}", "+52 123 456 7890")
        preview = preview.replace("{{membresia}}", "Mensual Libre")
        preview = preview.replace("{{fecha}}", "15/01/2025")
        preview = preview.replace("{{hora}}", "07:00 AM")
        preview = preview.replace("{{bicicleta}}", "#5")
        
        self.preview_text.setPlainText(preview)
    
    def on_new_template(self):
        """Crea una nueva plantilla."""
        self.templates_list.clearSelection()
        self.name_input.clear()
        self.content_editor.clear()
        self.preview_text.clear()
        self.status_label.setText("Nueva plantilla")
        self.status_label.setStyleSheet("color: blue;")
        
        self.name_input.setFocus()
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        
        self.current_template = None
    
    def on_save_template(self):
        """Guarda la plantilla actual."""
        name = self.name_input.text().strip()
        content = self.content_editor.toPlainText().strip()
        
        if not name:
            logger.warning("Template name is required")
            return
        
        if not content:
            logger.warning("Template content is required")
            return
        
        template_data = {
            'name': name,
            'content': content,
            'status': 'active'
        }
        
        if self.current_template:
            # Actualizar
            self.update_template_requested.emit(
                self.templates_list.currentRow(),
                template_data
            )
            logger.info(f"Template updated: {name}")
        else:
            # Crear nueva
            self.create_template_requested.emit(template_data)
            self.templates_list.addItem(name)
            logger.info(f"Template created: {name}")
        
        self.status_label.setText("Guardado")
        self.status_label.setStyleSheet("color: green;")
        self.current_template = name
    
    def on_delete_template(self):
        """Elimina la plantilla actual."""
        if not self.current_template:
            return
        
        if show_confirmation(
            self,
            f"¿Está seguro de eliminar la plantilla '{self.current_template}'?",
            title="Confirmar Eliminación",
            ok_text="Sí",
            cancel_text="No",
        ):
            row = self.templates_list.currentRow()
            self.delete_template_requested.emit(row)
            self.templates_list.takeItem(row)
            
            # Limpiar editor
            self.name_input.clear()
            self.content_editor.clear()
            self.preview_text.clear()
            self.save_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            
            logger.info(f"Template deleted: {self.current_template}")
            self.current_template = None
    
    def on_send_test(self):
        """Envía una prueba de la plantilla."""
        phone = self.test_phone.text().strip()
        if not phone:
            logger.warning("Phone number is required for test")
            return
        
        message = self.preview_text.toPlainText()
        if not message:
            logger.warning("No message to send")
            return
        
        self.send_message_requested.emit(phone, message)
        logger.info(f"Test message sent to {phone}")
