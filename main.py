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
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QColor, QIcon

from app.core import Config
from app.core import get_logger
from app.core import container
from app.views.login_view import LoginView
from app.views.main_window import MainWindow
from app.views.selectable_styles import selectable_item_states_qss
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
            from app.services.classes_service import ClassesService
            from app.services.payments_service import PaymentsService
            from app.services.whatsapp_service import WhatsAppService
            from app.services.whatsapp_chat_service import WhatsAppChatService
            from app.services.whatsapp_notifications_service import WhatsAppNotificationsService
            from app.services.chatbot_config_service import ChatbotConfigService
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
            container.register('classes_service', service=ClassesService(graphql_client))
            container.register('payments_service', service=PaymentsService(graphql_client))
            container.register('whatsapp_service', service=WhatsAppService(graphql_client))
            container.register('whatsapp_chat_service', service=WhatsAppChatService(graphql_client))
            container.register('whatsapp_notifications_service', service=WhatsAppNotificationsService(graphql_client))
            container.register('chatbot_config_service', service=ChatbotConfigService(graphql_client))
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
            favicon_path = Path(__file__).parent / "app" / "assets" / "icons" / "favicon.ico"
            logo_path = Path(__file__).parent / "app" / "assets" / "FitPilot-Logo.svg"

            if favicon_path.exists():
                app_icon.addFile(str(favicon_path), QSize(16, 16))
                icon_loaded = True
            else:
                logger.warning("Favicon icon not found at %s", favicon_path)

            if logo_path.exists():
                app_icon.addFile(str(logo_path), QSize(32, 32))
                app_icon.addFile(str(logo_path), QSize(64, 64))
                app_icon.addFile(str(logo_path), QSize(128, 128))
                app_icon.addFile(str(logo_path), QSize(256, 256))
                icon_loaded = True
            else:
                logger.warning("App logo not found at %s", logo_path)

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
            self.app.setStyleSheet(selectable_item_states_qss())

            # Usar el estilo por defecto del sistema (no forzar Fusion)
            # PySide6 automÃ¡ticamente detectarÃ¡ el mejor estilo para cada plataforma
        
    def show_splash(self) -> None:
            """Muestra la pantalla de splash."""
            if self.app is None:
                raise RuntimeError("QApplication is not initialized")

            # Crear splash screen simple (sin imagen por ahora)
            self.splash = QSplashScreen()
            if self.app_icon:
                self.splash.setWindowIcon(self.app_icon)
            self.splash.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
            
            # Usar un QPixmap vací­o con color de fondo
            pixmap = QPixmap(400, 300)
            pixmap.fill(QColor(44, 62, 80))  # Color de fondo
            self.splash.setPixmap(pixmap)
            
            # Mostrar mensajes
            self.splash.showMessage(
                "FitPilot\nSistema de Gestión para Gimnasios\n\nCargando...",
                Qt.AlignmentFlag.AlignCenter,
                Qt.GlobalColor.white
            )
            self.splash.show()
            
            # Procesar eventos para que se muestre
            self.app.processEvents()
        
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
