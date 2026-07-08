"""Async media downloader with an on-disk cache.

Single shared component used by the chat media bubbles and the template
preview. Downloads run on the global AsyncioExecutor event loop (never the GUI
thread); results land in ``Config.CACHE_DIR/media`` keyed by a hash of the URL,
so repeated views of the same attachment hit the disk cache.

Usage (from the GUI thread):

    handle = get_media_loader().fetch(url)
    handle.finished.connect(lambda path: ...)   # local file path (str)
    handle.failed.connect(lambda error: ...)    # user-displayable error (str)

Signal delivery is always asynchronous (also on cache hits) so callers can
connect right after calling ``fetch``. Concurrent fetches of the same URL are
deduplicated into a single download.
"""
import hashlib
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from PySide6.QtCore import QObject, QTimer, Signal

from ..core.config import Config
from ..core.logging import get_logger
from ..threads.asyncio_executor import get_global_executor

logger = get_logger(__name__)

MEDIA_CACHE_DIR = Config.CACHE_DIR / "media"

_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0)
# Hard cap so a misconfigured URL cannot fill the disk (matches the largest
# WhatsApp media limit: 100 MB documents).
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class MediaFetchHandle(QObject):
    """Per-request signal emitter returned by :meth:`MediaLoader.fetch`."""

    finished = Signal(str)  # absolute path of the cached local file
    failed = Signal(str)    # user-displayable error message


class MediaLoader(QObject):
    """Singleton download manager. Thread-safe: ``fetch`` may be called from
    the GUI thread while completions arrive from the executor thread."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._inflight: Dict[str, List[MediaFetchHandle]] = {}
        MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def cached_path(self, url: str) -> Optional[Path]:
        """Synchronous cache lookup; returns the local path or None."""
        if not url:
            return None
        path = self._path_for(url)
        return path if path.exists() else None

    def fetch(self, url: str, *, force: bool = False) -> MediaFetchHandle:
        """Request a media file; returns a handle whose signals fire later.

        ``force=True`` bypasses the disk cache (re-download).
        """
        handle = MediaFetchHandle()

        if not url or not url.startswith(("http://", "https://")):
            QTimer.singleShot(0, lambda: handle.failed.emit("URL de archivo no válida."))
            return handle

        path = self._path_for(url)
        if not force and path.exists():
            # Emit asynchronously so callers can connect after fetch() returns.
            QTimer.singleShot(0, lambda: handle.finished.emit(str(path)))
            return handle

        with self._lock:
            waiters = self._inflight.get(url)
            if waiters is not None:
                waiters.append(handle)
                return handle
            self._inflight[url] = [handle]

        try:
            # The executor's task object keeps the returned TaskSignals alive
            # for the duration of the download; no extra bookkeeping needed.
            get_global_executor().submit_coroutine(self._download(url, path))
        except Exception as e:  # noqa: BLE001 - executor not ready / shutting down
            # Capture the message NOW: Python deletes the except var `e` when the
            # block exits, so the deferred lambda below would raise NameError when
            # it runs on the event loop if it closed over `e` directly.
            err = str(e)
            logger.error("No se pudo programar la descarga de %s: %s", url, err)
            # Defer so callers connecting right after fetch() still get the signal.
            QTimer.singleShot(0, lambda: self._resolve(url, error=err))
        return handle

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _path_for(url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        if len(suffix) > 6:  # not a real extension (e.g. dotted path segment)
            suffix = ""
        return MEDIA_CACHE_DIR / f"{digest}{suffix}"

    async def _download(self, url: str, path: Path) -> None:
        """Runs on the executor loop; resolves all waiting handles at the end."""
        tmp_path = path.with_suffix(path.suffix + ".part")
        try:
            async with httpx.AsyncClient(
                timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
            ) as client:
                resp = await client.get(url)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}")
            if len(resp.content) > _MAX_DOWNLOAD_BYTES:
                raise RuntimeError("El archivo excede el tamaño máximo permitido.")

            MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(resp.content)
            os.replace(tmp_path, path)  # atomic publish into the cache
            self._resolve(url, path=str(path))
        except Exception as e:  # noqa: BLE001
            logger.warning("Descarga de media falló (%s): %s", url, e)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._resolve(url, error=str(e))

    def _resolve(self, url: str, *, path: Optional[str] = None, error: Optional[str] = None) -> None:
        """Emit completion on every handle waiting for ``url`` (any thread)."""
        with self._lock:
            handles = self._inflight.pop(url, [])
        for handle in handles:
            try:
                if path is not None:
                    handle.finished.emit(path)
                else:
                    handle.failed.emit(error or "Error desconocido al descargar.")
            except RuntimeError:
                # The receiving widget was deleted; nothing to deliver.
                pass


_loader_lock = threading.Lock()
_loader: Optional[MediaLoader] = None


def get_media_loader() -> MediaLoader:
    """Global MediaLoader instance (created lazily on first use)."""
    global _loader
    with _loader_lock:
        if _loader is None:
            _loader = MediaLoader()
    return _loader
