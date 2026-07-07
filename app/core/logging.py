"""
Sistema de logging unificado para FitPilot.
"""
import sys
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

from .config import Config

# Días de retención de logs (rotación diaria + purga de restos antiguos).
LOG_RETENTION_DAYS = 30


class Logger:
    """Sistema de logging centralizado."""

    _instance: Optional['Logger'] = None
    _loggers: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logging()
        return cls._instance

    def _setup_logging(self) -> None:
        """Configura el sistema de logging."""
        # Crear directorio de logs si no existe
        Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Formato y nivel
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)

        # Handlers: consola + archivo con rotación real a medianoche.
        # (El FileHandler anterior calculaba la fecha una sola vez al arrancar,
        # así que solo "rotaba" si se reiniciaba la app y crecía sin límite.)
        file_handler = TimedRotatingFileHandler(
            Config.LOGS_DIR / "fitpilot.log",
            when="midnight",
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        handlers = [
            logging.StreamHandler(sys.stdout),
            file_handler,
        ]

        logging.basicConfig(
            level=log_level,
            format=log_format,
            datefmt=date_format,
            handlers=handlers,
        )

        self._purge_old_logs()

    @staticmethod
    def _purge_old_logs() -> None:
        """Borra logs con más de LOG_RETENTION_DAYS días.

        Cubre los restos del esquema anterior (``fitpilot_YYYYMMDD.log``) y los
        sufijos rotados de TimedRotatingFileHandler (``fitpilot.log.YYYY-MM-DD``);
        backupCount solo limpia los suyos y no toca los legacy.
        """
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        try:
            for path in Config.LOGS_DIR.glob("fitpilot*.log*"):
                try:
                    if path.is_file() and path.stat().st_mtime < cutoff:
                        path.unlink()
                except OSError:
                    continue  # en uso o sin permisos; se reintenta al próximo arranque
        except OSError:
            pass

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Obtiene o crea un logger con el nombre especificado."""
        instance = cls()
        if name not in instance._loggers:
            logger = logging.getLogger(name)
            instance._loggers[name] = logger
        return instance._loggers[name]

    @classmethod
    def log_error(cls, name: str, error: Exception, context: Optional[dict] = None) -> None:
        """Registra un error con contexto adicional."""
        logger = cls.get_logger(name)
        error_msg = f"{type(error).__name__}: {str(error)}"
        if context:
            error_msg += f" | Context: {context}"
        logger.error(error_msg, exc_info=True)

    @classmethod
    def log_performance(cls, name: str, operation: str, duration: float) -> None:
        """Registra métricas de rendimiento."""
        logger = cls.get_logger(name)
        if duration > 1.0:
            logger.warning(f"Slow operation '{operation}': {duration:.2f}s")
        else:
            logger.debug(f"Operation '{operation}': {duration:.2f}s")


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger configurado."""
    return Logger.get_logger(name)

