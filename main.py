"""
FitPilot - Sistema de Gestión para Gimnasios
Punto de entrada principal de la aplicación.
"""
import sys
import asyncio
import faulthandler
import ctypes
from pathlib import Path
from typing import Optional

# Qt recomienda mantener el event loop principal en el hilo de la GUI; en Windows se usa la policy selector para compatibilidad con PySide6.
if sys.platform.startswith('win'):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

# Agregar el directorio raí­z al path
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QSplashScreen, QMessageBox
from PySide6.QtCore import Qt, QSize, QRectF, QTimer, QPropertyAnimation
from PySide6.QtGui import QPixmap, QColor, QIcon, QPainter, QFont, QPen

from app.core import Config
from app.core import get_logger
from app.core import container
from app.views.login_view import LoginView
from app.views.main_window import MainWindow
from app.views.app_styles import app_qss
from app.views.input_glow import install_neon_input_glow
from app.views.tabs.whatsapp import theme
from app.views.widgets.brand_logo import logo_pixmap
from app.controllers.main_controller import MainController
from app.auth.session_store import SessionStore
from app.graphql.client import GraphQLClient
from app.threads.asyncio_executor import get_global_executor, shutdown_global_executor

logger = get_logger(__name__)

class FitPilotApp:
    """Aplicación principal de FitPilot."""
    
    def __init__(self) -> None:
        self.app: Optional[QApplication] = None
        self.app_icon: Optional[QIcon] = None
        self.splash: Optional[QSplashScreen] = None
        self.main_controller: Optional[MainController] = None
        self.login_view: Optional[LoginView] = None
        self.main_window: Optional[MainWindow] = None
        # Estado del splash animado
        self._splash_timer: Optional[QTimer] = None
        self._splash_fade: Optional[QPropertyAnimation] = None
        self._splash_base: Optional[QPixmap] = None
        self._splash_angle: int = 0
        self._splash_dpr: float = 1.0
    
    def initialize_services(self):
        """Inicializa los servicios de la aplicación."""
        logger.info("Initializing services...")

        try:
            # ===== CRITICAL: Initialize AsyncioExecutor FIRST =====
            # This must be done before any async operations are attempted
            logger.info("Starting AsyncioExecutor...")
            executor = get_global_executor()
            executor.start()

            # Wait for executor to be ready (max 5 seconds)
            if not executor.wait_until_ready(timeout=5.0):
                raise RuntimeError("AsyncioExecutor failed to start within 5 seconds")

            logger.info("AsyncioExecutor started successfully")

            # Registrar servicios basicos
            session_store = SessionStore()
            graphql_client = GraphQLClient()

            # Configurar dependencias circulares
            graphql_client.set_session_store(session_store)

            # Registrar en contenedor DI
            container.register('session_store', service=session_store)
            container.register('graphql_client', service=graphql_client)

            # Registrar servicios de negocio
            from app.services.subscription_service import SubscriptionService
            from app.services.members_service import MembersService
            from app.services.memberships_service import MembershipsService
            from app.services.permissions_service import PermissionsService
            from app.services.classes_service import ClassesService
            from app.services.payments_service import PaymentsService
            from app.services.whatsapp_service import WhatsAppService
            from app.services.whatsapp_chat_service import WhatsAppChatService
            from app.services.whatsapp_notifications_service import WhatsAppNotificationsService
            from app.services.chatbot_config_service import ChatbotConfigService
            from app.services.owner_agent_config_service import OwnerAgentConfigService
            from app.services.campaigns_service import CampaignsService
            from app.services.dashboard_service import DashboardService
            from app.services.cache_service import CacheService
            from app.services.standing_bookings_service import StandingBookingsService
            from app.services.sessions_service import SessionsService
            from app.services.finances_service import FinancesService
            from app.auth.auth_service import AuthService

            container.register('auth_service', service=AuthService(graphql_client, session_store))
            container.register('subscriptions_service', service=SubscriptionService(graphql_client))
            container.register('members_service', service=MembersService(graphql_client))
            container.register('memberships_service', service=MembershipsService(graphql_client))
            container.register('permissions_service', service=PermissionsService(graphql_client))
            container.register('classes_service', service=ClassesService(graphql_client))
            container.register('payments_service', service=PaymentsService(graphql_client))
            container.register('whatsapp_service', service=WhatsAppService(graphql_client))
            container.register('whatsapp_chat_service', service=WhatsAppChatService(graphql_client))
            container.register('whatsapp_notifications_service', service=WhatsAppNotificationsService(graphql_client))
            container.register('chatbot_config_service', service=ChatbotConfigService(graphql_client))
            container.register('owner_agent_config_service', service=OwnerAgentConfigService(graphql_client))
            container.register('campaigns_service', service=CampaignsService(graphql_client))
            container.register('standing_bookings_service', service=StandingBookingsService(graphql_client))
            container.register('sessions_service', service=SessionsService(graphql_client))
            cache_service = CacheService()
            container.register('cache_service', service=cache_service)
            container.register('finances_service', service=FinancesService(graphql_client, cache_service))
            container.register('dashboard_service', service=DashboardService(graphql_client, cache_service))
            logger.info("Services initialized successfully")
            return True

        except Exception as e:
                logger.error(f"Failed to initialize services: {e}")
                return False
        
    def setup_application(self):
            """Configura la aplicación Qt."""
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("FitPilot")
            self.app.setOrganizationName("FitPilot")

            if sys.platform.startswith("win"):
                try:
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FitPilot")
                except Exception as exc:
                    logger.warning("Failed to set AppUserModelID: %s", exc)

            app_icon = QIcon()
            icon_loaded = False
            # Icono multi-resolución (16→256px) con el tile degradado de marca.
            icon_path = Path(__file__).parent / "app" / "assets" / "icons" / "fitpilot.ico"
            favicon_path = Path(__file__).parent / "app" / "assets" / "icons" / "favicon.ico"

            if icon_path.exists():
                app_icon = QIcon(str(icon_path))
                icon_loaded = not app_icon.isNull()

            if not icon_loaded and favicon_path.exists():
                app_icon = QIcon()
                app_icon.addFile(str(favicon_path), QSize(16, 16))
                icon_loaded = True

            if not icon_loaded:
                logger.warning("App icon not found at %s", icon_path)

            if icon_loaded:
                self.app_icon = app_icon
                self.app.setWindowIcon(app_icon)
            
            # Configurar tema
            self.setup_theme()
            
            # Mostrar splash screen
            self.show_splash()
        
    def setup_theme(self) -> None:
            """Configura el tema de la aplicación para usar el diseño por defecto del sistema."""
            if self.app is None:
                raise RuntimeError("QApplication is not initialized")
            self.app.setStyleSheet(app_qss())

            # Glow neon en hover/focus de los inputs de texto (app-wide).
            # Guardar la referencia para que el GC no recoja el event filter.
            self._neon_glow = install_neon_input_glow(self.app)

            # Usar el estilo por defecto del sistema (no forzar Fusion)
            # PySide6 automÃ¡ticamente detectarÃ¡ el mejor estilo para cada plataforma
        
    # Dimensiones lógicas del splash
    _SPLASH_W = 460
    _SPLASH_H = 320

    def show_splash(self) -> None:
            """Muestra un splash oscuro con logo, nombre y spinner animado."""
            if self.app is None:
                raise RuntimeError("QApplication is not initialized")

            screen = self.app.primaryScreen()
            self._splash_dpr = screen.devicePixelRatio() if screen else 1.0

            self.splash = QSplashScreen()
            if self.app_icon:
                self.splash.setWindowIcon(self.app_icon)
            self.splash.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
            )

            # Capa base (fondo + logo + texto), reusada en cada frame del spinner
            self._splash_base = self._render_splash_base()
            self._splash_angle = 0
            self.splash.setPixmap(self._compose_splash(0))

            # Fade-in
            self.splash.setWindowOpacity(0.0)
            self.splash.show()
            self._splash_fade = QPropertyAnimation(self.splash, b"windowOpacity", self.splash)
            self._splash_fade.setDuration(300)
            self._splash_fade.setStartValue(0.0)
            self._splash_fade.setEndValue(1.0)
            self._splash_fade.start()

            # Spinner: re-pinta el arco cada 60ms
            self._splash_timer = QTimer(self.splash)
            self._splash_timer.setInterval(60)
            self._splash_timer.timeout.connect(self._tick_splash)
            self._splash_timer.start()

            # Procesar eventos para que se muestre
            self.app.processEvents()

    def _render_splash_base(self) -> QPixmap:
            """Pixmap base del splash (fondo oscuro + chip con logo + textos)."""
            dpr = self._splash_dpr
            w, h = self._SPLASH_W, self._SPLASH_H
            pm = QPixmap(int(w * dpr), int(h * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(QColor(theme.SPLASH_BG))

            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # Chip blanco con el logo (el navy del logo no se vería sobre el fondo)
            logo = logo_pixmap(78, dpr)
            chip_y = 56
            if logo is not None and not logo.isNull():
                lw = logo.width() / dpr
                lh = logo.height() / dpr
                pad = 16
                chip_w = lw + pad * 2
                chip_h = lh + pad * 2
                chip_x = (w - chip_w) / 2
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#ffffff"))
                p.drawRoundedRect(QRectF(chip_x, chip_y, chip_w, chip_h), 18, 18)
                p.drawPixmap(int(chip_x + pad), int(chip_y + pad), logo)
                text_top = chip_y + chip_h + 22
            else:
                text_top = chip_y + 20

            # Nombre de la app
            p.setPen(QColor(theme.TEXT_PRIMARY))
            title_font = QFont("Segoe UI", 20, QFont.Weight.Bold)
            p.setFont(title_font)
            p.drawText(
                QRectF(0, text_top, w, 32),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "FitPilot",
            )

            # Subtítulo
            p.setPen(QColor(theme.TEXT_SECONDARY))
            sub_font = QFont("Segoe UI", 10)
            p.setFont(sub_font)
            p.drawText(
                QRectF(0, text_top + 34, w, 22),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Sistema de Gestión para Gimnasios",
            )
            p.end()
            return pm

    def _compose_splash(self, angle: int) -> QPixmap:
            """Copia la base y dibuja el arco del spinner en el ángulo dado."""
            base = self._splash_base
            if base is None:
                base = self._render_splash_base()
            pm = QPixmap(base)  # copy-on-write
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            w = self._SPLASH_W
            rect = QRectF(w / 2 - 15, self._SPLASH_H - 56, 30, 30)

            # Anillo tenue de fondo
            bg_pen = QPen(QColor(255, 255, 255, 28))
            bg_pen.setWidth(4)
            p.setPen(bg_pen)
            p.drawArc(rect, 0, 360 * 16)

            # Arco de acento giratorio
            pen = QPen(QColor(theme.ACCENT))
            pen.setWidth(4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, int(-angle * 16), int(270 * 16))
            p.end()
            return pm

    def _tick_splash(self) -> None:
            if self.splash is None:
                return
            self._splash_angle = (self._splash_angle + 18) % 360
            self.splash.setPixmap(self._compose_splash(self._splash_angle))
        
    def create_views(self):
            """Crea las vistas principales."""
            logger.info("Creating views...")
            
            try:
                self.login_view = LoginView()
                self.main_window = MainWindow()

                if self.app_icon:
                    self.login_view.setWindowIcon(self.app_icon)
                    self.main_window.setWindowIcon(self.app_icon)

                logger.info("Views created successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to create views: {e}")
                return False
        
    def setup_controllers(self):
            """Configura los controladores."""
            logger.info("Setting up controllers...")
            
            try:
                self.main_controller = MainController()
                if self.login_view is None or self.main_window is None:
                    raise RuntimeError('Application views are not initialized')
                self.main_controller.initialize(self.login_view, self.main_window)
                
                # Conectar seÃ±ales del arranque
                self.main_controller.app_ready.connect(self.on_app_ready)
                self.main_controller.app_error.connect(self.on_app_error)
                
                logger.info("Controllers setup successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to setup controllers: {e}")
                return False
        
    def on_app_ready(self) -> None:
            """Cierra el splash cuando la UI base ya esta lista."""
            # Detener el spinner ANTES de destruir el splash (evita disparos huérfanos)
            if self._splash_timer is not None:
                self._splash_timer.stop()
                self._splash_timer.deleteLater()
                self._splash_timer = None
            if self._splash_fade is not None:
                self._splash_fade.stop()
                self._splash_fade = None
            self._splash_base = None

            if self.splash:
                self.splash.close()
                self.splash.deleteLater()
                self.splash = None

    def on_app_error(self, error_message: str):
            """Maneja errores crí­ticos de la aplicación."""
            logger.error(f"Application error: {error_message}")
            
            QMessageBox.critical(
                None,
                "Error CrÃ­tico",
                f"Ha ocurrido un error:\n\n{error_message}\n\n"
                "La aplicaciÃ³n se cerrarÃ¡."
            )
            
            self.cleanup()
            sys.exit(1)
        
    def start(self) -> None:
            """Inicia la aplicación."""
            # Iniciar controlador principal
            if self.main_controller is None:
                raise RuntimeError("MainController is not initialized")
            self.main_controller.start()
        
    def cleanup(self):
            """Limpia recursos antes de cerrar."""
            logger.info("Cleaning up resources...")

            if self.main_controller:
                self.main_controller.cleanup()

            # Cerrar cliente GraphQL usando el AsyncioExecutor
            graphql_client = container.get('graphql_client')
            if graphql_client:
                try:
                    executor = get_global_executor()
                    if executor.is_running():
                        import threading
                        done_event = threading.Event()

                        def on_done(_=None):
                            done_event.set()

                        signals = executor.submit_coroutine(graphql_client.close())
                        signals.result.connect(on_done)
                        signals.error.connect(on_done)
                        signals.finished.connect(on_done)

                        # Wait for close to complete (max 5 seconds)
                        done_event.wait(timeout=5.0)
                        logger.info("GraphQL client closed")
                except Exception as e:
                    logger.warning(f"Error closing GraphQL client: {e}")

            # Shutdown AsyncioExecutor
            logger.info("Shutting down AsyncioExecutor...")
            shutdown_global_executor(wait_for_tasks=True)
            logger.info("AsyncioExecutor shut down")
        
    def run(self):
        """Ejecuta la aplicación."""
        logger.info("=" * 50)
        logger.info(f"Starting FitPilot v{Config.APP_VERSION}")
        logger.info(f"Environment: {Config.ENVIRONMENT}")
        logger.info("=" * 50)

        # Instalar ganchos globales de error para capturar cierres silenciosos
        def _global_excepthook(exctype, value, tb):
            try:
                logger.exception("Uncaught exception", exc_info=(exctype, value, tb))
            except Exception:
                pass
        sys.excepthook = _global_excepthook

        # Activar faulthandler para segfaults/abortos (si es posible)
        try:
            logs_dir = Path(__file__).parent / "logs"
            logs_dir.mkdir(exist_ok=True)
            fault_log = open(logs_dir / "fitpilot_fault.log", "a", buffering=1)
            faulthandler.enable(file=fault_log, all_threads=True)
        except Exception:
            logger.debug("No se pudo habilitar faulthandler")
            

        # Normal boot path (when faulthandler enabled successfully)
        # Ensure startup always runs even if the try block above succeeds.
        self.setup_application()

        if not self.initialize_services():
            self.on_app_error("No se pudieron inicializar los servicios")
            return 1

        if not self.create_views():
            self.on_app_error("No se pudieron crear las vistas")
            return 1

        if not self.setup_controllers():
            self.on_app_error("No se pudieron configurar los controladores")
            return 1

        self.start()

        app = self.app
        if app is None:
            raise RuntimeError("QApplication is not initialized")
        try:
            result = app.exec()
        except Exception as e:
            logger.error(f"Application crashed: {e}")
            result = 1
        finally:
            self.cleanup()

        logger.info("Application closed")
        return result

def main():
        """Punto de entrada principal."""
        app = FitPilotApp()
        sys.exit(app.run())

if __name__ == "__main__":
        main()
