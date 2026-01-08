"""
Vista de Login para FitPilot.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QFrame,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QColor, QPalette

from ..core import get_logger

logger = get_logger(__name__)


class LoginView(QWidget):
    """Vista de login de la aplicación."""

    # Señales
    login_requested = Signal(str, str, bool)  # email, password, remember_me

    def __init__(self) -> None:
        super().__init__()
        self.setup_ui()
        self.setup_styles()

    def setup_ui(self) -> None:
        """Configura la interfaz de usuario."""
        self.setWindowTitle("FitPilot - Login")
        self.setFixedSize(420, 540)

        # Layout principal
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(32, 28, 32, 20)
        main_layout.setSpacing(18)

        # Título
        title_label = QLabel("FitPilot")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setObjectName("titleLabel")
        main_layout.addWidget(title_label)

        # Subtítulo
        subtitle_label = QLabel("Sistema de Gestión de Gimnasio")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setObjectName("subtitleLabel")
        main_layout.addWidget(subtitle_label)

        main_layout.addSpacing(18)

        # Card de login
        login_frame = QFrame()
        login_frame.setObjectName("loginFrame")
        login_layout = QVBoxLayout(login_frame)
        login_layout.setContentsMargins(20, 20, 20, 20)
        login_layout.setSpacing(12)

        # Email
        email_label = QLabel("Email")
        email_label.setObjectName("fieldLabel")
        login_layout.addWidget(email_label)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("usuario@ejemplo.com")
        self.email_input.setObjectName("emailInput")
        login_layout.addWidget(self.email_input)

        # Password
        password_label = QLabel("Contraseña")
        password_label.setObjectName("fieldLabel")
        login_layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Ingresa tu contraseña")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("passwordInput")
        login_layout.addWidget(self.password_input)

        # Recordar
        self.remember_checkbox = QCheckBox("Recordar sesión")
        self.remember_checkbox.setObjectName("rememberCheck")
        login_layout.addWidget(self.remember_checkbox)

        # Botón
        self.login_button = QPushButton("Iniciar sesión")
        self.login_button.setObjectName("loginButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.on_login_clicked)
        self.login_button.setMinimumHeight(44)

        # Forzar color de texto del botón vía palette (algunos estilos de Windows lo ignoran con solo QSS)
        pal = self.login_button.palette()
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("white"))
        self.login_button.setPalette(pal)

        login_layout.addSpacing(6)
        login_layout.addWidget(self.login_button)

        # Error
        self.error_label = QLabel()
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        login_layout.addWidget(self.error_label)

        # Efecto de sombra para error label (reutilizable)
        self.error_shadow_effect = QGraphicsDropShadowEffect()
        self.error_shadow_effect.setBlurRadius(12)
        self.error_shadow_effect.setXOffset(0)
        self.error_shadow_effect.setYOffset(2)
        self.error_shadow_effect.setColor(QColor(185, 28, 28, 100))
        self.error_label.setGraphicsEffect(self.error_shadow_effect)

        main_layout.addWidget(login_frame, 1)  # que crezca un poco si hay espacio
        main_layout.addStretch()

        # Footer
        footer_label = QLabel("© 2025 FitPilot • Todos los derechos reservados")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_label.setObjectName("footerLabel")
        main_layout.addWidget(footer_label)

        self.setLayout(main_layout)

        # Enter para login
        self.password_input.returnPressed.connect(self.on_login_clicked)
        self.email_input.returnPressed.connect(self.password_input.setFocus)

        # Sombra del card
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 40))
        login_frame.setGraphicsEffect(shadow)

    def setup_styles(self) -> None:
        """Aplica los estilos con alto contraste y buena legibilidad."""
        # Paleta de colores
        # Verde accesible: #15803D (hover) y #166534 (pressed)
        # Primario: texto #111827, secundario #4B5563, placeholder #6B7280
        style = """
        QWidget {
            background-color: #F3F4F6; /* gris claro */
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            color: #111827; /* casi negro */
        }

        #titleLabel {
            color: #0F172A; /* gris muy oscuro */
            letter-spacing: 0.3px;
        }

        #subtitleLabel {
            color: #4B5563;
            font-size: 13px;
        }

        #loginFrame {
            background-color: #FFFFFF;
            border-radius: 12px;
            border: 1px solid #E5E7EB;
        }

        #fieldLabel {
            color: #1F2937;
            font-weight: 600;
        }

        QLineEdit {
            padding: 10px 12px;
            border: 1.5px solid #D1D5DB;
            border-radius: 8px;
            background-color: #FFFFFF;
            color: #111827;
            selection-background-color: #15803D;
            selection-color: #FFFFFF;
        }
        QLineEdit::placeholder {
            color: #6B7280;
        }
        QLineEdit:focus {
            border: 2px solid #22C55E;        /* anillo verde */
            outline: none;
            background-color: #FFFFFF;
        }
        QLineEdit:disabled {
            background-color: #F3F4F6;
            color: #9CA3AF;
        }

        QCheckBox {
            color: #374151;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 18px; height: 18px;
            border-radius: 4px;
            border: 2px solid #9CA3AF;
            background: #FFFFFF;
        }
        QCheckBox::indicator:checked {
            background: #15803D;
            border-color: #15803D;
        }
        QCheckBox::indicator:disabled {
            background: #E5E7EB;
            border-color: #D1D5DB;
        }

        #loginButton {
            background-color: #15803D;  /* verde oscuro accesible */
            color: #FFFFFF;
            border: none;
            padding: 10px 14px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.3px;
        }
        #loginButton:hover {
            background-color: #166534;
        }
        #loginButton:pressed {
            background-color: #14532D;
        }
        #loginButton:disabled {
            background-color: #86EFAC;  /* verde claro */
            color: rgba(255,255,255,0.95);
        }

        #errorLabel {
            color: #991B1B;
            background-color: #FEE2E2;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #FCA5A5;
            font-weight: 600;
        }

        #footerLabel {
            color: #9CA3AF;
            font-size: 11px;
        }
        """
        self.setStyleSheet(style)

    @Slot()
    def on_login_clicked(self) -> None:
        """Maneja el click en el botón de login."""
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email:
            self.show_error("Por favor, ingresa tu email.")
            return
        if not password:
            self.show_error("Por favor, ingresa tu contraseña.")
            return

        self.set_loading(True)
        remember_me = self.remember_checkbox.isChecked()
        self.login_requested.emit(email, password, remember_me)

    def show_error(self, message: str) -> None:
        """Muestra un mensaje de error con sombra suave."""
        self.error_label.setText(message)
        self.error_label.show()
        # El efecto de sombra ya está configurado en setup_ui()

    def hide_error(self) -> None:
        self.error_label.hide()

    def set_loading(self, loading: bool) -> None:
        self.login_button.setEnabled(not loading)
        self.email_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)

        if loading:
            self.login_button.setText("Iniciando sesión…")
            self.hide_error()
        else:
            self.login_button.setText("Iniciar sesión")

    def clear_fields(self) -> None:
        self.email_input.clear()
        self.password_input.clear()
        self.remember_checkbox.setChecked(False)
        self.hide_error()

    def set_default_credentials(self, email: str = "", password: str = "") -> None:
        if email:
            self.email_input.setText(email)
        if password:
            self.password_input.setText(password)
