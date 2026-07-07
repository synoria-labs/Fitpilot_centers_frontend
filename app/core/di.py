"""
Sistema simple de inyección de dependencias para FitPilot.
"""
import threading
from typing import Dict, Any, Type, Optional, Callable
from .logging import get_logger

logger = get_logger(__name__)

class ServiceContainer:
    """Contenedor de servicios para inyección de dependencias."""

    _instance: Optional['ServiceContainer'] = None
    _lock: threading.Lock = threading.Lock()
    # Reentrant: a factory may call container.get(...) for a sibling service while
    # this lock is held, so a plain Lock would self-deadlock. Guards the registry
    # dicts and the compound check-then-create in get().
    _registry_lock: "threading.RLock" = threading.RLock()
    _services: Dict[str, Any] = {}
    _factories: Dict[str, Callable] = {}
    # Per-factory singleton intent. Without this, singleton=False silently behaved
    # like a singleton (the factory ran once and the instance was cached forever).
    _singleton_flags: Dict[str, bool] = {}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, service: Any = None, factory: Callable = None, singleton: bool = True):
        """
        Registra un servicio o factory en el contenedor.

        Args:
            name: Nombre del servicio
            service: Instancia del servicio (para singletons)
            factory: Función factory para crear el servicio
            singleton: Si el servicio debe ser singleton (nueva instancia por get() si False)
        """
        with self._registry_lock:
            if service is not None:
                self._services[name] = service
                logger.debug(f"Registered service: {name}")
            elif factory is not None:
                self._factories[name] = factory
                self._singleton_flags[name] = singleton
                logger.debug(f"Registered factory: {name} (singleton={singleton})")
            else:
                raise ValueError("Debe proporcionar un servicio o factory")

    def get(self, name: str) -> Any:
        """
        Obtiene un servicio del contenedor.

        Singleton factories se crean una sola vez (double-checked locking); las
        no-singleton devuelven una instancia nueva en cada llamada.
        """
        # Fast path (lock-free): instancia eager o singleton ya materializado.
        # Una lectura de dict es atómica bajo el GIL; es el caso comun.
        if name in self._services:
            return self._services[name]

        with self._registry_lock:
            # Re-chequear bajo lock: otro hilo pudo materializar el singleton.
            if name in self._services:
                return self._services[name]
            if name not in self._factories:
                raise ValueError(f"Servicio no encontrado: {name}")
            factory = self._factories[name]
            is_singleton = self._singleton_flags.get(name, True)
            if is_singleton:
                # Se crea a lo sumo una vez y se cachea.
                instance = factory()
                self._services[name] = instance
                return instance
            # No-singleton: capturar la factory y crear FUERA del lock, sin cachear,
            # asi cada get() devuelve una instancia fresca.
        return factory()

    def has(self, name: str) -> bool:
        """Verifica si un servicio está registrado."""
        return name in self._services or name in self._factories

    def clear(self):
        """Limpia todos los servicios registrados."""
        with self._registry_lock:
            self._services.clear()
            self._factories.clear()
            self._singleton_flags.clear()
        logger.debug("Service container cleared")

# Instancia global del contenedor
container = ServiceContainer()

# Decorador para inyección automática
def inject(**dependencies):
    """
    Decorador para inyectar dependencias en una clase.
    
    Uso:
        @inject(auth_service='auth_service', db='database')
        class MyController:
            def __init__(self, auth_service, db):
                self.auth = auth_service
                self.db = db
    """
    def decorator(cls):
        original_init = cls.__init__
        
        def new_init(self, *args, **kwargs):
            # Inyectar dependencias
            for param_name, service_name in dependencies.items():
                if param_name not in kwargs and container.has(service_name):
                    kwargs[param_name] = container.get(service_name)
            
            # Llamar al __init__ original
            original_init(self, *args, **kwargs)
        
        cls.__init__ = new_init
        return cls
    
    return decorator

# Función helper para registrar servicios
