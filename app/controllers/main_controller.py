"""
Controlador principal para coordinar toda la aplicacion.
"""
from importlib import import_module
from typing import Any, Dict, Optional, Protocol, Set, cast, runtime_checkable

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..core.logging import get_logger
from ..threads.asyncio_executor import get_global_executor
from ..threads.workers import TabLoader
from .auth_controller import AuthController

logger = get_logger(__name__)


@runtime_checkable
class LoginViewLike(Protocol):
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def set_default_credentials(self, email: str) -> None: ...


@runtime_checkable
class MainWindowLike(Protocol):
    tab_changed: Any
    refresh_requested: Any
    tab_widget: Any

    def show(self) -> None: ...
    def hide(self) -> None: ...
    def set_current_user(self, user: Dict[str, Any]) -> None: ...
    def load_tab_content(self, tab_id: str, widget: QWidget) -> None: ...
    def show_error(self, title: str, msg: str) -> None: ...


class MainController(QObject):
    """Controlador principal de la aplicacion."""

    app_ready = Signal()
    app_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.auth_controller = AuthController()

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

        self.tab_controllers: Dict[str, Any] = {}
        self.services: Dict[str, Any] = {}
        self.loaded_tabs: Set[str] = set()
        self.loading_tabs: Set[str] = set()
        self.current_user: Optional[Dict[str, Any]] = None

        self._active_workers: Dict[str, Any] = {}
        self._startup_restore_signals: Optional[QObject] = None
        self._app_ready_emitted = False

        self.login_view: Optional[LoginViewLike] = None
        self.main_window: Optional[MainWindowLike] = None

        logger.info("Main controller initialized")

    def initialize(self, login_view: QObject, main_window: QObject) -> None:
        """Inicializa el controlador con las vistas."""
        self.login_view = cast(LoginViewLike, login_view)
        self.main_window = cast(MainWindowLike, main_window)

        self.auth_controller.set_views(login_view, main_window)
        self.auth_controller.login_success.connect(self.on_login_success)
        self.auth_controller.logout_success.connect(self.on_logout_success)

        if self.main_window:
            self.main_window.tab_changed.connect(self.on_tab_changed)
            self.main_window.refresh_requested.connect(
                lambda tab_id: self.load_tab_async(tab_id, force=True)
            )

    def start(self) -> None:
        """Inicia la aplicacion."""
        try:
            if self.auth_controller.check_existing_session():
                user_data = self.auth_controller.get_current_user()
                if not user_data:
                    raise RuntimeError("No se pudo obtener el usuario de la sesion actual.")
                self.on_login_success(user_data)
                self._emit_app_ready()
                return

            self.show_login()
            self._emit_app_ready()
            self.try_restore_session_async()

        except Exception as e:
            logger.exception(f"Startup error: {e}")
            self.app_error.emit(str(e))

    def _emit_app_ready(self) -> None:
        """Emite la senal de app lista una sola vez."""
        if not self._app_ready_emitted:
            self._app_ready_emitted = True
            self.app_ready.emit()

    def try_restore_session_async(self) -> bool:
        """
        Intenta restaurar la sesion desde almacenamiento persistente sin bloquear la UI.

        Returns:
            bool: True si se inicio el proceso de restauracion, False en caso contrario.
        """
        try:
            from ..auth.persistent_storage import load_refresh_token
            from ..graphql.client import GraphQLClient

            stored_data = load_refresh_token()
            if not stored_data:
                logger.debug("No stored session found")
                return False

            username, refresh_token = stored_data
            logger.info("Attempting to restore session for user: %s", username)
            GraphQLClient.restore_refresh_token(refresh_token)

            auth_service = self.auth_controller.auth_service
            executor = get_global_executor()
            if not executor.is_running():
                logger.error("AsyncioExecutor is not running, cannot restore session")
                return False

            logger.debug("Submitting refresh_token coroutine to executor")
            signals = executor.submit_coroutine(auth_service.refresh_token())
            self._startup_restore_signals = signals
            signals.result.connect(
                lambda success, username=username: self._on_session_restore_result(username, success)
            )
            signals.error.connect(self._on_session_restore_error)
            signals.finished.connect(self._clear_startup_restore_signals)
            logger.info("Session restore submitted asynchronously for user: %s", username)
            return True

        except Exception as e:
            logger.error(f"Error restoring session: {e}")
            try:
                from ..auth.persistent_storage import clear_refresh_token

                clear_refresh_token()
            except Exception:
                pass

        return False

    @Slot(object)
    def _on_session_restore_result(self, username: str, success: object) -> None:
        """Procesa el resultado de restaurar sesion sin bloquear el hilo principal."""
        try:
            if bool(success) and self.auth_controller.check_existing_session():
                user_data = self.auth_controller.get_current_user()
                if user_data:
                    logger.info("Session restored successfully for user: %s", username)
                    self.on_login_success(user_data)
                    return
                logger.warning("Token refresh succeeded but no user data available")

            logger.warning("Failed to refresh token, clearing persistent storage")
            from ..auth.persistent_storage import clear_refresh_token

            clear_refresh_token()
        except Exception as e:
            logger.error(f"Error handling restored session result: {e}")
            self.app_error.emit(str(e))

    @Slot(str)
    def _on_session_restore_error(self, error_msg: str) -> None:
        """Maneja el error al restaurar una sesion persistente."""
        logger.error(f"Error refreshing token: {error_msg}")
        try:
            from ..auth.persistent_storage import clear_refresh_token

            clear_refresh_token()
        except Exception:
            logger.debug("No se pudo limpiar la sesion persistente tras error de refresh")

    @Slot()
    def _clear_startup_restore_signals(self) -> None:
        """Libera la referencia fuerte al restore al finalizar."""
        self._startup_restore_signals = None

    def show_login(self) -> None:
        """Muestra la pantalla de login."""
        if self.main_window:
            self.main_window.hide()

        if self.login_view:
            self.login_view.show()

            try:
                from ..core.config import Config

                if getattr(Config, "is_development", lambda: False)():
                    self.login_view.set_default_credentials("aleramos")
            except Exception:
                logger.debug("No se pudo establecer credenciales por defecto (modo dev).")

    @Slot(dict)
    def on_login_success(self, user_data: Dict[str, Any]) -> None:
        """Maneja el login exitoso."""
        logger.info("User logged in: %s", user_data.get("username"))
        self.current_user = user_data

        if self.login_view:
            self.login_view.hide()

        if self.main_window:
            self.main_window.set_current_user(user_data)
            self.main_window.show()
            self.load_initial_tabs(user_data.get("role"))

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
        self.load_tab_async("members")

    def load_tab_async(self, tab_id: str, force: bool = False) -> None:
        """Carga una pestana de forma asincrona."""
        if force:
            self.loaded_tabs.discard(tab_id)

        if not force and tab_id in self.loaded_tabs:
            logger.debug("Tab '%s' ya esta cargada. Omitiendo.", tab_id)
            return

        if tab_id in self.loading_tabs:
            logger.debug("Tab '%s' ya se esta cargando. Omitiendo.", tab_id)
            return

        self.loading_tabs.add(tab_id)

        worker = TabLoader(tab_id)
        logger.info("TabLoader created for tab: %s", tab_id)

        worker_key = f"tab_loader_{tab_id}"
        self._active_workers[worker_key] = worker
        logger.info("Worker reference stored with key: %s", worker_key)

        def make_loaded_handler(tab_id_local: str):
            def handler(payload: Any) -> None:
                logger.info(
                    "Handler called for tab %s with payload type: %s",
                    tab_id_local,
                    type(payload),
                )
                self.on_tab_loaded(tab_id_local, payload)

            return handler

        def make_error_handler(tab_id_local: str):
            def handler(err: str) -> None:
                logger.info("Error handler called for tab %s: %s", tab_id_local, err)
                self.on_tab_error(tab_id_local, err)

            return handler

        def make_finished_handler(worker_key_local: str):
            def handler() -> None:
                logger.info("Finished handler called, removing worker: %s", worker_key_local)
                self._active_workers.pop(worker_key_local, None)

            return handler

        worker.signals.result.connect(make_loaded_handler(tab_id))
        worker.signals.error.connect(make_error_handler(tab_id))
        worker.signals.finished.connect(make_finished_handler(worker_key))
        logger.info("Signals connected for tab: %s", tab_id)

        self.thread_pool.start(worker)
        logger.info("Loading tab: %s", tab_id)

    def on_tab_loaded(self, tab_id: str, payload: Any) -> None:
        """Maneja cuando una pestana termina de cargarse."""
        try:
            logger.info("on_tab_loaded called for tab: %s", tab_id)

            if not payload:
                logger.error("No payload received for tab %s", tab_id)
                return

            widget = self._build_tab_widget(tab_id, payload)
            if self.main_window:
                self.main_window.load_tab_content(tab_id, widget)

            controller = getattr(widget, "controller", None)
            if controller is not None:
                self.tab_controllers[tab_id] = controller

            self.loaded_tabs.add(tab_id)
            logger.info("Tab '%s' successfully added to loaded_tabs", tab_id)
        except Exception as e:
            logger.exception(f"Error loading tab {tab_id}: {e}")
        finally:
            self.loading_tabs.discard(tab_id)

    def _build_tab_widget(self, tab_id: str, payload: Any) -> QWidget:
        """Construye la pestana en el hilo principal a partir del payload del worker."""
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
                    raise TypeError(f"La factory de '{tab_id}' no devolvio un QWidget.")

            if callable(payload):
                res = payload()
                if isinstance(res, QWidget):
                    return res
                raise TypeError(f"El callable de '{tab_id}' no devolvio un QWidget.")

            if isinstance(payload, QWidget):
                return payload

        except Exception as exc:
            logger.exception(f"Failed to build widget for tab {tab_id}: {exc}")

        return self._create_placeholder_tab(None, tab_id)

    def _create_placeholder_tab(self, message: Optional[str], tab_id: str) -> QWidget:
        """Crea una pestana placeholder cuando la real no puede construirse."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)
        layout.addStretch()

        label = QLabel(message or f"Pestana '{tab_id}' no disponible")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        layout.addStretch()
        return widget

    def on_tab_error(self, tab_id: str, error: str) -> None:
        """Maneja el error al cargar una pestana."""
        self.loading_tabs.discard(tab_id)
        logger.error("Error loading tab %s: %s", tab_id, error)

        if self.main_window:
            self.main_window.show_error("Error", f"No se pudo cargar {tab_id}: {error}")

    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        """Maneja el cambio de pestana."""
        logger.debug("Tab changed to index: %s", index)

        if self.main_window and index >= 0:
            tab_name = self.main_window.tab_widget.tabText(index)
            tab_mapping = {
                "Socios": "members",
                "Clases": "classes",
                "Membresias": "memberships",
                "Dashboard": "dashboard",
                "WhatsApp": "whatsapp",
                "Chats": "whatsapp_chat",
            }

            tab_id = tab_mapping.get(tab_name)
            if tab_id and tab_id not in self.loaded_tabs:
                logger.info("Tab '%s' not loaded, loading now...", tab_id)
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
