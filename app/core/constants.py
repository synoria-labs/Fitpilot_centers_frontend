"""
Application-wide constants for FitPilot.

Centralized location for all magic numbers, strings, and configuration values
to improve maintainability and reduce duplication.
"""

# ==============================================================================
# TIMING CONSTANTS (all in milliseconds)
# ==============================================================================

# Refresh intervals
DASHBOARD_REFRESH_INTERVAL_MS = 60_000  # 60 seconds
SESSION_CHECK_INTERVAL_MS = 300_000  # 5 minutes
AUTO_SAVE_INTERVAL_MS = 30_000  # 30 seconds

# Debounce/throttle delays
SEARCH_DEBOUNCE_DELAY_MS = 300  # 300ms delay for search inputs
SCROLL_THROTTLE_INTERVAL_MS = 100  # 100ms throttle for scroll events
INPUT_DEBOUNCE_DELAY_MS = 500  # 500ms for general input fields

# Timeouts
NETWORK_REQUEST_TIMEOUT_MS = 30_000  # 30 seconds
ASYNCIO_QUEUE_TIMEOUT_MS = 100  # 100ms for asyncio queue operations
TOKEN_REFRESH_TIMEOUT_MS = 10_000  # 10 seconds

# Animation durations
FADE_ANIMATION_DURATION_MS = 200
SLIDE_ANIMATION_DURATION_MS = 300

# ==============================================================================
# SIZE CONSTANTS
# ==============================================================================

# Limits
MAX_AMOUNT = 1_000_000.0  # Maximum payment amount
MIN_AMOUNT = 0.01  # Minimum payment amount
MAX_MEMBER_NAME_LENGTH = 100
MAX_SEARCH_RESULTS = 100
DEFAULT_PAGE_SIZE = 20

# Concurrent operations
MAX_CONCURRENT_WORKERS = 3  # Maximum concurrent authenticated operations
MAX_THREAD_POOL_SIZE = 5  # Maximum threads in pool

# ==============================================================================
# UI CONSTANTS
# ==============================================================================

# Window sizes
MIN_WINDOW_WIDTH = 1024
MIN_WINDOW_HEIGHT = 768
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800

# Widget sizes
METRIC_CARD_MIN_WIDTH = 200
METRIC_CARD_MIN_HEIGHT = 120
SIDEBAR_WIDTH = 250
TOOLBAR_HEIGHT = 60

# Spacing and margins
DEFAULT_SPACING = 10
DEFAULT_MARGIN = 15
CARD_PADDING = 15
FORM_FIELD_SPACING = 8

# ==============================================================================
# COLOR CONSTANTS
# ==============================================================================

# Primary colors
COLOR_PRIMARY = "#3498db"  # Blue
COLOR_SUCCESS = "#27ae60"  # Green
COLOR_WARNING = "#f39c12"  # Orange
COLOR_DANGER = "#e74c3c"  # Red
COLOR_INFO = "#16a085"  # Teal

# Text colors
COLOR_TEXT_PRIMARY = "#2c3e50"
COLOR_TEXT_SECONDARY = "#7f8c8d"
COLOR_TEXT_MUTED = "#95a5a6"
COLOR_TEXT_LIGHT = "#bdc3c7"

# Background colors
COLOR_BG_PRIMARY = "#ffffff"
COLOR_BG_SECONDARY = "#f8f9fa"
COLOR_BG_DARK = "#34495e"
COLOR_BG_HOVER = "#ecf0f1"

# Border colors
COLOR_BORDER_LIGHT = "#e1e8ed"
COLOR_BORDER_DEFAULT = "#bdc3c7"
COLOR_BORDER_DARK = "#7f8c8d"

# ==============================================================================
# VALIDATION CONSTANTS
# ==============================================================================

# Field lengths
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 100
MIN_PHONE_LENGTH = 8
MAX_PHONE_LENGTH = 20
MIN_EMAIL_LENGTH = 5
MAX_EMAIL_LENGTH = 254

# Patterns (regex)
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
PHONE_PATTERN = r"^\+?[\d\s\-\(\)]{8,20}$"

# ==============================================================================
# PAYMENT CONSTANTS
# ==============================================================================

# Payment methods
PAYMENT_METHOD_CASH = "cash"
PAYMENT_METHOD_CARD = "card"
PAYMENT_METHOD_TRANSFER = "transfer"
PAYMENT_METHOD_OTHER = "other"

VALID_PAYMENT_METHODS = [
    PAYMENT_METHOD_CASH,
    PAYMENT_METHOD_CARD,
    PAYMENT_METHOD_TRANSFER,
    PAYMENT_METHOD_OTHER,
]

# Payment status
PAYMENT_STATUS_PENDING = "PENDING"
PAYMENT_STATUS_COMPLETED = "COMPLETED"
PAYMENT_STATUS_FAILED = "FAILED"
PAYMENT_STATUS_REFUNDED = "REFUNDED"

# ==============================================================================
# CACHE CONSTANTS
# ==============================================================================

# TTL (time to live) in seconds
CACHE_TTL_SHORT = 60  # 1 minute
CACHE_TTL_MEDIUM = 300  # 5 minutes
CACHE_TTL_LONG = 1800  # 30 minutes
CACHE_TTL_VERY_LONG = 86400  # 24 hours

# Cache keys
CACHE_KEY_PLANS = "membership_plans"
CACHE_KEY_TEMPLATES = "class_templates"
CACHE_KEY_MEMBERS = "members_list"
CACHE_KEY_USER_PROFILE = "user_profile_{user_id}"

# ==============================================================================
# API CONSTANTS
# ==============================================================================

# Retry settings
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_MS = 1000  # 1 second
RETRY_BACKOFF_MULTIPLIER = 2.0

# Endpoints (relative to base URL)
ENDPOINT_LOGIN = "/graphql"
ENDPOINT_REFRESH = "/graphql"
ENDPOINT_LOGOUT = "/graphql"

# ==============================================================================
# DATE/TIME CONSTANTS
# ==============================================================================

# Date formats
DATE_FORMAT_DISPLAY = "%d/%m/%Y"  # DD/MM/YYYY
DATE_FORMAT_ISO = "%Y-%m-%d"  # YYYY-MM-DD
DATETIME_FORMAT_DISPLAY = "%d/%m/%Y %H:%M"  # DD/MM/YYYY HH:MM
DATETIME_FORMAT_ISO = "%Y-%m-%dT%H:%M:%S"  # ISO 8601

# Timezone
DEFAULT_TIMEZONE = "America/Mexico_City"

# ==============================================================================
# STATUS CONSTANTS
# ==============================================================================

# Member status
MEMBER_STATUS_ACTIVE = "active"
MEMBER_STATUS_INACTIVE = "inactive"
MEMBER_STATUS_SUSPENDED = "suspended"

# Subscription status
SUBSCRIPTION_STATUS_ACTIVE = "active"
SUBSCRIPTION_STATUS_EXPIRED = "expired"
SUBSCRIPTION_STATUS_CANCELLED = "cancelled"

# ==============================================================================
# LOGGING CONSTANTS
# ==============================================================================

# Log levels
LOG_LEVEL_DEBUG = "DEBUG"
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"
LOG_LEVEL_CRITICAL = "CRITICAL"

# Log format
LOG_FORMAT_DEFAULT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_DETAILED = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

# ==============================================================================
# FILE CONSTANTS
# ==============================================================================

# Extensions
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
ALLOWED_DOCUMENT_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx"]

# Size limits (in bytes)
MAX_UPLOAD_SIZE = 10_485_760  # 10 MB
MAX_IMAGE_SIZE = 5_242_880  # 5 MB

# ==============================================================================
# ERROR MESSAGES (Common)
# ==============================================================================

ERROR_SERVICE_UNAVAILABLE = "Servicio no disponible"
ERROR_NETWORK = "Error de conexión de red"
ERROR_AUTH_FAILED = "Error de autenticación"
ERROR_VALIDATION_FAILED = "Error de validación"
ERROR_NOT_FOUND = "Recurso no encontrado"
ERROR_PERMISSION_DENIED = "Permiso denegado"

# ==============================================================================
# SUCCESS MESSAGES (Common)
# ==============================================================================

SUCCESS_SAVE = "Guardado correctamente"
SUCCESS_UPDATE = "Actualizado correctamente"
SUCCESS_DELETE = "Eliminado correctamente"
SUCCESS_CREATE = "Creado correctamente"
