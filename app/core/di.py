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
    _services: Dict[str, Any] = {}
    _factories: Dict[str, Callable] = {}

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
            singleton: Si el servicio debe ser singleton
        """
        if service is not None:
            self._services[name] = service
            logger.debug(f"Registered service: {name}")
        elif factory is not None:
            if singleton:
                # Crear instancia única al primer uso
                self._factories[name] = factory
            else:
                # Crear nueva instancia cada vez
                self._factories[name] = lambda: factory()
            logger.debug(f"Registered factory: {name}")
        else:
            raise ValueError("Debe proporcionar un servicio o factory")
    
    def get(self, name: str) -> Any:
        """
        Obtiene un servicio del contenedor.
        
        Args:
            name: Nombre del servicio
            
        Returns:
            Instancia del servicio
        """
        # Buscar en servicios registrados
        if name in self._services:
            return self._services[name]
        
        # Buscar en factories
        if name in self._factories:
            if name not in self._services:
                # Crear instancia usando factory
                self._services[name] = self._factories[name]()
            return self._services[name]
        
        raise ValueError(f"Servicio no encontrado: {name}")
    
    def has(self, name: str) -> bool:
        """Verifica si un servicio está registrado."""
        return name in self._services or name in self._factories
    
    def clear(self):
        """Limpia todos los servicios registrados."""
        self._services.clear()
        self._factories.clear()
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
