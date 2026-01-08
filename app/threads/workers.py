"""
Workers para carga asíncrona y paralela de componentes.

Cambios v2:
- DataLoader usa AsyncioExecutor en lugar de crear event loops
- Elimina Windows access violations causados por creación concurrente de loops
- Mantiene compatibilidad con código existente
"""

import asyncio
import time
import threading
from typing import Any, Dict, ClassVar, Optional, Dict

from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool

from ..core.logging import get_logger
from .asyncio_executor import get_global_executor

logger = get_logger(__name__)


# ------------------
# Señales base
# ------------------
class WorkerSignals(QObject):
    started = Signal()
    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int)


# ------------------
# BaseWorker
# ------------------
class BaseWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.signals = WorkerSignals()
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        logger.info(f"{self.__class__.__name__}: run() started")
        self.signals.started.emit()
        logger.info(f"{self.__class__.__name__}: started signal emitted")
        try:
            if not self._is_cancelled:
                logger.info(f"{self.__class__.__name__}: calling do_work()")
                result = self.do_work()
                logger.info(f"{self.__class__.__name__}: do_work() returned: {type(result)}")
                if result is not None:
                    logger.info(f"{self.__class__.__name__}: Emitting result signal with payload: {type(result)}")
                    self.signals.result.emit(result)
                    logger.info(f"{self.__class__.__name__}: result signal emitted successfully")
                else:
                    logger.warning(f"{self.__class__.__name__}: do_work() returned None, not emitting result")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            self.signals.error.emit(str(e))
        finally:
            logger.info(f"{self.__class__.__name__}: emitting finished signal")
            self.signals.finished.emit()
            logger.info(f"{self.__class__.__name__}: run() completed")

    def do_work(self) -> Any:
        raise NotImplementedError


# ------------------
# TabLoader
# ------------------
class TabLoader(BaseWorker):
    """Carga perezosa de metadatos para construir una pestaña en el hilo principal."""
    def __init__(self, tab_id: str) -> None:
        super().__init__()
        self.tab_id = tab_id

    def do_work(self) -> Dict[str, Any]:
        logger.info("TabLoader: cargando tab: %s", self.tab_id)
        time.sleep(0.05)  # Simular latencia mínima

        return self._build_tab_descriptor()

    def _build_tab_descriptor(self) -> Dict[str, Any]:
        tab_mapping = {
            "members": ("app.views.tabs.members_tab", "MembersTab"),
            "subscriptions": ("app.views.tabs.subscriptions_tab", "SubscriptionsTab"),
            "classes": ("app.views.tabs.classes_tab", "ClassesTab"),
            "memberships": ("app.views.tabs.memberships_tab", "MembershipsTab"),
            "dashboard": ("app.views.tabs.dashboard_tab", "DashboardTab"),
            "whatsapp": ("app.views.tabs.whatsapp_tab", "WhatsAppTab"),
        }

        if self.tab_id in tab_mapping:
            module_path, class_name = tab_mapping[self.tab_id]
            return {"type": "widget_class", "module": module_path, "class": class_name}

        return {"type": "placeholder", "tab_id": self.tab_id, "message": f"Pestaña '{self.tab_id}' no implementada"}


# ------------------
# DataLoader
# ------------------
class DataLoader(BaseWorker):
    """
    Ejecuta un método de servicio (sync/async) usando AsyncioExecutor.

    En lugar de crear su propio event loop (lo que causaba Windows access violations
    cuando múltiples DataLoaders se ejecutaban concurrentemente), ahora usa el
    AsyncioExecutor global y espera el resultado sincrónicamente.
    """
    def __init__(self, service_method, *args, **kwargs) -> None:
        super().__init__()
        self.service_method = service_method
        self.args = args
        self.kwargs = kwargs

    def do_work(self) -> Any:
        result = self.service_method(*self.args, **self.kwargs)

        # Si es síncrono, retornar directamente
        if not (asyncio.iscoroutine(result) or asyncio.isfuture(result) or hasattr(result, "__await__")):
            return result

        # Si es asíncrono, usar el executor
        return self._run_in_executor(result)

    def _run_in_executor(self, coro_or_awaitable) -> Any:
        """
        Ejecuta una coroutine/awaitable en el AsyncioExecutor y espera el resultado.

        Usa threading.Event para esperar sincrónicamente el resultado,
        permitiendo que DataLoader funcione dentro del patrón BaseWorker.
        """
        executor = get_global_executor()

        if not executor.is_running():
            raise RuntimeError("AsyncioExecutor is not running. Cannot execute async operation.")

        # Convertir a coroutine si es necesario
        if asyncio.iscoroutine(coro_or_awaitable):
            coro = coro_or_awaitable
        else:
            async def _wrap():
                return await coro_or_awaitable
            coro = _wrap()

        # Variables para capturar resultado/error
        result_container = {"value": None, "error": None}
        done_event = threading.Event()

        def on_result(value):
            result_container["value"] = value
            done_event.set()

        def on_error(error):
            result_container["error"] = error
            done_event.set()

        # Enviar al executor
        signals = executor.submit_coroutine(coro)
        signals.result.connect(on_result)
        signals.error.connect(on_error)

        # Esperar resultado (con timeout de 30 segundos)
        if not done_event.wait(timeout=30.0):
            raise TimeoutError("DataLoader operation timed out after 30 seconds")

        # Verificar si hubo error
        if result_container["error"] is not None:
            raise RuntimeError(f"Async operation failed: {result_container['error']}")

        return result_container["value"]


# ------------------
# ThreadPoolManager
# ------------------
class ThreadPoolManager:
    """Gestor centralizado de thread pools nombrados (con límites prudentes)."""

    _instance: ClassVar[Optional["ThreadPoolManager"]] = None

    # Atributos de instancia (anotados a nivel de clase para Pylance/mypy)
    default_pool: QThreadPool
    pools: Dict[str, QThreadPool]

    def __new__(cls) -> "ThreadPoolManager":
        if cls._instance is None:
            self = super().__new__(cls)
            # Inicialización de atributos de instancia
            self.default_pool = QThreadPool.globalInstance()
            self.default_pool.setMaxThreadCount(4)
            self.pools = {}
            cls._instance = self
        return cls._instance

    def get_pool(self, name: str = "default") -> QThreadPool:
        if name == "default":
            return self.default_pool

        pool = self.pools.get(name)
        if pool is None:
            pool = QThreadPool()
            pool.setMaxThreadCount(2)
            self.pools[name] = pool
        return pool

    def submit(self, worker: QRunnable, pool_name: str = "default") -> None:
        pool = self.get_pool(pool_name)
        pool.start(worker)

    def wait_all(self, timeout_ms: int = 5000) -> None:
        self.default_pool.waitForDone(timeout_ms)
        for pool in self.pools.values():
            pool.waitForDone(timeout_ms)

