"""
Configuración principal de la aplicación FitPilot.
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class Config:
    """Configuración central de la aplicación."""
    
    # API Configuration
    API_BASE_URL: str = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
    GRAPHQL_URL: str = os.getenv('GRAPHQL_URL', 'http://127.0.0.1:8000/graphql')
    # WebSocket endpoint for GraphQL subscriptions (Strawberry serves it on /graphql)
    GRAPHQL_WS_URL: str = os.getenv('GRAPHQL_WS_URL', 'ws://127.0.0.1:8000/graphql')
    REST_USERS_URL: str = os.getenv('REST_USERS_URL', 'http://127.0.0.1:8000/users')
    
    # JWT Configuration
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '15'))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '7'))
    
    # Environment
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')
    TIMEZONE: str = os.getenv('TIMEZONE', 'America/Mexico_City')
    
    # Application Settings
    APP_NAME: str = os.getenv('APP_NAME', 'FitPilot')
    APP_VERSION: str = os.getenv('APP_VERSION', '1.0.0')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / 'data'
    LOGS_DIR: Path = BASE_DIR / 'logs'
    CACHE_DIR: Path = BASE_DIR / 'cache'
    
    # UI Settings
    THEME: str = 'dark'
    WINDOW_WIDTH: int = 1280
    WINDOW_HEIGHT: int = 800

    # POS / thermal receipt (POS-58). PRINTER_NAME empty -> use the OS default printer.
    PRINTER_NAME: str = os.getenv('PRINTER_NAME', 'POS-58')
    RECEIPT_BRAND: str = os.getenv('RECEIPT_BRAND', 'FITPILOT')
    RECEIPT_FOOTER: str = os.getenv('RECEIPT_FOOTER', '¡Gracias por su preferencia!')
    RECEIPT_WIDTH: int = int(os.getenv('RECEIPT_WIDTH', '40'))
    
    # Performance Settings
    MAX_THREADS: int = 4
    CACHE_ENABLED: bool = True
    LAZY_LOADING: bool = True

    # Request Settings
    GRAPHQL_TIMEOUT: float = 30.0
    GRAPHQL_MAX_RETRIES: int = 3
    GRAPHQL_RETRY_DELAYS: list = [0.1, 0.3, 0.5]  # Exponential backoff in seconds
    MAX_CONCURRENT_WORKERS: int = 3  # Limit concurrent authenticated workers

    @classmethod
    def init_directories(cls):
        """Crea los directorios necesarios si no existen."""
        for dir_path in [cls.DATA_DIR, cls.LOGS_DIR, cls.CACHE_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def is_development(cls) -> bool:
        """Verifica si estamos en modo desarrollo."""
        return cls.ENVIRONMENT == 'development'
    
    @classmethod
    def is_production(cls) -> bool:
        """Verifica si estamos en modo producción."""
        return cls.ENVIRONMENT == 'production'
    
    @classmethod
    def get_api_headers(cls, token: Optional[str] = None) -> dict:
        """Obtiene los headers para las peticiones API."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers

# Inicializar configuración
Config.init_directories()

# Exportar instancia
config = Config()
