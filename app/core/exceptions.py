"""
Custom exceptions for FitPilot frontend application.

Provides a hierarchical exception structure for better error handling
and more specific error reporting throughout the application.
"""


class FitPilotException(Exception):
    """
    Base exception for all FitPilot-specific errors.

    All custom exceptions should inherit from this class to allow
    catching all application-specific errors at once if needed.
    """

    def __init__(self, message: str, details: str = None):
        """
        Initialize the exception.

        Args:
            message: User-friendly error message
            details: Optional technical details for logging
        """
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class ServiceUnavailableError(FitPilotException):
    """
    Raised when a required service is not available.

    Examples:
    - Backend server is down
    - Database connection failed
    - Required service not initialized
    """

    def __init__(self, service_name: str = "servicio", details: str = None):
        message = f"No se pudo conectar con {service_name}"
        super().__init__(message, details)
        self.service_name = service_name


class ValidationError(FitPilotException):
    """
    Raised when data validation fails.

    Examples:
    - Invalid form input
    - Business rule violation
    - Data integrity check failed
    """

    def __init__(self, field: str = None, message: str = "Error de validación", details: str = None):
        if field:
            full_message = f"Error en el campo '{field}': {message}"
        else:
            full_message = message
        super().__init__(full_message, details)
        self.field = field


class AuthenticationError(FitPilotException):
    """
    Raised when authentication or authorization fails.

    Examples:
    - Invalid credentials
    - Expired session/token
    - Insufficient permissions
    """

    def __init__(self, message: str = "Error de autenticación", details: str = None):
        super().__init__(message, details)


class NetworkError(FitPilotException):
    """
    Raised when network communication fails.

    Examples:
    - Connection timeout
    - DNS resolution failed
    - Network unreachable
    """

    def __init__(self, message: str = "Error de conexión de red", details: str = None):
        super().__init__(message, details)


class DataNotFoundError(FitPilotException):
    """
    Raised when requested data is not found.

    Examples:
    - Member not found
    - Subscription not found
    - Resource doesn't exist
    """

    def __init__(self, resource: str = "recurso", resource_id: int = None, details: str = None):
        if resource_id:
            message = f"{resource.capitalize()} con ID {resource_id} no encontrado"
        else:
            message = f"{resource.capitalize()} no encontrado"
        super().__init__(message, details)
        self.resource = resource
        self.resource_id = resource_id


class OperationCancelledError(FitPilotException):
    """
    Raised when an operation is cancelled by the user or system.

    Examples:
    - User cancelled dialog
    - Operation timed out
    - Concurrent operation conflict
    """

    def __init__(self, operation: str = "operación", details: str = None):
        message = f"La {operation} fue cancelada"
        super().__init__(message, details)
        self.operation = operation


class ConfigurationError(FitPilotException):
    """
    Raised when there's a configuration problem.

    Examples:
    - Missing environment variable
    - Invalid configuration value
    - Configuration file not found
    """

    def __init__(self, setting: str = None, message: str = "Error de configuración", details: str = None):
        if setting:
            full_message = f"Error en configuración '{setting}': {message}"
        else:
            full_message = message
        super().__init__(full_message, details)
        self.setting = setting


class BusinessRuleViolationError(FitPilotException):
    """
    Raised when a business rule is violated.

    Examples:
    - Subscription already exists
    - Cannot delete active member
    - Seat already occupied
    """

    def __init__(self, rule: str, message: str = None, details: str = None):
        if message:
            full_message = f"Violación de regla de negocio '{rule}': {message}"
        else:
            full_message = f"Violación de regla de negocio: {rule}"
        super().__init__(full_message, details)
        self.rule = rule


# Convenience functions for common error scenarios
def raise_service_unavailable(service_name: str = "servicio") -> None:
    """Raise ServiceUnavailableError with standard message."""
    raise ServiceUnavailableError(service_name)


def raise_validation_error(field: str, message: str) -> None:
    """Raise ValidationError for a specific field."""
    raise ValidationError(field, message)


def raise_authentication_error(message: str = "Sesión expirada. Por favor, inicie sesión nuevamente.") -> None:
    """Raise AuthenticationError with standard message."""
    raise AuthenticationError(message)


def raise_not_found(resource: str, resource_id: int = None) -> None:
    """Raise DataNotFoundError for a resource."""
    raise DataNotFoundError(resource, resource_id)
