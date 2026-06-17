"""
Vista de Login para FitPilot.

Rediseño oscuro estilo Spotify: panel dividido (marca a la izquierda, formulario
a la derecha), ventana sin marco arrastrable, toggle de contraseña, spinner en el
botón, animación de entrada y un scaffold de inicio de sesión por código QR.

La API pública (señal ``login_requested`` y los métodos que invocan los
controladores) se mantiene intacta para no romper el flujo de autenticación.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QFrame,
    QStackedWidget, QButtonGroup, QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QSize, QPoint,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve,
)
from PySide6.QtGui import QFont, QColor, QIcon, QAction

import qtawesome as qta

from ..core import get_logger
from .tabs.whatsapp import theme
from .widgets.brand_logo import logo_pixmap
from .widgets.qr_mock import render_qr_mock

logger = get_logger(__name__)


class LoginView(QWidget):
    """Vista de login de la aplicación (panel dividido, tema oscuro)."""

    # Señales
    login_requested = Signal(str, str, bool)  # email, password, remember_me
    qr_login_requested = Signal()             # scaffold QR (futuro backend)

    def __init__(self) -> None:
        super().__init__()
        # Estado interno
        self._password_visible = False
        self._positioned = False
        self._dragging = False
        self._drag_offset = QPoint()
        self._spin_icon: QIcon | None = None
        self._brand_panel: QWidget | None = None
        self._title_strip: QWidget | None = None

        self.setup_ui()
        self.setup_styles()

    # ------------------------------------------------------------------ UI
    def setup_ui(self) -> None:
        """Construye la interfaz."""
        self.setWindowTitle("FitPilot - Login")
        self.setFixedSize(900, 560)
        # Ventana sin marco con esquinas redondeadas (la superficie redondeada se
        # pinta en #rootCard; el widget raíz queda translúcido).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)  # espacio para la sombra
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("rootCard")
        root.addWidget(card)

        # Sombra flotante de la tarjeta
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 170))
        card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        card_layout.addWidget(self._build_brand_panel())
        card_layout.addWidget(self._build_form_panel(), 1)

    def _build_brand_panel(self) -> QWidget:
        """Panel de marca con degradado, logo y tagline."""
        panel = QFrame()
        panel.setObjectName("brandPanel")
        panel.setFixedWidth(340)
        self._brand_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(34, 40, 34, 28)
        layout.setSpacing(18)
        layout.addStretch(2)

        # Chip blanco con el logo (el navy del logo no se vería sobre el degradado)
        chip = QFrame()
        chip.setObjectName("logoChip")
        chip_layout = QVBoxLayout(chip)
        chip_layout.setContentsMargins(20, 18, 20, 18)
        chip_layout.setSpacing(0)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dpr = self._device_pixel_ratio()
        pix = logo_pixmap(96, dpr)
        if pix is not None:
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("FitPilot")
            logo_label.setObjectName("logoFallback")
        chip_layout.addWidget(logo_label)

        chip_row = QHBoxLayout()
        chip_row.addStretch()
        chip_row.addWidget(chip)
        chip_row.addStretch()
        layout.addLayout(chip_row)

        tagline = QLabel("Gestiona tu gimnasio,\nsin complicaciones.")
        tagline.setObjectName("brandTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        layout.addWidget(tagline)

        layout.addStretch(3)

        footnote = QLabel("© 2025 FitPilot • Todos los derechos reservados")
        footnote.setObjectName("brandFootnote")
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setWordWrap(True)
        layout.addWidget(footnote)

        return panel

    def _build_form_panel(self) -> QWidget:
        """Panel derecho: barra de título, segmented Email/QR y formulario."""
        panel = QFrame()
        panel.setObjectName("formPanel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(40, 16, 40, 26)
        outer.setSpacing(0)

        # --- Barra de título propia (frameless): zona de arrastre + min/cerrar ---
        title_strip = QWidget()
        title_strip.setObjectName("titleStrip")
        title_strip.setFixedHeight(34)
        self._title_strip = title_strip
        ts = QHBoxLayout(title_strip)
        ts.setContentsMargins(0, 0, 0, 0)
        ts.setSpacing(4)
        ts.addStretch()

        btn_min = QPushButton()
        btn_min.setObjectName("winBtn")
        btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_min.setIcon(qta.icon("mdi6.window-minimize", color=theme.TEXT_SECONDARY))
        btn_min.setIconSize(QSize(16, 16))
        btn_min.setFixedSize(28, 26)
        btn_min.clicked.connect(self.showMinimized)
        ts.addWidget(btn_min)

        btn_close = QPushButton()
        btn_close.setObjectName("winClose")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setIcon(qta.icon("mdi6.close", color=theme.TEXT_SECONDARY))
        btn_close.setIconSize(QSize(16, 16))
        btn_close.setFixedSize(28, 26)
        btn_close.clicked.connect(self._on_close_clicked)
        ts.addWidget(btn_close)

        outer.addWidget(title_strip)
        outer.addSpacing(6)

        # --- Encabezado ---
        heading = QLabel("Bienvenido de nuevo")
        heading.setObjectName("formHeading")
        outer.addWidget(heading)

        sub = QLabel("Inicia sesión para continuar")
        sub.setObjectName("formSub")
        outer.addWidget(sub)
        outer.addSpacing(18)

        # --- Segmented control Email | Código QR ---
        outer.addWidget(self._build_segmented())
        outer.addSpacing(16)

        # --- Stack: formulario email / scaffold QR ---
        self.auth_stack = QStackedWidget()
        self.auth_stack.setObjectName("authStack")
        self.auth_stack.addWidget(self._build_email_page())   # index 0
        self.auth_stack.addWidget(self._build_qr_page())      # index 1
        outer.addWidget(self.auth_stack)

        outer.addStretch()

        footer = QLabel("¿Problemas para entrar? Contacta al administrador.")
        footer.setObjectName("footerLabel")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(footer)

        return panel

    def _build_segmented(self) -> QWidget:
        seg = QFrame()
        seg.setObjectName("segmented")
        lay = QHBoxLayout(seg)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self._btn_email = QPushButton("  Email")
        self._btn_email.setObjectName("segEmail")
        self._btn_email.setCheckable(True)
        self._btn_email.setChecked(True)
        self._btn_email.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_email.setIcon(qta.icon("mdi6.email-outline", color=theme.ACCENT))
        self._btn_email.clicked.connect(lambda: self._select_segment(0))

        self._btn_qr = QPushButton("  Código QR")
        self._btn_qr.setObjectName("segQr")
        self._btn_qr.setCheckable(True)
        self._btn_qr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_qr.setIcon(qta.icon("mdi6.qrcode-scan", color=theme.TEXT_SECONDARY))
        self._btn_qr.clicked.connect(lambda: self._select_segment(1))

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self._btn_email)
        group.addButton(self._btn_qr)

        lay.addWidget(self._btn_email, 1)
        lay.addWidget(self._btn_qr, 1)
        return seg

    def _build_email_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        email_label = QLabel("Email")
        email_label.setObjectName("fieldLabel")
        lay.addWidget(email_label)

        self.email_input = QLineEdit()
        self.email_input.setObjectName("emailInput")
        self.email_input.setPlaceholderText("usuario@ejemplo.com")
        self.email_input.setMinimumHeight(44)
        lay.addWidget(self.email_input)

        password_label = QLabel("Contraseña")
        password_label.setObjectName("fieldLabel")
        lay.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("passwordInput")
        self.password_input.setPlaceholderText("Ingresa tu contraseña")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(44)
        # Toggle ver/ocultar contraseña (icono al final del campo)
        self._eye_action = QAction(self)
        self._eye_action.setIcon(qta.icon("mdi6.eye", color=theme.TEXT_SECONDARY))
        self._eye_action.setToolTip("Mostrar contraseña")
        self._eye_action.triggered.connect(self._toggle_password)
        self.password_input.addAction(
            self._eye_action, QLineEdit.ActionPosition.TrailingPosition
        )
        lay.addWidget(self.password_input)

        self.remember_checkbox = QCheckBox("Recordar sesión")
        self.remember_checkbox.setObjectName("rememberCheck")
        lay.addWidget(self.remember_checkbox)

        lay.addSpacing(4)

        self.login_button = QPushButton("Iniciar sesión")
        self.login_button.setObjectName("loginButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.setMinimumHeight(46)
        self.login_button.setIconSize(QSize(20, 20))
        self.login_button.clicked.connect(self.on_login_clicked)
        lay.addWidget(self.login_button)

        self.error_label = QLabel()
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        lay.addWidget(self.error_label)

        # Enter para login
        self.password_input.returnPressed.connect(self.on_login_clicked)
        self.email_input.returnPressed.connect(self.password_input.setFocus)

        return page

    def _build_qr_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addStretch()

        # El propio QR (tarjeta blanca) es la "caja": se renderiza como pixmap.
        self._qr_image = QLabel()
        self._qr_image.setObjectName("qrImage")
        self._qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_image.setPixmap(self._render_qr())
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self._qr_image)
        row.addStretch()
        lay.addLayout(row)

        lay.addSpacing(6)

        self._qr_status = QLabel("Escanea el código para iniciar sesión")
        self._qr_status.setObjectName("qrTitle")
        self._qr_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_status.setWordWrap(True)
        lay.addWidget(self._qr_status)

        hint = QLabel(
            "Desde tu teléfono, abre la cámara o el escáner de QR para escanear este código."
        )
        hint.setObjectName("qrHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addSpacing(2)
        preview = QLabel("VISTA PREVIA")
        preview.setObjectName("qrPreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(preview)

        lay.addStretch()
        return page

    def _render_qr(self):
        """Pixmap del QR de maqueta (decorativo) a la resolución de pantalla."""
        return render_qr_mock(188, self._device_pixel_ratio())

    # --------------------------------------------------------------- Estilos
    def setup_styles(self) -> None:
        """Hoja de estilos oscura derivada de los tokens de marca."""
        style = f"""
        LoginView {{ background: transparent; }}

        #rootCard {{
            background-color: {theme.SPLASH_BG};
            border-radius: 18px;
        }}

        /* ----- Panel de marca ----- */
        #brandPanel {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme.BRAND_NAVY}, stop:0.55 #1f4a82, stop:1 #2563a0);
            border-top-left-radius: 18px;
            border-bottom-left-radius: 18px;
        }}
        #logoChip {{
            background-color: #ffffff;
            border-radius: 22px;
        }}
        #logoFallback {{ color: {theme.BRAND_NAVY}; font-size: 26px; font-weight: 800; }}
        #brandTagline {{
            color: rgba(233, 237, 239, 0.92);
            font-size: 17px;
            font-weight: 600;
            line-height: 22px;
        }}
        #brandFootnote {{ color: rgba(233, 237, 239, 0.55); font-size: 11px; }}

        /* ----- Panel de formulario ----- */
        #formPanel {{
            background-color: {theme.SPLASH_BG};
            border-top-right-radius: 18px;
            border-bottom-right-radius: 18px;
        }}
        QWidget {{ font-family: 'Segoe UI', Arial, sans-serif; }}
        #formHeading {{ color: {theme.TEXT_PRIMARY}; font-size: 24px; font-weight: 800; }}
        #formSub {{ color: {theme.TEXT_SECONDARY}; font-size: 13px; }}
        #fieldLabel {{ color: {theme.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; }}

        QLineEdit#emailInput, QLineEdit#passwordInput {{
            background-color: {theme.INPUT_BG};
            color: {theme.TEXT_PRIMARY};
            border: 1.5px solid transparent;
            border-radius: 11px;
            padding: 11px 14px;
            font-size: 14px;
            selection-background-color: {theme.ACCENT};
            selection-color: #0b141a;
        }}
        QLineEdit#emailInput:focus, QLineEdit#passwordInput:focus {{
            border: 1.6px solid {theme.ACCENT};
            background-color: #0e171d;
        }}
        QLineEdit#emailInput:disabled, QLineEdit#passwordInput:disabled {{
            color: {theme.TEXT_SECONDARY};
        }}

        /* ----- Segmented ----- */
        #segmented {{ background-color: {theme.INPUT_BG}; border-radius: 12px; }}
        #segmented QPushButton {{
            background: transparent; border: none;
            color: {theme.TEXT_SECONDARY};
            padding: 9px 12px; border-radius: 9px;
            font-size: 13px; font-weight: 600; text-align: center;
        }}
        #segmented QPushButton:checked {{ background-color: #0e171d; color: {theme.ACCENT}; }}
        #segmented QPushButton:hover:!checked {{ color: {theme.TEXT_PRIMARY}; }}

        /* ----- Recordar ----- */
        QCheckBox#rememberCheck {{ color: {theme.TEXT_SECONDARY}; spacing: 8px; font-size: 13px; }}
        QCheckBox#rememberCheck::indicator {{
            width: 18px; height: 18px; border-radius: 5px;
            border: 1.5px solid #3a4a54; background: {theme.INPUT_BG};
        }}
        QCheckBox#rememberCheck::indicator:checked {{
            background: {theme.ACCENT}; border-color: {theme.ACCENT};
        }}

        /* ----- Botón ----- */
        #loginButton {{
            background-color: {theme.ACCENT_STRONG};
            color: #ffffff; border: none; border-radius: 23px;
            padding: 12px 16px; font-size: 15px; font-weight: 700; letter-spacing: 0.3px;
        }}
        #loginButton:hover {{ background-color: {theme.ACCENT_STRONG_HOVER}; }}
        #loginButton:pressed {{ background-color: {theme.ACCENT_STRONG_PRESSED}; }}
        #loginButton:disabled {{ background-color: #243b46; color: rgba(233, 237, 239, 0.65); }}

        /* ----- Error ----- */
        #errorLabel {{
            color: #FCA5A5; background-color: rgba(220, 38, 38, 0.12);
            border: 1px solid rgba(248, 113, 113, 0.45); border-radius: 9px;
            padding: 10px 12px; font-weight: 600;
        }}

        /* ----- QR ----- */
        #qrTitle {{ color: {theme.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; }}
        #qrHint {{ color: {theme.TEXT_SECONDARY}; font-size: 12px; }}
        #qrPreview {{ color: {theme.TEXT_SECONDARY}; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }}

        /* ----- Botones de ventana ----- */
        #winBtn, #winClose {{ background: transparent; border: none; border-radius: 8px; }}
        #winBtn:hover {{ background-color: rgba(255, 255, 255, 0.08); }}
        #winClose:hover {{ background-color: rgba(229, 57, 53, 0.85); }}

        #footerLabel {{ color: rgba(233, 237, 239, 0.40); font-size: 11px; }}
        """
        self.setStyleSheet(style)

    # ---------------------------------------------------------- Interacción
    @Slot()
    def on_login_clicked(self) -> None:
        """Valida y emite la solicitud de login."""
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

    def _toggle_password(self) -> None:
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_action.setIcon(qta.icon("mdi6.eye-off", color=theme.TEXT_SECONDARY))
            self._eye_action.setToolTip("Ocultar contraseña")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_action.setIcon(qta.icon("mdi6.eye", color=theme.TEXT_SECONDARY))
            self._eye_action.setToolTip("Mostrar contraseña")

    def _select_segment(self, index: int) -> None:
        self.auth_stack.setCurrentIndex(index)
        active = theme.ACCENT
        inactive = theme.TEXT_SECONDARY
        self._btn_email.setIcon(
            qta.icon("mdi6.email-outline", color=active if index == 0 else inactive)
        )
        self._btn_qr.setIcon(
            qta.icon("mdi6.qrcode-scan", color=active if index == 1 else inactive)
        )
        if index == 1:
            self.start_qr_session()

    def _on_close_clicked(self) -> None:
        """Cerrar desde el login equivale a salir de la app."""
        app = QApplication.instance()
        if app is not None:
            app.quit()
        else:
            self.close()

    # ----------------------------------------------------- API pública (auth)
    def show_error(self, message: str) -> None:
        """Muestra un mensaje de error."""
        self.error_label.setText(message)
        self.error_label.show()

    def hide_error(self) -> None:
        self.error_label.hide()

    def set_loading(self, loading: bool) -> None:
        self.login_button.setEnabled(not loading)
        self.email_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self._btn_email.setEnabled(not loading)
        self._btn_qr.setEnabled(not loading)

        if loading:
            # Spinner animado dentro del botón (qta.Spin se parenta al botón)
            self._spin_icon = qta.icon(
                "mdi6.loading", color="white", animation=qta.Spin(self.login_button)
            )
            self.login_button.setIcon(self._spin_icon)
            self.login_button.setText("  Iniciando sesión…")
            self.hide_error()
        else:
            self.login_button.setIcon(QIcon())
            self._spin_icon = None
            self.login_button.setText("Iniciar sesión")

    def clear_fields(self) -> None:
        self.email_input.clear()
        self.password_input.clear()
        self.remember_checkbox.setChecked(False)
        self.hide_error()
        # Resetear estados visuales para el re-show tras logout
        self._password_visible = False
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye_action.setIcon(qta.icon("mdi6.eye", color=theme.TEXT_SECONDARY))
        self.login_button.setIcon(QIcon())
        self._spin_icon = None
        self._btn_email.setChecked(True)
        self._select_segment(0)

    def set_default_credentials(self, email: str = "", password: str = "") -> None:
        if email:
            self.email_input.setText(email)
        if password:
            self.password_input.setText(password)

    # ------------------------------------------------------- Scaffold QR
    def start_qr_session(self) -> None:
        """Punto de extensión del login por QR.

        Por ahora solo muestra el placeholder. TODO: conectar backend QR-auth
        (emitir ``qr_login_requested`` y poblar el QR con ``set_qr_pixmap``).
        """
        self.show_qr_pending()

    def show_qr_pending(self) -> None:
        self._qr_image.setPixmap(self._render_qr())
        self._qr_status.setText("Escanea el código para iniciar sesión")

    def show_qr_expired(self) -> None:
        self._qr_image.setPixmap(
            qta.icon("mdi6.qrcode-remove", color="#FCA5A5").pixmap(QSize(96, 96))
        )
        self._qr_status.setText("Código expirado")

    def set_qr_pixmap(self, pixmap) -> None:
        """Coloca un QR real (cuando exista backend)."""
        if pixmap is not None:
            self._qr_image.setPixmap(pixmap)
            self._qr_status.setText("Escanea el código para iniciar sesión")

    # ----------------------------------------------- Ventana frameless
    def _device_pixel_ratio(self) -> float:
        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        return screen.devicePixelRatio() if screen else 1.0

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._positioned:
            self._positioned = True
            self._center_on_screen()
            self._play_entrance()

    def _center_on_screen(self) -> None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def _play_entrance(self) -> None:
        final = self.pos()
        start = QPoint(final.x(), final.y() + 18)
        self.move(start)
        self.setWindowOpacity(0.0)

        self._anim_pos = QPropertyAnimation(self, b"pos", self)
        self._anim_pos.setDuration(240)
        self._anim_pos.setStartValue(start)
        self._anim_pos.setEndValue(final)
        self._anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_op = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_op.setDuration(240)
        self._anim_op.setStartValue(0.0)
        self._anim_op.setEndValue(1.0)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._anim_pos)
        self._anim_group.addAnimation(self._anim_op)
        self._anim_group.start()

    # Arrastre de la ventana (solo desde el panel de marca o la barra de título)
    def _in_drag_zone(self, global_pos: QPoint) -> bool:
        for w in (self._brand_panel, self._title_strip):
            if w is None:
                continue
            local = w.mapFromGlobal(global_pos)
            if w.rect().contains(local):
                child = w.childAt(local)
                if isinstance(child, QPushButton):
                    return False
                return True
        return False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._in_drag_zone(
            event.globalPosition().toPoint()
        ):
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)
