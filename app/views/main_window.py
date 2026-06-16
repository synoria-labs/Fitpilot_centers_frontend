"""
Ventana principal de FitPilot con pestañas modulares.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QToolBar, QStatusBar,
    QMenu, QMenuBar
)
from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtGui import QAction, QIcon, QFont
from ..core import get_logger
from ..utils.dialog_helpers import (
    show_confirmation,
    show_error as show_error_dialog,
    show_info as show_info_dialog,
)

logger = get_logger(__name__)


class ClickableLabel(QLabel):
    """QLabel personalizado que emite una señal al hacer click."""
    clicked = Signal()

    def mousePressEvent(self, event):
        """Emite la señal clicked al hacer click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""
    
    # Señales
    logout_requested = Signal()
    tab_changed = Signal(int)
    refresh_requested = Signal(str)  # nombre de la pestaña
    
    def __init__(self):
        super().__init__()
        self.current_user = None
        self.tabs = {}
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        self.setup_statusbar()
        self.setup_styles()
    
    def setup_ui(self):
        """Configura la interfaz principal."""
        self.setWindowTitle("FitPilot - Sistema de Gestión")
        self.setGeometry(100, 100, 1280, 800)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header con información del usuario
        header_widget = QWidget()
        header_widget.setObjectName("headerWidget")
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        
        # Logo/Título
        logo_label = QLabel("FitPilot")
        logo_font = QFont("Arial", 16)
        logo_font.setWeight(QFont.Weight.Bold)
        logo_label.setFont(logo_font)
        header_layout.addWidget(logo_label)
        
        header_layout.addStretch()

        # Información de sesión (dispositivo)
        self.session_label = ClickableLabel("")
        self.session_label.setObjectName("sessionLabel")
        self.session_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.session_label.clicked.connect(self.show_sessions_dialog)
        self.session_label.setToolTip("Click para ver todas las sesiones activas")
        header_layout.addWidget(self.session_label)

        # Información del usuario
        self.user_label = QLabel("Usuario: ")
        self.user_label.setObjectName("userLabel")
        header_layout.addWidget(self.user_label)

        # Botón de logout
        self.logout_button = QPushButton("Cerrar Sesión")
        self.logout_button.setObjectName("logoutButton")
        self.logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_button.clicked.connect(self.on_logout_clicked)
        header_layout.addWidget(self.logout_button)
        
        main_layout.addWidget(header_widget)
        
        # TabWidget para las pestañas
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("mainTabWidget")
        # Asegurar que el tab widget se expanda completamente
        main_layout.addWidget(self.tab_widget, 1)  # El 1 le da factor de estiramiento
        
        # Conectar señal después de agregar al layout
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # Inicializar pestañas (se cargarán dinámicamente)
        self.init_tabs()
    
    def init_tabs(self):
        """Inicializa las pestañas de la aplicación."""
        # Las pestañas se crearán con skeleton loaders
        tab_configs = [
            ("Socios", "members", True),
            ("Clases", "classes", True),
            ("Chats", "whatsapp_chat", False),  # Solo admin
            ("WhatsApp", "whatsapp", False),  # Solo admin (plantillas)
            ("Notificaciones", "whatsapp_notifications", False),  # Solo admin (config de envíos)
            ("Chatbot", "chatbot_config", False),  # Solo admin (config del agente de WhatsApp)
            ("Campañas", "campaigns", False),  # Solo admin (difusión de marketing por WhatsApp)
            ("Membresías", "memberships", True),
            ("Dashboard", "dashboard", True),
            ("Finanzas", "finances", False),  # Solo admin
        ]
        
        for tab_name, tab_id, is_public in tab_configs:
            # Crear widget placeholder con loading
            placeholder = self.create_loading_widget(tab_name)
            self.tab_widget.addTab(placeholder, tab_name)
            self.tabs[tab_id] = {
                'name': tab_name,
                'widget': placeholder,
                'loaded': False,
                'is_public': is_public
            }
    
    def create_loading_widget(self, tab_name: str) -> QWidget:
        """Crea un widget de carga para una pestaña."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Mensaje de carga
        loading_label = QLabel(f"Cargando {tab_name}...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_label.setObjectName("loadingLabel")
        loading_font = QFont("Arial", 14)
        loading_label.setFont(loading_font)
        
        layout.addStretch()
        layout.addWidget(loading_label)
        layout.addStretch()
        
        return widget
    
    def setup_menu(self):
        """Configura el menú principal."""
        menubar = self.menuBar()
        
        # Menú Archivo
        file_menu = menubar.addMenu("&Archivo")

        refresh_action = QAction("&Actualizar", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.on_refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        # Sesiones activas
        sessions_action = QAction("&Sesiones Activas", self)
        sessions_action.triggered.connect(self.show_sessions_dialog)
        file_menu.addAction(sessions_action)

        logout_action = QAction("&Cerrar Sesión", self)
        logout_action.setShortcut("Ctrl+Q")
        logout_action.triggered.connect(self.on_logout_clicked)
        file_menu.addAction(logout_action)
        
        # Menú Ver
        view_menu = menubar.addMenu("&Ver")
        
        fullscreen_action = QAction("&Pantalla Completa", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        # Menú Ayuda
        help_menu = menubar.addMenu("&Ayuda")
        
        about_action = QAction("&Acerca de", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_toolbar(self):
        """Configura la barra de herramientas."""
        toolbar = QToolBar("Herramientas Principales")
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(toolbar)
        
        # Acciones rápidas
        refresh_action = QAction("Actualizar", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.on_refresh)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        # Acciones específicas por pestaña (se actualizarán dinámicamente)
        self.toolbar_actions = {}
    
    def setup_statusbar(self):
        """Configura la barra de estado."""
        self.status_bar = self.statusBar()
        self.status_bar.setObjectName("mainStatusBar")
        
        # Mensaje de estado
        self.status_message = QLabel("Listo")
        self.status_bar.addWidget(self.status_message)
        
        # Indicador de conexión
        self.connection_status = QLabel("● Conectado")
        self.connection_status.setObjectName("connectionStatus")
        self.status_bar.addPermanentWidget(self.connection_status)
        
        # Timer para verificar conexión
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection)
        self.connection_timer.start(30000)  # Cada 30 segundos
    
    def setup_styles(self):
        """Aplica estilos mínimos manteniendo el tema nativo del sistema."""
        # Solo aplicamos estilos esenciales sin sobrescribir el tema del sistema
        style = """
        #headerWidget {
            padding: 10px;
            border-bottom: 1px solid palette(mid);
        }

        #userLabel {
            padding: 0 10px;
        }

        #logoutButton {
            background-color: red;
            padding: 8px 16px;
            font-weight: bold;
        }

        #connectionStatus {
            padding: 0 10px;
        }

        #connectionStatus[connected="true"] {
            color: #2ecc71;
        }

        #connectionStatus[connected="false"] {
            color: #e74c3c;
        }
        """
        self.setStyleSheet(style)
    
    def set_current_user(self, user_data: dict):
        """Establece el usuario actual."""
        self.current_user = user_data
        username = user_data.get('username', 'Usuario')
        role = user_data.get('role', 'usuario')
        self.user_label.setText(f"Usuario: {username} ({role})")

        # Mostrar información de sesión (se cargará de forma asíncrona)
        self._load_current_session_info()

        # Ocultar pestañas según permisos
        self.update_tabs_visibility(role)
    
    def update_tabs_visibility(self, role: str):
        """Actualiza la visibilidad de las pestañas según el rol."""
        # WhatsApp y Chats solo para admin
        if role != 'admin':
            admin_only_tabs = {"WhatsApp", "Chats", "Finanzas", "Chatbot", "Campañas"}
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) in admin_only_tabs:
                    self.tab_widget.setTabEnabled(i, False)
    
    def load_tab_content(self, tab_id: str, widget: QWidget):
        """Carga el contenido real de una pestaña."""
        if tab_id in self.tabs:
            tab_info = self.tabs[tab_id]
            index = self.get_tab_index(tab_info['name'])
            
            if index >= 0:
                # Guardar el índice actual
                current_index = self.tab_widget.currentIndex()
                
                # Bloquear señales temporalmente para evitar eventos no deseados
                self.tab_widget.blockSignals(True)
                
                # Reemplazar el widget
                self.tab_widget.removeTab(index)
                self.tab_widget.insertTab(index, widget, tab_info['name'])
                
                # Restaurar el índice actual si era diferente
                if current_index == index:
                    self.tab_widget.setCurrentIndex(index)
                elif current_index > index:
                    # Si el índice actual era mayor, no cambia
                    self.tab_widget.setCurrentIndex(current_index)
                
                # Desbloquear señales
                self.tab_widget.blockSignals(False)
                
                tab_info['widget'] = widget
                tab_info['loaded'] = True
                
                logger.info(f"Tab loaded: {tab_info['name']}")
    
    def get_tab_index(self, tab_name: str) -> int:
        """Obtiene el índice de una pestaña por nombre."""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_name:
                return i
        return -1
    
    @Slot(int)
    def on_tab_changed(self, index: int):
        """Maneja el cambio de pestaña."""
        if index >= 0:
            tab_name = self.tab_widget.tabText(index)
            logger.info(f"Tab changed to: {tab_name} (index: {index})")
            
            if getattr(self, "status_message", None):
                self.status_message.setText(f"Vista: {tab_name}")
            
            # Cargar pestaña si es necesario
            for tab_id, tab_info in self.tabs.items():
                if tab_info['name'] == tab_name:
                    if not tab_info['loaded']:
                        logger.info(f"Tab '{tab_name}' not loaded, requesting load...")
                        self.refresh_requested.emit(tab_id)
                    break
            
            # Emitir señal después de procesar
            self.tab_changed.emit(index)
    
    @Slot()
    def on_refresh(self):
        """Actualiza la pestaña actual."""
        current_index = self.tab_widget.currentIndex()
        if current_index >= 0:
            tab_name = self.tab_widget.tabText(current_index)
            for tab_id, tab_info in self.tabs.items():
                if tab_info['name'] == tab_name:
                    self.refresh_requested.emit(tab_id)
                    self.show_status("Actualizando...", 2000)
                    break
    
    @Slot()
    def on_logout_clicked(self):
        """Maneja el click en logout."""
        if show_confirmation(
            self,
            "¿Está seguro que desea cerrar sesión?",
            title="Cerrar Sesión",
            ok_text="Sí",
            cancel_text="No",
        ):
            self.logout_requested.emit()
    
    @Slot(bool)
    def toggle_fullscreen(self, checked: bool):
        """Alterna el modo pantalla completa."""
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()
    
    @Slot()
    def show_about(self):
        """Muestra el diálogo Acerca de."""
        show_info_dialog(
            self,
            "FitPilot v1.0.0\n\n"
            "Sistema de Gestión para Gimnasios\n\n"
            "© 2025 FitPilot",
            title="Acerca de FitPilot",
        )
    
    @Slot()
    def check_connection(self):
        """Verifica el estado de conexión (placeholder)."""
        # Esto se conectará con el servicio real
        pass
    
    def set_connection_status(self, connected: bool):
        """Actualiza el indicador de conexión."""
        if connected:
            self.connection_status.setText("● Conectado")
            self.connection_status.setProperty("connected", "true")
        else:
            self.connection_status.setText("● Desconectado")
            self.connection_status.setProperty("connected", "false")

        # Refrescar estilos
        self.connection_status.style().polish(self.connection_status)
    
    def show_status(self, message: str, timeout: int = 0):
        """Muestra un mensaje en la barra de estado."""
        self.status_bar.showMessage(message, timeout)
    
    def show_error(self, title: str, message: str):
        """Muestra un diálogo de error."""
        show_error_dialog(self, message, title=title)
    
    def show_info(self, title: str, message: str):
        """Muestra un diálogo de información."""
        show_info_dialog(self, message, title=title)

    @Slot()
    def show_sessions_dialog(self):
        """Muestra el diálogo de sesiones activas."""
        try:
            from .dialogs.sessions_dialog import SessionsDialog
            dialog = SessionsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to show sessions dialog: {e}")
            self.show_error("Error", f"No se pudo abrir el diálogo de sesiones: {str(e)}")

    def _load_current_session_info(self):
        """Carga información de la sesión actual."""
        try:
            from ..core.di import container
            from ..threads.authenticated_operations import start_authenticated_operation

            sessions_service = container.get('sessions_service')

            def on_sessions_loaded(sessions):
                # Buscar la sesión actual
                current_session = next((s for s in sessions if s.get('is_current')), None)
                if current_session:
                    device_icon = sessions_service.get_device_icon(current_session['device_name'])
                    self.session_label.setText(f"{device_icon} {current_session['device_name']}")
                else:
                    self.session_label.setText("🖥️ Esta sesión")

            # Ejecutar correctamente la operación autenticada
            start_authenticated_operation(
                service=sessions_service,
                method_name="get_my_sessions",
                parent=self,
                on_success=on_sessions_loaded,
                on_error=lambda err: logger.error(f"Failed to load session info: {err}"),
            )

        except Exception as e:
            logger.error(f"Failed to load session info: {e}")
            self.session_label.setText("🖥️ Esta sesión")
