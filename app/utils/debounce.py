"""
Debouncing utilities for Qt applications.

Provides mechanisms to delay execution of functions until after
a specified time has elapsed since the last invocation.
"""

from typing import Callable, Optional, Any
from PySide6.QtCore import QTimer, QObject


class Debouncer(QObject):
    """
    Debouncer for delaying function execution.

    Useful for search inputs, window resize events, or any scenario where
    you want to wait for user to stop typing/acting before executing.

    Example:
        >>> def search(query: str):
        ...     print(f"Searching for: {query}")
        >>>
        >>> debouncer = Debouncer(delay=300)
        >>> search_edit.textChanged.connect(
        ...     lambda text: debouncer.debounce(search, text)
        ... )
    """

    def __init__(self, delay: int = 300, parent: Optional[QObject] = None):
        """
        Initialize the debouncer.

        Args:
            delay: Delay in milliseconds (default: 300ms)
            parent: Parent QObject
        """
        super().__init__(parent)
        self._delay = delay
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._callback: Optional[Callable] = None
        self._args: tuple = ()
        self._kwargs: dict = {}

    def debounce(self, callback: Callable, *args: Any, **kwargs: Any) -> None:
        """
        Schedule a function to be called after the delay.

        If called again before delay expires, the previous call is cancelled.

        Args:
            callback: Function to call after delay
            *args: Positional arguments for the callback
            **kwargs: Keyword arguments for the callback
        """
        # Cancel previous timer if running
        if self._timer.isActive():
            self._timer.stop()

        # Store callback and arguments
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

        # Connect timer to execute callback
        try:
            self._timer.timeout.disconnect()
        except RuntimeError:
            # No connections exist
            pass

        self._timer.timeout.connect(self._execute)

        # Start timer
        self._timer.start(self._delay)

    def _execute(self) -> None:
        """Execute the stored callback with its arguments."""
        if self._callback:
            try:
                self._callback(*self._args, **self._kwargs)
            except Exception as e:
                print(f"Error in debounced callback: {e}")

    def cancel(self) -> None:
        """Cancel any pending debounced execution."""
        if self._timer.isActive():
            self._timer.stop()

    def set_delay(self, delay: int) -> None:
        """
        Change the debounce delay.

        Args:
            delay: New delay in milliseconds
        """
        self._delay = delay

    def is_pending(self) -> bool:
        """
        Check if there's a pending execution.

        Returns:
            True if timer is active
        """
        return self._timer.isActive()


class Throttler(QObject):
    """
    Throttler for limiting function execution frequency.

    Unlike debouncing (which delays until user stops), throttling
    ensures a function is called at most once per time interval.

    Example:
        >>> def on_scroll(position: int):
        ...     print(f"Scrolled to: {position}")
        >>>
        >>> throttler = Throttler(interval=100)
        >>> scroll_area.verticalScrollBar().valueChanged.connect(
        ...     lambda pos: throttler.throttle(on_scroll, pos)
        ... )
    """

    def __init__(self, interval: int = 100, parent: Optional[QObject] = None):
        """
        Initialize the throttler.

        Args:
            interval: Minimum interval between calls in milliseconds
            parent: Parent QObject
        """
        super().__init__(parent)
        self._interval = interval
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._can_execute = True
        self._pending_callback: Optional[Callable] = None
        self._pending_args: tuple = ()
        self._pending_kwargs: dict = {}

    def throttle(self, callback: Callable, *args: Any, **kwargs: Any) -> None:
        """
        Execute a function immediately if possible, or queue it.

        Args:
            callback: Function to throttle
            *args: Positional arguments for the callback
            **kwargs: Keyword arguments for the callback
        """
        if self._can_execute:
            # Execute immediately
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in throttled callback: {e}")

            # Block further executions until interval passes
            self._can_execute = False
            self._timer.timeout.connect(self._reset)
            self._timer.start(self._interval)

        else:
            # Store for later execution
            self._pending_callback = callback
            self._pending_args = args
            self._pending_kwargs = kwargs

    def _reset(self) -> None:
        """Reset throttle state and execute pending callback if any."""
        self._can_execute = True

        # Execute pending callback if exists
        if self._pending_callback:
            callback = self._pending_callback
            args = self._pending_args
            kwargs = self._pending_kwargs

            # Clear pending
            self._pending_callback = None
            self._pending_args = ()
            self._pending_kwargs = {}

            # Execute
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in pending throttled callback: {e}")

            # Restart throttle interval
            self._can_execute = False
            self._timer.start(self._interval)

    def set_interval(self, interval: int) -> None:
        """
        Change the throttle interval.

        Args:
            interval: New interval in milliseconds
        """
        self._interval = interval


# Convenience functions
def create_search_debouncer(delay: int = 300) -> Debouncer:
    """
    Create a debouncer optimized for search inputs.

    Args:
        delay: Delay in milliseconds (default: 300ms)

    Returns:
        Debouncer instance

    Example:
        >>> debouncer = create_search_debouncer(delay=500)
        >>> search_edit.textChanged.connect(
        ...     lambda text: debouncer.debounce(perform_search, text)
        ... )
    """
    return Debouncer(delay=delay)


def create_scroll_throttler(interval: int = 100) -> Throttler:
    """
    Create a throttler optimized for scroll events.

    Args:
        interval: Interval in milliseconds (default: 100ms)

    Returns:
        Throttler instance

    Example:
        >>> throttler = create_scroll_throttler(interval=150)
        >>> scroll_bar.valueChanged.connect(
        ...     lambda pos: throttler.throttle(on_scroll, pos)
        ... )
    """
    return Throttler(interval=interval)
