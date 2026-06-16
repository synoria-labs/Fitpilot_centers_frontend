"""
Ventana principal de FitPilot con navegación por barra lateral (Sidebar).
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QToolBar, QStatusBar,
    QMenu, QMenuBar, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, Slot, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
)
from PySide6.QtGui import QAction, QIcon, QFont
from ..core import get_logger
from ..utils.dialog_helpers import (
    show_confirmation,
    show_error as show_error_dialog,
    show_info as show_info_dialog,
)
from .widgets.sidebar import Sidebar, SidebarItem

logger = get_logger(__name__)


# Navegación principal (reemplaza la antigua lista de tuplas ``tab_configs``).
# Notificaciones NO está aquí: vive en el menú Configuración (ver setup_menu).
NAV_ITEMS = [
    SidebarItem("members", "Socios", "mdi6.account-group", is_public=True),
    SidebarItem("classes", "Clases", "mdi6.calendar-month", is_public=True),
    SidebarItem("memberships", "Membresías", "mdi6.card-account-details", is_public=True),
    SidebarItem("dashboard", "Dashboard", "mdi6.view-dashboard", is_public=True),
    SidebarItem("whatsapp_chat", "Chats", "mdi6.message-text", is_public=False),
    SidebarItem("whatsapp", "WhatsApp", "mdi6.whatsapp", is_public=False),
    SidebarItem("chatbot_config", "Chatbot", "mdi6.robot-outline", is_public=False),
    SidebarItem("campaigns", "Campañas", "mdi6.bullhorn", is_public=False),
    SidebarItem("finances", "Finanzas", "mdi6.cash-multiple", is_public=False),
]

# Sección alojada en el menú Configuración (fuera de la sidebar).
SETTINGS_SECTIONS = [
    ("whatsapp_notifications", "Notificaciones"),
]


class ClickableLabel(QLabel):
    """QLabel personalizado que emite una señal al hacer click (compatibilidad)."""
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""

    # Señales
    logout_requested = Signal()
    nav_changed = Signal(str)         # tab_id de la sección seleccionada
    refresh_requested = Signal(str)   # tab_id a (re)cargar

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.tabs = {}
        self.stack_index = {}
        self._active_tab_id = None
        self._page_anim = None
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        self.setup_statusbar()
        self.setup_styles()

    def setup_ui(self):
        """Configura la interfaz principal: sidebar (izquierda) + contenido (stack)."""
        self.setWindowTitle("FitPilot - Sistema de Gestión")
        self.setGeometry(100, 100, 1280, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Barra lateral de navegación. El branding y los datos de sesión (usuario, sesión,
        # logout) viven ahora en la propia sidebar (header superior fusionado).
        self.sidebar = Sidebar()
        self.sidebar.item_selected.connect(self.on_nav_selected)
        body.addWidget(self.sidebar)

        # Host de contenido: una página por sección.
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        body.addWidget(self.content_stack, 1)

        main_layout.addLayout(body, 1)

        # Alias hacia los widgets del footer de la sidebar (los métodos existentes los usan).
        self.user_label = self.sidebar.user_label
        self.session_label = self.sidebar.session_label
        self.logout_button = self.sidebar.logout_button
        self.session_label.clicked.connect(self.show_sessions_dialog)
        self.logout_button.clicked.connect(self.on_logout_clicked)

        self.init_navigation()

    def init_navigation(self):
        """Crea los ítems de la sidebar y una página (placeholder) por sección en el stack."""
        for item in NAV_ITEMS:
            self.sidebar.add_item(item)
            placeholder = self.create_loading_widget(item.label)
            idx = self.content_stack.addWidget(placeholder)
            self.stack_index[item.tab_id] = idx
            self.tabs[item.tab_id] = {
                'name': item.label,
                'widget': placeholder,
                'loaded': False,
                'is_public': item.is_public,
            }

        # Secciones del menú Configuración (registradas en el stack pero NO en la sidebar).
        for tab_id, label in SETTINGS_SECTIONS:
            placeholder = self.create_loading_widget(label)
            idx = self.content_stack.addWidget(placeholder)
            self.stack_index[tab_id] = idx
            self.tabs[tab_id] = {
                'name': label,
                'widget': placeholder,
                'loaded': False,
                'is_public': False,
            }

        if "members" in self.stack_index:
            self.content_stack.setCurrentIndex(self.stack_index["members"])

    def create_loading_widget(self, tab_name: str) -> QWidget:
        """Crea un widget de carga (skeleton) para una sección."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

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
        """Configura la barra de menús superior."""
        menubar = self.menuBar()

        # Menú Archivo
        file_menu = menubar.addMenu("&Archivo")

        refresh_action = QAction("&Actualizar", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.on_refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

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

        collapse_action = QAction("&Colapsar barra lateral", self)
        collapse_action.setShortcut("Ctrl+B")
        collapse_action.setCheckable(True)
        collapse_action.triggered.connect(
            lambda checked: self.sidebar.set_collapsed(checked)
        )
        view_menu.addAction(collapse_action)

        # Menú Ayuda
        help_menu = menubar.addMenu("&Ayuda")

        about_action = QAction("&Acerca de", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # Menú Configuración (junto a Ayuda). Despliega sus opciones al pasar el cursor,
        # igual que los demás menús. Preparado para más opciones futuras.
        self.settings_menu = menubar.addMenu("&Configuración")
        for tab_id, label in SETTINGS_SECTIONS:
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, t=tab_id: self.show_settings_section(t))
            self.settings_menu.addAction(action)

    def setup_toolbar(self):
        """Configura la barra de herramientas."""
        toolbar = QToolBar("Herramientas Principales")
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(toolbar)

        refresh_action = QAction("Actualizar", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.on_refresh)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        self.toolbar_actions = {}

    def setup_statusbar(self):
        """Configura la barra de estado."""
        self.status_bar = self.statusBar()
        self.status_bar.setObjectName("mainStatusBar")

        self.status_message = QLabel("Listo")
        self.status_bar.addWidget(self.status_message)

        self.connection_status = QLabel("● Conectado")
        self.connection_status.setObjectName("connectionStatus")
        self.status_bar.addPermanentWidget(self.connection_status)

        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection)
        self.connection_timer.start(30000)

    def setup_styles(self):
        """Aplica estilos mínimos manteniendo el tema nativo del sistema en el contenido."""
        style = """
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
        """Establece el usuario actual y ajusta navegación/permisos."""
        self.current_user = user_data
        username = user_data.get('username', 'Usuario')
        role = user_data.get('role', 'usuario')
        self.user_label.setText(f"{username}\n({role})")

        # Cargar info de sesión (asíncrono)
        self._load_current_session_info()

        # Permisos por rol → habilita/deshabilita ítems de la sidebar y el menú Configuración.
        self.update_tabs_visibility(role)

        # Selección inicial.
        self.sidebar.set_active("members")
        self._navigate("members")

    def update_tabs_visibility(self, role: str):
        """Habilita/deshabilita ítems de navegación según el rol."""
        is_admin = (role == 'admin')
        for item in NAV_ITEMS:
            self.sidebar.set_enabled(item.tab_id, item.is_public or is_admin)
        # Notificaciones (única opción de Configuración hoy) es admin-only.
        if getattr(self, "settings_menu", None) is not None:
            self.settings_menu.setEnabled(is_admin)

    def load_tab_content(self, tab_id: str, widget: QWidget):
        """Reemplaza el placeholder de una sección por su widget real en el stack."""
        if tab_id not in self.stack_index:
            logger.warning("load_tab_content: sección desconocida '%s'", tab_id)
            return
        idx = self.stack_index[tab_id]
        old = self.content_stack.widget(idx)
        is_current = (self.content_stack.currentIndex() == idx)

        self.content_stack.removeWidget(old)
        old.deleteLater()
        self.content_stack.insertWidget(idx, widget)  # insertar en el mismo índice lo preserva

        self.tabs[tab_id]['widget'] = widget
        self.tabs[tab_id]['loaded'] = True

        if is_current:
            self.content_stack.setCurrentIndex(idx)
            self._animate_page_in(widget)

        logger.info("Tab loaded: %s", self.tabs[tab_id]['name'])

    @Slot(str)
    def on_nav_selected(self, tab_id: str):
        """Maneja la selección de una sección desde la sidebar."""
        self._navigate(tab_id)

    def show_settings_section(self, tab_id: str):
        """Abre una sección del menú Configuración en el área de contenido."""
        self.sidebar.set_active(None)  # ninguna sección de la sidebar queda activa
        self._navigate(tab_id)

    def _navigate(self, tab_id: str):
        """Cambia la página activa del stack (con fade) y dispara la carga perezosa."""
        if tab_id not in self.stack_index:
            return
        self._active_tab_id = tab_id
        idx = self.stack_index[tab_id]
        self.content_stack.setCurrentIndex(idx)
        self._animate_page_in(self.content_stack.widget(idx))

        if getattr(self, "status_message", None):
            self.status_message.setText(f"Vista: {self.tabs[tab_id]['name']}")

        if not self.tabs[tab_id]['loaded']:
            self.refresh_requested.emit(tab_id)
        self.nav_changed.emit(tab_id)

    def _animate_page_in(self, widget: QWidget):
        """Fade-in ligero de la página entrante. Libera el effect al terminar."""
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._page_anim = anim  # referencia fuerte
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @Slot()
    def on_refresh(self):
        """Actualiza (fuerza recarga de) la sección activa."""
        tab_id = self._active_tab_id
        if tab_id and tab_id in self.tabs:
            self.refresh_requested.emit(tab_id)
            self.show_status("Actualizando...", 2000)

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
        pass

    def set_connection_status(self, connected: bool):
        """Actualiza el indicador de conexión."""
        if connected:
            self.connection_status.setText("● Conectado")
            self.connection_status.setProperty("connected", "true")
        else:
            self.connection_status.setText("● Desconectado")
            self.connection_status.setProperty("connected", "false")
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
                current_session = next((s for s in sessions if s.get('is_current')), None)
                if current_session:
                    device_icon = sessions_service.get_device_icon(current_session['device_name'])
                    self.session_label.setText(f"{device_icon} {current_session['device_name']}")
                else:
                    self.session_label.setText("🖥️ Esta sesión")

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
