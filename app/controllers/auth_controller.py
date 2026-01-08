"""
Controlador de autenticación para coordinar vista y servicios.

Cambios v2:
- LoginThread y LogoutThread usan AsyncioExecutor en lugar de crear event loops
- Elimina Windows access violations causados por creación concurrente de loops
"""
import asyncio
import threading
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtCore import QObject, Signal, QThread, Slot
from ..core.logging import get_logger
from ..core.di import container
from ..threads.asyncio_executor import get_global_executor

logger = get_logger(__name__)

class AuthController(QObject):
    """Controlador para el proceso de autenticación."""
    
    # Señales
    login_success = Signal(dict)  # user_data
    login_failed = Signal(str)  # error_message
    logout_success = Signal()
    
    def __init__(self):
        super().__init__()
        self.auth_service = container.get('auth_service')
        self.login_view = None
        self.main_window = None
        self._login_thread = None
    
    def set_views(self, login_view, main_window):
        """Establece las vistas asociadas."""
        self.login_view = login_view
        self.main_window = main_window
        
        # Conectar señales
        if self.login_view:
            self.login_view.login_requested.connect(self.handle_login)
        
        if self.main_window:
            self.main_window.logout_requested.connect(self.handle_logout)
    
    @Slot(str, str, bool)
    def handle_login(self, email: str, password: str, remember_me: bool = False):
        """Maneja la solicitud de login."""
        # Crear thread para login asíncrono
        self._login_thread = LoginThread(self.auth_service, email, password, remember_me)
        self._login_thread.success.connect(self.on_login_success)
        self._login_thread.error.connect(self.on_login_error)
        self._login_thread.start()
    
    @Slot(dict)
    def on_login_success(self, user_data: dict):
        """Maneja el login exitoso."""
        logger.info(f"Login successful for user: {user_data.get('username')}")

        if self.login_view:
            self.login_view.set_loading(False)
            self.login_view.hide()

        # Emitir señal de éxito
        self.login_success.emit(user_data)
    
    @Slot(str)
    def on_login_error(self, error_message: str):
        """Maneja el error de login."""
        logger.error(f"Login failed: {error_message}")

        if self.login_view:
            self.login_view.set_loading(False)
            self.login_view.show_error(error_message)

        # Emitir señal de error
        self.login_failed.emit(error_message)
    
    @Slot()
    def handle_logout(self):
        """Maneja la solicitud de logout."""
        # Crear thread para logout asíncrono
        logout_thread = LogoutThread(self.auth_service)
        logout_thread.finished.connect(self.on_logout_complete)
        logout_thread.start()
    
    @Slot()
    def on_logout_complete(self):
        """Maneja el logout completo."""
        logger.info("User logged out")

        if self.main_window:
            self.main_window.hide()

        if self.login_view:
            self.login_view.clear_fields()
            self.login_view.show()

        # Emitir señal de logout
        self.logout_success.emit()
    
    def check_existing_session(self) -> bool:
        """Verifica si hay una sesión existente."""
        return self.auth_service.is_authenticated()
    
    def get_current_user(self) -> Optional[dict]:
        """Obtiene el usuario actual."""
        return self.auth_service.get_current_user()


class LoginThread(QThread):
    """
    Thread para realizar login asíncrono usando AsyncioExecutor.

    En lugar de crear su propio event loop, usa el AsyncioExecutor global
    y espera el resultado sincrónicamente usando threading.Event.
    """

    success = Signal(dict)
    error = Signal(str)

    def __init__(self, auth_service, email: str, password: str, remember_me: bool = False):
        super().__init__()
        self.auth_service = auth_service
        self.email = email
        self.password = password
        self.remember_me = remember_me

    def run(self):
        """Ejecuta el login usando AsyncioExecutor."""
        try:
            executor = get_global_executor()

            if not executor.is_running():
                raise RuntimeError("AsyncioExecutor is not running")

            # Contenedor para resultado
            result_container = {"success": None, "message": None, "error": None}
            done_event = threading.Event()

            def on_result(result):
                success, message = result
                result_container["success"] = success
                result_container["message"] = message
                done_event.set()

            def on_error(error_msg):
                result_container["error"] = error_msg
                done_event.set()

            # Enviar operación al executor
            signals = executor.submit_coroutine(
                self.auth_service.login(self.email, self.password, self.remember_me)
            )
            # Use DirectConnection to avoid deadlock since this thread is blocked waiting
            signals.result.connect(on_result, Qt.ConnectionType.DirectConnection)
            signals.error.connect(on_error, Qt.ConnectionType.DirectConnection)

            # Esperar resultado
            if not done_event.wait(timeout=30.0):
                self.error.emit("Login timeout")
                return

            # Verificar resultado
            if result_container["error"] is not None:
                self.error.emit(result_container["error"])
            elif result_container["success"]:
                user_data = self.auth_service.get_current_user()
                self.success.emit(user_data)
            else:
                self.error.emit(result_container["message"] or "Login failed")

        except Exception as e:
            logger.exception("LoginThread error: %s", e)
            self.error.emit(str(e))


class LogoutThread(QThread):
    """
    Thread para realizar logout asíncrono usando AsyncioExecutor.

    En lugar de crear su propio event loop, usa el AsyncioExecutor global
    y espera el resultado sincrónicamente usando threading.Event.
    """

    def __init__(self, auth_service):
        super().__init__()
        self.auth_service = auth_service

    def run(self):
        """Ejecuta el logout usando AsyncioExecutor."""
        try:
            executor = get_global_executor()

            if not executor.is_running():
                logger.warning("AsyncioExecutor is not running, logout may be incomplete")
                return

            # Contenedor para resultado
            done_event = threading.Event()
            error_container = {"error": None}

            def on_result(_):
                done_event.set()

            def on_error(error_msg):
                error_container["error"] = error_msg
                done_event.set()

            # Enviar operación al executor
            signals = executor.submit_coroutine(self.auth_service.logout())
            # Use DirectConnection to avoid deadlock since this thread is blocked waiting
            signals.result.connect(on_result, Qt.ConnectionType.DirectConnection)
            signals.error.connect(on_error, Qt.ConnectionType.DirectConnection)

            # Esperar resultado
            if not done_event.wait(timeout=10.0):
                logger.error("Logout timeout")
                return

            # Verificar si hubo error
            if error_container["error"] is not None:
                logger.error(f"Logout error: {error_container['error']}")

        except Exception as e:
            logger.exception("LogoutThread error: %s", e)
