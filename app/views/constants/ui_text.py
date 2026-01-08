"""UI text constants for the new subscription dialog."""

import re

# Constants
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
MINIMUM_DIALOG_WIDTH = 420
AMOUNT_MAXIMUM = 1_000_000
COMMENT_MAX_HEIGHT = 80
AMOUNT_DECIMALS = 2


class NewSubscriptionUIText:
    """UI text constants for better maintainability."""

    WINDOW_TITLE = "Nueva Suscripcion"
    NAME_PLACEHOLDER = "Nombre completo del socio"
    EMAIL_PLACEHOLDER = "correo@ejemplo.com"
    PHONE_PLACEHOLDER = "Telefono de contacto"
    WHATSAPP_PLACEHOLDER = "WhatsApp ID (opcional)"
    COMMENT_PLACEHOLDER = "Notas u observaciones del pago"

    # Form labels
    NAME_LABEL = "Nombre"
    EMAIL_LABEL = "Email"
    PHONE_LABEL = "Telefono"
    WHATSAPP_LABEL = "WhatsApp"
    PLAN_LABEL = "Plan"
    START_DATE_LABEL = "Fecha inicio"
    PAYMENT_METHOD_LABEL = "Metodo de pago"
    AMOUNT_LABEL = "Monto"
    COMMENT_LABEL = "Comentario"

    # Standing booking
    STANDING_BOOKING_TITLE = "Reserva de Clase"
    CLASS_LABEL = "Clase:"
    SEAT_LABEL = "Bicicleta / Lugar:"

    # Button states
    CREATING_TEXT = "Creando..."
    CREATING_BOOKING_TEXT = "Creando reserva con horario fijo..."
    ACCEPT_TEXT = "Aceptar"

    # Messages
    NO_PLANS_WARNING = "No hay planes de membresía disponibles."
    PLANS_ERROR = "No se pudieron cargar los planes de membresía."
    INCOMPLETE_DATA = "Datos incompletos"
    NAME_REQUIRED = "El nombre es obligatorio."
    INVALID_EMAIL = "El formato del email no es válido."
    SELECT_PLAN = "Selecciona un plan"
    VALID_PLAN_REQUIRED = "Debes elegir un plan de membresía válido."
    PAYMENT_METHOD_REQUIRED = "Selecciona un método de pago."
    CLASS_REQUIRED = "Debes seleccionar una clase para la reserva."
    SEAT_REQUIRED = "Debes seleccionar un lugar para esta clase."
    CREATION_ERROR = "No se pudo crear la suscripcion. Intenta de nuevo."
    ENROLLMENT_SUCCESS = "Suscripcion creada exitosamente."
    BOOKING_SUCCESS = "Suscripcion y reserva creados exitosamente."
    CONFIRMATION_TITLE = "Confirmacion"
    ERROR_TITLE = "Error"
class RenewSubscriptionUIText:
    """UI text constants used by the renew subscription dialog."""

    WINDOW_TITLE = "Renovar suscripcion"
    GROUP_TITLE = "Datos de renovacion"
    PLAN_LABEL = "Plan"
    CLASS_LABEL = "Clase"
    NO_CLASS_OPTION = "Sin clase asignada"
    SEAT_LABEL = "Lugar / Asiento"
    PAYMENT_METHOD_LABEL = "Metodo de pago"
    CONFIRM_TEXT = "Confirmar"
    CANCEL_TEXT = "Cancelar"
    LOADING_TEXT = "Cargando..."
    ERROR_TITLE = "Error"
    PLAN_REQUIRED = "Selecciona un plan valido."
    SEAT_REQUIRED = "Selecciona un lugar disponible."
    PAYMENT_REQUIRED = "Selecciona un metodo de pago."
