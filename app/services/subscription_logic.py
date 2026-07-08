"""Pure (Qt-free) subscription business logic.

Extracted from ``SubscriptionService`` (a QObject that also self-orchestrates
signals/threads) so this logic can be unit-tested and reused without a Qt event
loop. Everything here is a plain function of its inputs — no ``self``, no cache,
no signals. ``SubscriptionService`` keeps thin delegating wrappers so existing
call sites (``SubscriptionService.build_timeslot_groups(...)`` and
``service.validate_basic_form_data(...)``) are unchanged.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import md5
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from ..models.base import ClassTemplate, TimeslotGroup

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Template grouping
# ---------------------------------------------------------------------------
def build_timeslot_groups(templates: List[ClassTemplate]) -> List[TimeslotGroup]:
    """Agrupa plantillas de clase por horario recurrente.

    Agrupa por (class_type, venue, start_time_local, instructor); devuelve los
    grupos ordenados por tipo → venue → hora.
    """
    buckets: Dict[str, TimeslotGroup] = {}

    for template in templates:
        group_key = (
            template.class_type_id,
            template.venue_id,
            template.start_time_local,
            template.instructor_id,
        )
        key_hash = md5(str(group_key).encode()).hexdigest()[:8]

        if key_hash not in buckets:
            buckets[key_hash] = TimeslotGroup(
                key=key_hash,
                class_type_name=getattr(template, "class_type_name", "") or "Clase",
                venue_name=getattr(template, "venue_name", "") or "Venue",
                instructor_name=getattr(template, "instructor_name", None),
                start_time_local=getattr(template, "start_time_local", "") or "00:00",
                template_ids=[],
                templates=[],
            )

        buckets[key_hash].template_ids.append(template.id)
        buckets[key_hash].templates.append(template)

    groups = list(buckets.values())
    groups.sort(key=lambda g: (g.class_type_name, g.venue_name, g.start_time_local))

    logger.info("Created %d timeslot groups from %d templates", len(groups), len(templates))
    return groups


def find_group_by_template_id(
    template_id: int, groups: List[TimeslotGroup]
) -> Optional[TimeslotGroup]:
    """Encuentra el grupo que contiene una plantilla específica, o None."""
    for group in groups:
        if template_id in group.template_ids:
            return group
    return None


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def next_occurrence_on_or_after(start_date: date, weekday_1_to_7: int) -> date:
    """Primera fecha >= ``start_date`` que cae en el weekday objetivo.

    Modelo: Monday=1..Sunday=7. Python: Monday=0..Sunday=6.
    """
    target = (weekday_1_to_7 - 1) % 7
    delta = (target - start_date.weekday()) % 7
    return start_date + timedelta(days=delta)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_person_data(person_data: Dict[str, Any]) -> Optional[str]:
    """Valida datos de persona. Devuelve el mensaje de error o None si es válido."""
    full_name = person_data.get("full_name", "").strip()
    if not full_name:
        return "Nombre completo es requerido"
    if len(full_name) < 2:
        return "Nombre debe tener al menos 2 caracteres"

    phone = person_data.get("phone_number", "").strip()
    if phone and len(phone) < 8:
        return "Teléfono debe tener al menos 8 dígitos"
    return None


def validate_subscription_data(subscription_data: Dict[str, Any]) -> Optional[str]:
    """Valida datos de suscripción. Devuelve el mensaje de error o None."""
    plan_id = subscription_data.get("plan_id")
    if not plan_id or not isinstance(plan_id, int) or plan_id <= 0:
        return "Plan de membresía requerido"

    start_at = subscription_data.get("start_at")
    end_at = subscription_data.get("end_at")
    if isinstance(start_at, datetime) and isinstance(end_at, datetime):
        if end_at <= start_at:
            return "Fecha de fin debe ser posterior a fecha de inicio"
    return None


def validate_basic_form_data(form_data: Dict[str, Any]) -> Optional[str]:
    """Valida campos comunes de formulario (monto, método de pago, plan, fechas,
    y opcionalmente ``person``/``subscription``). Devuelve el mensaje de error o None.

    Acepta varios nombres de campo (amount/payment_amount, start_at/start_date, …).
    """
    try:
        amount = form_data.get("payment_amount") or form_data.get("amount", 0)
        if not isinstance(amount, (int, float)) or amount <= 0:
            return "Monto debe ser mayor a 0"

        payment_method = form_data.get("payment_method")
        if not payment_method:
            return "Método de pago requerido"

        valid_methods = ["cash", "card", "transfer", "other"]
        if payment_method not in valid_methods:
            return f"Método de pago inválido. Debe ser uno de: {', '.join(valid_methods)}"

        plan_id = form_data.get("plan_id")
        if plan_id is not None and (not isinstance(plan_id, int) or plan_id <= 0):
            return "Plan de membresía inválido"

        start_at = form_data.get("start_at") or form_data.get("start_date")
        end_at = form_data.get("end_at") or form_data.get("end_date")

        if isinstance(start_at, datetime) and isinstance(end_at, datetime):
            if end_at <= start_at:
                return "La fecha fin debe ser posterior a la fecha de inicio"
        elif isinstance(start_at, date) and isinstance(end_at, date):
            if end_at <= start_at:
                return "La fecha fin debe ser posterior a la fecha de inicio"

        # NOTE: la validación de fecha de inicio vive en
        # RenewSubscriptionDialog._validate_start_date_with_admin() para permitir
        # rangos flexibles con contraseña de administrador.

        if "person" in form_data:
            error = validate_person_data(form_data["person"])
            if error:
                return error

        if "subscription" in form_data:
            error = validate_subscription_data(form_data["subscription"])
            if error:
                return error

        return None
    except Exception as e:  # noqa: BLE001 - preserva el comportamiento original
        logger.error("Error validating form data: %s", e)
        return "Error de validación"


def validate_timeslot_group(group: TimeslotGroup) -> Optional[str]:
    """Valida un grupo de horario para crear una reserva fija. Error o None."""
    if not group.template_ids:
        return "Grupo de horario no contiene plantillas válidas"
    if not group.class_type_name or not group.venue_name:
        return "Información de clase incompleta"
    if not group.start_time_local:
        return "Hora de inicio requerida"
    return None
