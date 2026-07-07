"""
Servicio de cache para optimización de rendimiento.
"""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, Optional, TypedDict

from ..core.config import Config
from ..core.logging import get_logger

logger = get_logger(__name__)

# Tope de entradas en memoria. El caché en memoria era un dict sin límite: crecía
# indefinidamente (las entradas vencidas nunca se purgaban, solo se sobreescribían
# por clave). Ahora es un LRU acotado.
_MAX_MEMORY_ENTRIES = 256


class CacheEntry(TypedDict):
    value: Any
    timestamp: float


class CacheService:
    """Servicio simple de caché en memoria (LRU acotado) y disco (singleton)."""

    # Para Pylance: declarar atributos de instancia y el singleton
    _instance: ClassVar[Optional["CacheService"]] = None
    memory_cache: "OrderedDict[str, CacheEntry]"
    cache_dir: Path

    def __new__(cls) -> "CacheService":
        if cls._instance is None:
            inst = super().__new__(cls)
            # Inicializamos atributos de instancia tipados
            inst.memory_cache = OrderedDict()
            # Asegura Path: Config.CACHE_DIR puede ser str o Path
            cache_dir = getattr(Config, "CACHE_DIR", ".cache")
            inst.cache_dir = Path(cache_dir)
            inst.cache_dir.mkdir(parents=True, exist_ok=True)
            cls._instance = inst
        return cls._instance  # type: ignore[return-value]

    # No redefinimos __init__ para no re-ejecutar nada en cada obtención del singleton

    def _remember(self, key: str, entry: CacheEntry) -> None:
        """Inserta en el LRU en memoria y desaloja las entradas más antiguas."""
        self.memory_cache[key] = entry
        self.memory_cache.move_to_end(key)
        while len(self.memory_cache) > _MAX_MEMORY_ENTRIES:
            self.memory_cache.popitem(last=False)  # elimina la menos usada

    def _key_path(self, key: str) -> Path:
        """Convierte una clave en una ruta de archivo segura."""
        # Sanea caracteres problemáticos en nombres de archivo
        safe = "".join(c if c.isalnum() or c in ("-", "_", ".", "@") else "_" for c in key)
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str, max_age: int = 300) -> Optional[Any]:
        """
        Obtiene un valor del caché.

        Args:
            key: Clave del caché.
            max_age: Edad máxima en segundos (default: 5 minutos).
        """
        now = time.time()

        # 1) Memoria
        entry = self.memory_cache.get(key)
        if entry:
            if now - entry["timestamp"] < max_age:
                self.memory_cache.move_to_end(key)  # marca como reciente (LRU)
                logger.debug(f"Cache hit (memory): {key}")
                return entry["value"]
            # Vencida: purgar de memoria en vez de retenerla para siempre.
            self.memory_cache.pop(key, None)

        # 2) Disco
        cache_file = self._key_path(key)
        if cache_file.exists():
            try:
                with cache_file.open("r", encoding="utf-8") as f:
                    on_disk: CacheEntry = json.load(f)  # type: ignore[assignment]
                if now - on_disk["timestamp"] < max_age:
                    # Promociona a memoria
                    self._remember(key, on_disk)
                    logger.debug(f"Cache hit (disk): {key}")
                    return on_disk["value"]
            except (OSError, JSONDecodeError) as e:
                logger.error(f"Error reading cache {key}: {e}")

        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """
        Guarda un valor en el caché.

        Args:
            key: Clave del caché.
            value: Valor a guardar.
            persist: Si se debe persistir en disco.
        """
        entry: CacheEntry = {"value": value, "timestamp": time.time()}

        # Memoria (LRU acotado)
        self._remember(key, entry)

        # Disco
        if persist:
            cache_file = self._key_path(key)
            try:
                with cache_file.open("w", encoding="utf-8") as f:
                    json.dump(entry, f)
                logger.debug(f"Cache set: {key}")
            except OSError as e:
                logger.error(f"Error saving cache {key}: {e}")

    def delete(self, key: str) -> None:
        """Elimina una entrada del caché (memoria y disco)."""
        self.memory_cache.pop(key, None)
        cache_file = self._key_path(key)
        try:
            if cache_file.exists():
                cache_file.unlink()
        except OSError as e:
            logger.error(f"Error deleting cache {key}: {e}")
        logger.debug(f"Cache deleted: {key}")

    def clear(self) -> None:
        """Limpia todo el caché (memoria y disco)."""
        self.memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except OSError as e:
                logger.error(f"No se pudo eliminar {cache_file}: {e}")
        logger.info("Cache cleared")

    def warm(self, key: str) -> None:
        """Precalienta una clave (placeholder)."""
        logger.debug(f"Warming cache: {key}")

    def get_or_set(self, key: str, factory_func: Callable[[], Any], max_age: int = 300) -> Any:
        """
        Obtiene del caché o calcula y guarda.

        Args:
            key: Clave del caché.
            factory_func: Función que produce el valor si no existe o está vencido.
            max_age: Edad máxima en segundos.
        """
        value = self.get(key, max_age)
        if value is None:
            value = factory_func()
            self.set(key, value)
        return value

    def invalidate_pattern(self, pattern: str) -> None:
        """
        Invalida todas las entradas que contengan un patrón en la clave.
        """
        # Memoria
        keys_to_delete = [k for k in self.memory_cache.keys() if pattern in k]
        for k in keys_to_delete:
            self.memory_cache.pop(k, None)

        # Disco
        for cache_file in self.cache_dir.glob(f"*{pattern}*.json"):
            try:
                cache_file.unlink()
            except OSError as e:
                logger.error(f"No se pudo eliminar {cache_file}: {e}")

        logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")

    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del caché."""
        disk_files = list(self.cache_dir.glob("*.json"))
        disk_size = sum((f.stat().st_size for f in disk_files), 0)
        return {
            "memory_entries": len(self.memory_cache),
            "disk_entries": len(disk_files),
            "disk_size_bytes": disk_size,
            "disk_size_mb": disk_size / (1024 * 1024),
        }
