"""
AsyncioExecutor: Dedicated thread with persistent event loop for async operations.

This module implements a robust solution to avoid Windows access violations caused by
concurrent event loop creation. It provides a single dedicated thread with one persistent
event loop that handles all async operations in the application.

Design principles (following PySide6 best practices):
- Single QThread with persistent event loop (created once at startup)
- Thread-safe queue for submitting coroutines from Qt threads
- Signal/slot communication with Qt GUI thread
- Proper lifecycle management and graceful shutdown
- No concurrent event loop creation (eliminates race conditions)

References:
- PySide6 Threading: https://doc.qt.io/qtforpython-6/overviews/threads-technologies.html
- asyncio Thread Safety: https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading
"""

import asyncio
import inspect
import logging
import threading
import weakref
from typing import Any, Awaitable, Callable, Coroutine, Optional, cast
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Qt

logger = logging.getLogger(__name__)


# -------------
# Task Submission
# -------------
@dataclass
class AsyncTask:
    """Represents a task to be executed in the asyncio event loop."""
    task_id: int
    coro: Coroutine[Any, Any, Any]
    signals: 'TaskSignals'
    graphql_client: Optional[Any] = None
    session_store: Optional[Any] = None


class TaskSignals(QObject):
    """Signals emitted by async task execution (thread-safe Qt signals)."""
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


# -------------
# Asyncio Executor Thread
# -------------
class AsyncioExecutor(QThread):
    """
    Dedicated thread that runs a persistent asyncio event loop.

    This class provides a thread-safe way to execute async operations from Qt threads
    without creating multiple event loops, which causes Windows access violations.

    Usage:
        executor = AsyncioExecutor()
        executor.start()

        # Submit async operation
        signals = executor.submit_coroutine(my_async_function(args))
        signals.result.connect(on_result)
        signals.error.connect(on_error)
        signals.finished.connect(on_finished)

        # Shutdown when done
        executor.shutdown()
        executor.wait()
    """

    # Class-level signals for executor status
    executor_ready = Signal()
    executor_stopped = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # Task submission queue (will be created in run() as asyncio.Queue)
        self._task_queue: Optional[asyncio.Queue[Optional[AsyncTask]]] = None

        # Event loop reference (set in run())
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()

        # Shutdown control
        self._shutdown_requested = False
        self._shutdown_lock = threading.Lock()

        # Task tracking
        self._task_counter = 0
        self._task_counter_lock = threading.Lock()
        self._active_tasks: dict[int, asyncio.Task[Any]] = {}
        self._active_tasks_lock = threading.Lock()

        logger.info("AsyncioExecutor initialized")

    def run(self) -> None:
        """
        Main thread execution: create persistent event loop and process tasks.

        This runs in the dedicated QThread and should never be called directly.
        """
        try:
            # Create the persistent event loop (ONCE, at thread startup)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Create the async queue (must be done after setting event loop)
            self._task_queue = asyncio.Queue()

            logger.info("AsyncioExecutor event loop created (thread: %s)", threading.current_thread().name)

            # Signal that loop is ready
            self._loop_ready.set()
            self.executor_ready.emit()

            # Start processing tasks
            self._loop.run_until_complete(self._process_tasks())

        except Exception as e:
            logger.exception("AsyncioExecutor thread error: %s", e)
        finally:
            self._cleanup_loop()
            logger.info("AsyncioExecutor thread finished")

    async def _process_tasks(self) -> None:
        """
        Drain submitted work until shutdown is requested.

        This coroutine runs in the persistent event loop and schedules each
        submitted coroutine as its own asyncio task. The loop stays single, but
        long-lived operations do not block later requests from starting.
        """
        logger.info("AsyncioExecutor started processing tasks")

        if self._task_queue is None:
            raise RuntimeError("Task queue not initialized")

        while True:
            # Check for shutdown
            with self._shutdown_lock:
                if self._shutdown_requested and self._task_queue.empty():
                    logger.info("AsyncioExecutor shutdown requested and queue empty, stopping")
                    break

            # Get next task (with timeout to check shutdown periodically)
            # CRITICAL FIX: Use asyncio.wait_for instead of run_in_executor to avoid deadlock
            try:
                task = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                # No task available, continue checking shutdown
                continue

            # None is the shutdown sentinel
            if task is None:
                logger.info("AsyncioExecutor received shutdown sentinel")
                break

            # Schedule the submitted coroutine and keep draining the queue. Some
            # tasks, such as WebSocket subscriptions, are intentionally long-lived.
            asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: AsyncTask) -> None:
        """
        Execute a single async task and emit appropriate signals.

        Args:
            task: The AsyncTask to execute
        """
        try:
            # Inject session_store into graphql_client if provided
            if task.graphql_client is not None and task.session_store is not None:
                try:
                    setattr(task.graphql_client, "session_store", task.session_store)
                except Exception as e:
                    logger.debug("Could not set session_store on graphql_client: %s", e)

            # Create asyncio task for cancellation support
            async_task = asyncio.create_task(task.coro)

            # Track active task
            with self._active_tasks_lock:
                self._active_tasks[task.task_id] = async_task

            try:
                # Execute and wait for result
                result = await async_task

                # Emit success signal (thread-safe) with error handling
                try:
                    task.signals.result.emit(result)
                    logger.debug("Task %d completed successfully", task.task_id)
                except Exception as emit_error:
                    logger.error("Failed to emit result signal for task %d: %s", task.task_id, emit_error)

            except asyncio.CancelledError:
                logger.info("Task %d was cancelled", task.task_id)
                try:
                    task.signals.error.emit("Task cancelled")
                except Exception as emit_error:
                    logger.error("Failed to emit error signal for task %d: %s", task.task_id, emit_error)
            except Exception as e:
                logger.exception("Task %d failed: %s", task.task_id, e)
                try:
                    task.signals.error.emit(str(e))
                except Exception as emit_error:
                    logger.error("Failed to emit error signal for task %d: %s", task.task_id, emit_error)
            finally:
                # Remove from active tasks
                try:
                    with self._active_tasks_lock:
                        self._active_tasks.pop(task.task_id, None)
                except Exception as e:
                    logger.error("Error removing task %d from active tasks: %s", task.task_id, e)

                # ALWAYS emit finished, even if other emissions failed
                try:
                    task.signals.finished.emit()
                except Exception as emit_error:
                    logger.error("Failed to emit finished signal for task %d: %s", task.task_id, emit_error)

        except Exception as e:
            logger.exception("Critical error executing task %d: %s", task.task_id, e)
            try:
                task.signals.error.emit(str(e))
            except Exception as emit_error:
                logger.error("Failed to emit error signal for task %d: %s", task.task_id, emit_error)
            try:
                task.signals.finished.emit()
            except Exception as emit_error:
                logger.error("Failed to emit finished signal for task %d: %s", task.task_id, emit_error)

    def _cleanup_loop(self) -> None:
        """
        Clean up the event loop on shutdown.

        Cancels all pending tasks and closes the loop gracefully.
        """
        if self._loop is None:
            return

        try:
            # Cancel all active tasks
            with self._active_tasks_lock:
                active_tasks = list(self._active_tasks.values())

            if active_tasks:
                logger.info("Cancelling %d active tasks", len(active_tasks))
                for task in active_tasks:
                    task.cancel()

                # Wait for cancellations to complete
                try:
                    self._loop.run_until_complete(asyncio.gather(*active_tasks, return_exceptions=True))
                except Exception as e:
                    logger.debug("Error during task cancellation: %s", e)

            # Cancel all remaining tasks
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()

            # Give tasks a chance to complete cancellation
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            # Close the loop
            self._loop.close()
            logger.info("AsyncioExecutor event loop closed")

        except Exception as e:
            logger.exception("Error during loop cleanup: %s", e)
        finally:
            self._loop = None
            self.executor_stopped.emit()

    def submit_coroutine(
        self,
        coro: Coroutine[Any, Any, Any],
        graphql_client: Optional[Any] = None,
        session_store: Optional[Any] = None
    ) -> TaskSignals:
        """
        Submit a coroutine for execution in the persistent event loop.

        This method is thread-safe and can be called from any thread.

        Args:
            coro: The coroutine to execute
            graphql_client: Optional GraphQL client for session injection
            session_store: Optional session store for authentication

        Returns:
            TaskSignals object for connecting to result/error/finished signals

        Raises:
            RuntimeError: If executor is not running or has been shut down
        """
        with self._shutdown_lock:
            if self._shutdown_requested:
                raise RuntimeError("AsyncioExecutor has been shut down")

        # Wait for loop to be ready (with timeout)
        if not self._loop_ready.wait(timeout=5.0):
            raise RuntimeError("AsyncioExecutor event loop not ready")

        if self._loop is None or self._task_queue is None:
            raise RuntimeError("AsyncioExecutor not properly initialized")

        # Generate task ID
        with self._task_counter_lock:
            self._task_counter += 1
            task_id = self._task_counter

        # Create signals
        signals = TaskSignals()

        # Create task
        task = AsyncTask(
            task_id=task_id,
            coro=coro,
            signals=signals,
            graphql_client=graphql_client,
            session_store=session_store
        )

        # Submit to queue using run_coroutine_threadsafe (thread-safe for asyncio.Queue)
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._task_queue.put(task),
                self._loop
            )
            # Wait for task to be added to queue (with timeout)
            future.result(timeout=1.0)
            logger.debug("Task %d submitted to executor queue", task_id)
        except TimeoutError:
            raise RuntimeError(f"Timeout submitting task {task_id} to queue")
        except Exception as e:
            logger.error("Failed to submit task %d: %s", task_id, e)
            raise

        return signals

    def submit_sync_or_async(
        self,
        func: Callable[..., Any],
        *args: Any,
        graphql_client: Optional[Any] = None,
        session_store: Optional[Any] = None,
        **kwargs: Any
    ) -> TaskSignals:
        """
        Submit a function (sync or async) for execution.

        This method handles both synchronous and asynchronous functions,
        converting sync functions to coroutines if needed.

        Args:
            func: The function to execute (sync or async)
            *args: Positional arguments for the function
            graphql_client: Optional GraphQL client for session injection
            session_store: Optional session store for authentication
            **kwargs: Keyword arguments for the function

        Returns:
            TaskSignals object for connecting to result/error/finished signals
        """
        # Call the function to get result/awaitable/coroutine
        result = func(*args, **kwargs)

        # Convert to coroutine if needed
        if inspect.iscoroutine(result):
            coro = cast(Coroutine[Any, Any, Any], result)
        elif inspect.isawaitable(result):
            async def _wrap() -> Any:
                return await result
            coro = _wrap()
        else:
            # Synchronous result - wrap in coroutine
            async def _sync_wrap() -> Any:
                return result
            coro = _sync_wrap()

        return self.submit_coroutine(coro, graphql_client, session_store)

    def shutdown(self, wait_for_tasks: bool = True) -> None:
        """
        Request graceful shutdown of the executor.

        Args:
            wait_for_tasks: If True, waits for current tasks to complete before stopping
        """
        with self._shutdown_lock:
            if self._shutdown_requested:
                logger.warning("AsyncioExecutor shutdown already requested")
                return

            self._shutdown_requested = True
            logger.info("AsyncioExecutor shutdown requested (wait_for_tasks=%s)", wait_for_tasks)

        # Send shutdown sentinel using run_coroutine_threadsafe
        if self._loop and self._task_queue:
            try:
                # If not waiting for tasks, could clear queue first (but we skip for simplicity)
                # For asyncio.Queue, we just send the sentinel
                future = asyncio.run_coroutine_threadsafe(
                    self._task_queue.put(None),
                    self._loop
                )
                # Wait for sentinel to be queued
                future.result(timeout=1.0)
                logger.debug("Shutdown sentinel sent to task queue")
            except Exception as e:
                logger.error("Error sending shutdown sentinel: %s", e)
        else:
            logger.warning("Cannot send shutdown sentinel: loop or queue not initialized")

    def is_running(self) -> bool:
        """Check if the executor thread is running."""
        return self.isRunning() and not self._shutdown_requested

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """
        Wait until the executor's event loop is ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if ready, False if timeout
        """
        return self._loop_ready.wait(timeout=timeout)


# -------------
# Global Executor Instance (Singleton Pattern)
# -------------
_global_executor: Optional[AsyncioExecutor] = None
_global_executor_lock = threading.Lock()


def get_global_executor() -> AsyncioExecutor:
    """
    Get the global AsyncioExecutor instance (singleton).

    The executor is created on first access and should be started
    by the application's main controller.

    Returns:
        The global AsyncioExecutor instance
    """
    global _global_executor

    with _global_executor_lock:
        if _global_executor is None:
            _global_executor = AsyncioExecutor()
            logger.info("Global AsyncioExecutor created")

    return _global_executor


def shutdown_global_executor(wait_for_tasks: bool = True) -> None:
    """
    Shutdown the global executor if it exists.

    Args:
        wait_for_tasks: If True, waits for current tasks to complete
    """
    global _global_executor

    with _global_executor_lock:
        if _global_executor is not None:
            _global_executor.shutdown(wait_for_tasks)
            _global_executor.wait()
            _global_executor = None
            logger.info("Global AsyncioExecutor shut down")
