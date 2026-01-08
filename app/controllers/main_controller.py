"""
Controlador principal para coordinar toda la aplicación.
"""
from importlib import import_module
import threading
from typing import Any, Dict, Optional, Set, Protocol, runtime_checkable, cast

from PySide6.QtCore import QObject, Signal, QThreadPool, Qt, Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..core.logging import get_logger
from ..threads.workers import TabLoader
from ..threads.asyncio_executor import get_global_executor
from .auth_controller import AuthController

logger = get_logger(__name__)


# ===== Protocolos para que Pylance conozca la "forma" de las vistas =====

@runtime_checkable
class LoginViewLike(Protocol):
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def set_default_credentials(self, email: str) -> None: ...


@runtime_checkable
class MainWindowLike(Protocol):
    # Señales (tipadas como Any para no pelear con los stubs de Qt)
    tab_changed: Any           # emite int
    refresh_requested: Any     # emite str (tab_id)

    # Widgets principales
    tab_widget: Any            # QTabWidget

    # Métodos usados por el controlador
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def set_current_user(self, user: Dict[str, Any]) -> None: ...
    def load_tab_content(self, tab_id: str, widget: QWidget) -> None: ...
    def show_error(self, title: str, msg: str) -> None: ...


class MainController(QObject):
    """Controlador principal de la aplicación."""

    # Señales propias
    app_ready = Signal()
    app_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.auth_controller = AuthController()

        # Pool de hilos
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

        # Estado
        self.tab_controllers: Dict[str, Any] = {}
        self.services: Dict[str, Any] = {}
        self.loaded_tabs: Set[str] = set()
        self.loading_tabs: Set[str] = set()
        self.current_user: Optional[Dict[str, Any]] = None

        # Keep strong references to workers to prevent premature deletion
        self._active_workers: Dict[str, Any] = {}

        # Vistas
        self.login_view: Optional[LoginViewLike] = None
        self.main_window: Optional[MainWindowLike] = None

        logger.info("Main controller initialized")

    def initialize(self, login_view: QObject, main_window: QObject) -> None:
        """Inicializa el controlador con las vistas."""
        # Hacemos cast para que Pylance entienda los métodos/atributos usados.
        self.login_view = cast(LoginViewLike, login_view)
        self.main_window = cast(MainWindowLike, main_window)

        # Configurar controlador de autenticación
        self.auth_controller.set_views(login_view, main_window)

        # Conectar señales
        self.auth_controller.login_success.connect(self.on_login_success)
        self.auth_controller.logout_success.connect(self.on_logout_success)

        if self.main_window:
            self.main_window.tab_changed.connect(self.on_tab_changed)
            self.main_window.refresh_requested.connect(
                lambda tab_id: self.load_tab_async(tab_id, force=True)
            )

    def start(self) -> None:
        """Inicia la aplicación."""
        try:
            # Primero intentar restaurar sesión desde almacenamiento persistente
            restored = self.try_restore_session()

            if not restored:
                # Si no se pudo restaurar, verificar sesión existente en memoria
                if self.auth_controller.check_existing_session():
                    user_data = self.auth_controller.get_current_user()
                    if not user_data:
                        raise RuntimeError("No se pudo obtener el usuario de la sesión actual.")
                    self.on_login_success(user_data)
                else:
                    self.show_login()

            self.app_ready.emit()

        except Exception as e:
            logger.exception(f"Startup error: {e}")
            self.app_error.emit(str(e))

    def try_restore_session(self) -> bool:
        """
        Intenta restaurar la sesión desde el almacenamiento persistente.

        Returns:
            bool: True si la sesión se restauró exitosamente, False en caso contrario
        """
        try:
            from ..auth.persistent_storage import load_refresh_token
            from ..graphql.client import GraphQLClient

            # Cargar el refresh token guardado
            stored_data = load_refresh_token()
            if not stored_data:
                logger.debug("No stored session found")
                return False

            username, refresh_token = stored_data
            logger.info(f"Attempting to restore session for user: {username}")

            # Restaurar el refresh token en las cookies del cliente GraphQL
            GraphQLClient.restore_refresh_token(refresh_token)

            # Intentar refrescar el token usando AsyncioExecutor
            auth_service = self.auth_controller.auth_service

            executor = get_global_executor()
            if not executor.is_running():
                logger.error("AsyncioExecutor is not running, cannot restore session")
                return False

            # Contenedor para resultado
            result_container = {"success": None, "error": None}
            done_event = threading.Event()

            def on_result(success):
                logger.debug(f"on_result called with success={success}")
                result_container["success"] = success
                done_event.set()
                logger.debug("done_event set from on_result")

            def on_error(error_msg):
                logger.debug(f"on_error called with error={error_msg}")
                result_container["error"] = error_msg
                done_event.set()
                logger.debug("done_event set from on_error")

            # Enviar al executor
            logger.debug("Submitting refresh_token coroutine to executor")
            signals = executor.submit_coroutine(auth_service.refresh_token())
            
            # CRITICAL: Use DirectConnection to avoid deadlock since main thread is blocked waiting
            # The default AutoConnection can cause deadlock when crossing threads if receiver is blocked
            signals.result.connect(on_result, Qt.ConnectionType.DirectConnection)
            signals.error.connect(on_error, Qt.ConnectionType.DirectConnection)
            logger.debug("Signal handlers connected, waiting for result")

            # Esperar resultado
            if not done_event.wait(timeout=10.0):
                logger.error("Token refresh timeout during session restore")
                return False

            # Verificar resultado
            if result_container["error"] is not None:
                logger.error(f"Error refreshing token: {result_container['error']}")
                from ..auth.persistent_storage import clear_refresh_token
                clear_refresh_token()
                return False

            success = result_container["success"]
            if success and auth_service.is_authenticated():
                user_data = auth_service.get_current_user()
                if user_data:
                    logger.info(f"Session restored successfully for user: {username}")
                    self.on_login_success(user_data)
                    return True
                else:
                    logger.warning("Token refresh succeeded but no user data available")
            else:
                logger.warning("Failed to refresh token, clearing persistent storage")
                from ..auth.persistent_storage import clear_refresh_token
                clear_refresh_token()

        except Exception as e:
            logger.error(f"Error restoring session: {e}")
            # En caso de error, limpiar el almacenamiento persistente
            try:
                from ..auth.persistent_storage import clear_refresh_token
                clear_refresh_token()
            except:
                pass

        return False

    def show_login(self) -> None:
        """Muestra la pantalla de login."""
        if self.main_window:
            self.main_window.hide()

        if self.login_view:
            self.login_view.show()

            # En desarrollo, establecer credenciales por defecto
            try:
                from ..core.config import Config
                if getattr(Config, "is_development", lambda: False)():
                    self.login_view.set_default_credentials("aleramos")
            except Exception:
                logger.debug("No se pudo establecer credenciales por defecto (modo dev).")

    @Slot(dict)
    def on_login_success(self, user_data: Dict[str, Any]) -> None:
        """Maneja el login exitoso."""
        logger.info(f"User logged in: {user_data.get('username')}")
        self.current_user = user_data

        if self.login_view:
            self.login_view.hide()

        if self.main_window:
            self.main_window.set_current_user(user_data)
            self.main_window.show()
            # Cargar pestanas en paralelo segun permisos
            self.load_initial_tabs(user_data.get('role'))

    @Slot()
    def on_logout_success(self) -> None:
        """Maneja el logout exitoso."""
        logger.info("User logged out")
        self.current_user = None
        self.tab_controllers.clear()
        self.loaded_tabs.clear()
        self.loading_tabs.clear()
        self.show_login()

    def load_initial_tabs(self, user_role: Optional[str] = None) -> None:
        """Carga las pestanas iniciales segun los permisos del usuario."""
        # Solo cargar la primera pestaña inicialmente
        # Las demás se cargarán cuando el usuario las seleccione
        self.load_tab_async("members")

    def load_tab_async(self, tab_id: str, force: bool = False) -> None:
        """Carga una pestaña de forma asíncrona."""
        if force:
            self.loaded_tabs.discard(tab_id)

        if not force and tab_id in self.loaded_tabs:
            logger.debug(f"Tab '{tab_id}' ya está cargada. Omitiendo.")
            return

        if tab_id in self.loading_tabs:
            logger.debug(f"Tab '{tab_id}' ya se está cargando. Omitiendo.")
            return

        self.loading_tabs.add(tab_id)

        worker = TabLoader(tab_id)
        logger.info(f"TabLoader created for tab: {tab_id}")

        # CRITICAL: Store worker reference to prevent premature deletion
        worker_key = f"tab_loader_{tab_id}"
        self._active_workers[worker_key] = worker
        logger.info(f"Worker reference stored with key: {worker_key}")

        # Importante: capturar tab_id en el closure correctamente
        def make_loaded_handler(tab_id_local):
            def handler(payload):
                logger.info(f"Handler called for tab {tab_id_local} with payload type: {type(payload)}")
                self.on_tab_loaded(tab_id_local, payload)
            return handler

        def make_error_handler(tab_id_local):
            def handler(err):
                logger.info(f"Error handler called for tab {tab_id_local}: {err}")
                self.on_tab_error(tab_id_local, err)
            return handler

        def make_finished_handler(worker_key_local):
            def handler():
                logger.info(f"Finished handler called, removing worker: {worker_key_local}")
                self._active_workers.pop(worker_key_local, None)
            return handler

        worker.signals.result.connect(make_loaded_handler(tab_id))
        worker.signals.error.connect(make_error_handler(tab_id))
        worker.signals.finished.connect(make_finished_handler(worker_key))
        logger.info(f"Signals connected for tab: {tab_id}")

        self.thread_pool.start(worker)
        logger.info(f"Loading tab: {tab_id}")

    def on_tab_loaded(self, tab_id: str, payload: Any) -> None:
        """Maneja cuando una pestaña termina de cargarse."""
        try:
            logger.info(f"on_tab_loaded called for tab: {tab_id}")

            if not payload:
                logger.error(f"No payload received for tab {tab_id}")
                return

            widget = self._build_tab_widget(tab_id, payload)
            if self.main_window:
                self.main_window.load_tab_content(tab_id, widget)

            controller = getattr(widget, "controller", None)
            if controller is not None:
                self.tab_controllers[tab_id] = controller

            self.loaded_tabs.add(tab_id)
            logger.info(f"Tab '{tab_id}' successfully added to loaded_tabs")
        except Exception as e:
            logger.exception(f"Error loading tab {tab_id}: {e}")
        finally:
            self.loading_tabs.discard(tab_id)

    def _build_tab_widget(self, tab_id: str, payload: Any) -> QWidget:
        """Construye la pestaña en el hilo principal a partir del payload del worker."""
        try:
            if isinstance(payload, dict):
                ptype = payload.get("type")
                if ptype == "widget_class":
                    module = import_module(payload["module"])
                    tab_class = getattr(module, payload["class"])
                    inst = tab_class()
                    if isinstance(inst, QWidget):
                        return inst
                    raise TypeError(f"La clase para '{tab_id}' no es un QWidget.")
                if ptype == "placeholder":
                    return self._create_placeholder_tab(payload.get("message"), tab_id)
                if ptype == "factory" and callable(payload.get("factory")):
                    res = payload["factory"]()
                    if isinstance(res, QWidget):
                        return res
                    raise TypeError(f"La factory de '{tab_id}' no devolvió un QWidget.")

            if callable(payload):
                res = payload()
                if isinstance(res, QWidget):
                    return res
                raise TypeError(f"El callable de '{tab_id}' no devolvió un QWidget.")

            if isinstance(payload, QWidget):
                return payload

        except Exception as exc:
            logger.exception(f"Failed to build widget for tab {tab_id}: {exc}")

        # Fallback seguro
        return self._create_placeholder_tab(None, tab_id)

    def _create_placeholder_tab(self, message: Optional[str], tab_id: str) -> QWidget:
        """Crea una pestaña placeholder cuando la real no puede construirse."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)
        layout.addStretch()

        label = QLabel(message or f"Pestaña '{tab_id}' no disponible")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        layout.addStretch()
        return widget

    def on_tab_error(self, tab_id: str, error: str) -> None:
        """Maneja el error al cargar una pestaña."""
        self.loading_tabs.discard(tab_id)
        logger.error(f"Error loading tab {tab_id}: {error}")

        if self.main_window:
            self.main_window.show_error("Error", f"No se pudo cargar {tab_id}: {error}")

    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        """Maneja el cambio de pestaña."""
        logger.debug(f"Tab changed to index: {index}")

        # Verificar si necesitamos cargar la pestaña
        if self.main_window and index >= 0:
            tab_name = self.main_window.tab_widget.tabText(index)

            # Mapear nombre a ID de pestaña
            tab_mapping = {
                "Socios": "members",
                "Clases": "classes",
                "Membresías": "memberships",
                "Dashboard": "dashboard",
                "WhatsApp": "whatsapp"
            }

            tab_id = tab_mapping.get(tab_name)
            if tab_id and tab_id not in self.loaded_tabs:
                logger.info(f"Tab '{tab_id}' not loaded, loading now...")
                self.load_tab_async(tab_id)

    def cleanup(self) -> None:
        """Limpia recursos antes de cerrar."""
        logger.info("Cleaning up resources")
        self.thread_pool.waitForDone(5000)
        for service in self.services.values():
            try:
                close = getattr(service, "close", None)
                if callable(close):
                    close()
            except Exception:
                logger.exception("Error al cerrar un servicio.")

