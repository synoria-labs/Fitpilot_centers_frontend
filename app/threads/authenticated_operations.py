"""
Authenticated operations: ejecución de métodos (sync/async) con contexto de autenticación
usando un AsyncioExecutor dedicado.

Cambios clave (v2 - usando AsyncioExecutor):
- Usa un thread dedicado con event loop persistente (AsyncioExecutor)
- Elimina creación concurrente de event loops (evita Windows access violations)
- Mantiene la misma interfaz de señales para compatibilidad con código existente
- Sigue mejores prácticas de PySide6 para threading
"""

import inspect
import itertools
import logging
import os
from typing import Any, Awaitable, Callable, Coroutine, Optional, cast

from PySide6.QtCore import QObject, Signal, Qt

from .asyncio_executor import get_global_executor

# Logger configurable por env
logger = logging.getLogger(__name__)
if not logger.handlers:
    _level = os.getenv("AUTH_OPS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, _level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

# Nota: aquí vivía un QSemaphore "limitador de workers" (MAX_CONCURRENT_WORKERS)
# que NUNCA se adquiría — no limitaba nada. Se eliminó en lugar de "arreglarlo":
# el executor corre operaciones long-lived (suscripciones WebSocket) que
# retendrían un slot indefinidamente y matarían de hambre al resto. La
# concurrencia real la gobierna el event loop único del AsyncioExecutor.


# --------------------------------
# Utilidades de logging compacto
# --------------------------------
def _truncate(text: str, max_len: int = 120) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _safe_item_preview(obj: Any, max_len: int = 120) -> str:
    try:
        r = repr(obj)
    except Exception as e:  # pragma: no cover
        r = f"<repr-error {e!r}>"
    return _truncate(r, max_len=max_len)


def _summarize_result(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        try:
            n = len(value)  # type: ignore[assignment]
        except Exception:
            n = -1
        head = list(itertools.islice(iter(value), 3))
        preview = ", ".join(_safe_item_preview(x) for x in head)
        suffix = ", ..." if (n == -1 or n > 3) else ""
        return f"{type(value)} with {n if n != -1 else 'unknown'} items | preview: [{preview}{suffix}]"
    return f"{type(value)} | value: {_truncate(repr(value))}"


# -------------
# Señales
# -------------
class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


# -------------
# Helpers async
# -------------
def _await_any(awaitable: Awaitable[Any]) -> Coroutine[Any, Any, Any]:
    """Envuelve cualquier awaitable (Task/Future/etc.) en una coroutine real."""
    async def _runner() -> Any:
        return await awaitable
    return _runner()


# -------------
# Orquestador
# -------------
class AuthenticatedOperation(QObject):
    """
    Orquesta la ejecución de un método de servicio usando AsyncioExecutor.

    Esta clase mantiene la misma interfaz de señales que antes, pero ahora
    usa el AsyncioExecutor global en lugar de crear event loops en workers.
    Esto elimina los Windows access violations causados por creación concurrente
    de event loops.
    """

    success = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        service: Any,
        method_name: str,
        parent: Optional[QObject] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.method_name = method_name
        self.args = args
        self.kwargs = kwargs
        self._task_signals: Optional[Any] = None  # Keep reference to prevent GC

    def _on_result(self, value: Any) -> None:
        """Slot para resultado exitoso."""
        logger.debug("AuthenticatedOperation result: %s", _summarize_result(value))
        self.success.emit(value)

    def _on_error(self, msg: str) -> None:
        """Slot para errores."""
        logger.error("AuthenticatedOperation error: %s", _truncate(msg))
        self.error.emit(msg)

    def _on_finished(self) -> None:
        """Slot para finalización."""
        self.finished.emit()

    def execute(self) -> None:
        """
        Ejecuta la operación usando el AsyncioExecutor global.

        En lugar de crear un worker con su propio event loop, ahora
        simplemente enviamos la coroutine al executor dedicado.
        """
        try:
            # Obtener el executor global
            executor = get_global_executor()

            if not executor.is_running():
                raise RuntimeError("AsyncioExecutor is not running. Did you forget to start it?")

            # Obtener referencias necesarias
            graphql_client = getattr(self.service, "client", None)
            session_store = getattr(graphql_client, "session_store", None) if graphql_client else None

            # Obtener el método
            method = getattr(self.service, self.method_name)

            # Enviar al executor
            self._task_signals = executor.submit_sync_or_async(
                method,
                *self.args,
                graphql_client=graphql_client,
                session_store=session_store,
                **self.kwargs
            )

            # Conectar señales (con QueuedConnection para thread-safety)
            conn = Qt.ConnectionType.QueuedConnection
            self._task_signals.result.connect(self._on_result, conn)
            self._task_signals.error.connect(self._on_error, conn)
            self._task_signals.finished.connect(self._on_finished, conn)

            logger.debug("AuthenticatedOperation submitted to AsyncioExecutor: %s.%s",
                        self.service.__class__.__name__, self.method_name)

        except Exception as e:
            logger.exception("AuthenticatedOperation.execute failed: %s", e)
            self.error.emit(str(e))
            self.finished.emit()


def start_authenticated_operation(
    service: Any,
    method_name: str,
    *,
    parent: Optional[QObject] = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    on_finished: Optional[Callable[[], None]] = None,
    **kwargs: Any,
) -> AuthenticatedOperation:
    """Create and execute an AuthenticatedOperation with optional callbacks."""
    operation = AuthenticatedOperation(
        service=service,
        method_name=method_name,
        parent=parent,
        **kwargs,
    )
    if on_success:
        operation.success.connect(on_success)
    if on_error:
        operation.error.connect(on_error)
    if on_finished:
        operation.finished.connect(on_finished)
    operation.execute()
    return operation
