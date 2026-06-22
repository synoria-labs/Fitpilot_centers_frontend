"""
Modelos base y DTOs para FitPilot.
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List
from enum import Enum

class BaseModel:
    """Modelo base con funcionalidad común."""
    
    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    @classmethod
    def from_dict(cls, data: dict):
        """Crea una instancia desde un diccionario."""
        return cls(**data)

# Enums
class UserRole(Enum):
    ADMIN = "admin"
    RECEPTIONIST = "recepcionista"
    USER = "usuario"

class PaymentStatus(Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class AssetStatus(Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"

class ReservationStatus(Enum):
    RESERVED = "reserved"
    WAITLISTED = "waitlisted"
    CANCELED = "canceled"
    CHECKED_IN = "checked_in"
    NO_SHOW = "no_show"

class SubscriptionStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"
    PENDING = "pending"

# DTOs (Data Transfer Objects)

@dataclass
class User(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str = "usuario"
    role_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class AppRole(BaseModel):
    """A system role available to assign to login users."""
    id: int
    code: str
    description: Optional[str] = None

    def display(self) -> str:
        return self.description or self.code

@dataclass
class AppUser(BaseModel):
    """A login account (staff user): credentials + identity + roles."""
    account_id: int
    person_id: int
    username: str
    is_active: bool = True
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    created_at: Optional[datetime] = None
    roles: List['AppRole'] = field(default_factory=list)

    def roles_display(self) -> str:
        return ", ".join(r.display() for r in self.roles) if self.roles else "—"

    def role_ids(self) -> List[int]:
        return [r.id for r in self.roles]

@dataclass
class Person(BaseModel):
    id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    wa_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Member(BaseModel):
    id: int
    full_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    wa_id: Optional[str] = None
    registration_date: datetime = field(default_factory=datetime.now)
    active_membership: Optional['MembershipInfo'] = None
    active_standing_booking: Optional['ActiveStandingBookingInfo'] = None
    total_payments: float = 0.0
    last_activity: Optional[datetime] = None

@dataclass
class MembershipPlan(BaseModel):
    id: int
    name: str
    price: float
    duration_value: int
    description: Optional[str] = None
    duration_unit: str = "day"  # day, week, month
    class_limit: Optional[int] = None
    plan_type: str = "fixed_schedule"  # fixed_schedule | flexible | credit_pack
    fixed_time_slot: bool = False
    is_active: bool = True
    max_sessions_per_day: Optional[int] = None
    max_sessions_per_week: Optional[int] = None
    created_at: Optional[datetime] = None

    def price_display(self) -> str:
        """Retorna el precio formateado."""
        return f"${self.price:,.2f}"

    def duration_display(self) -> str:
        """Retorna la duración formateada."""
        unit_map = {"day": "días", "week": "semanas", "month": "meses"}
        unit_text = unit_map.get(self.duration_unit, self.duration_unit)
        return f"{self.duration_value} {unit_text}"

    def type_display(self) -> str:
        """Retorna el tipo de plan en texto legible."""
        type_map = {
            "fixed_schedule": "Horario fijo",
            "flexible": "Acceso libre",
            "credit_pack": "Créditos prepagados",
        }
        return type_map.get(self.plan_type, self.plan_type)

@dataclass
class MembershipInfo(BaseModel):
    status: str
    subscription_id: Optional[int] = None
    plan_name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    remaining_days: Optional[int] = None
    price: Optional[float] = None
    duration_value: Optional[int] = None
    duration_unit: Optional[str] = None


@dataclass
class ActiveStandingBookingInfo(BaseModel):
    template_id: int
    template_name: Optional[str] = None
    class_type_name: Optional[str] = None
    weekday: Optional[int] = None
    start_time_local: Optional[str] = None
    venue_name: Optional[str] = None
    instructor_name: Optional[str] = None

    def display_label(self) -> str:
        name = self.template_name or self.class_type_name or "Clase"
        time_label = self.start_time_local or ""
        venue_label = self.venue_name or ""
        parts = [name, time_label, venue_label]
        return " - ".join([part for part in parts if part])

    def weekday_label(self) -> str:
        mapping = {
            0: "Dom",
            1: "Lun",
            2: "Mar",
            3: "Mie",
            4: "Jue",
            5: "Vie",
            6: "Sab",
            7: "Dom",
        }
        if self.weekday is None:
            return ""
        return mapping.get(self.weekday, str(self.weekday))

@dataclass
class MembershipSubscription(BaseModel):
    id: int
    person_id: int
    plan_id: int
    start_at: datetime
    end_at: datetime
    status: str  # active, expired, canceled, pending
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Relaciones
    person: Optional[Person] = None
    plan: Optional[MembershipPlan] = None

    # Campos calculados
    total_payments: float = 0.0
    remaining_days: Optional[int] = None

    def is_active(self) -> bool:
        """Verifica si la suscripción está activa."""
        return self.status == 'active'

    def is_expired(self) -> bool:
        """Verifica si la suscripción está vencida."""
        return self.status == 'expired'

    def days_until_expiry(self) -> Optional[int]:
        """Calcula los días hasta el vencimiento."""
        if self.end_at:
            delta = self.end_at.date() - datetime.now().date()
            return max(0, delta.days)
        return None

    def status_display(self) -> str:
        """Retorna el estado en español."""
        status_map = {
            'active': 'Activo',
            'expired': 'Vencido',
            'canceled': 'Cancelado',
            'pending': 'Pendiente'
        }
        return status_map.get(self.status, self.status)

@dataclass
class Asset(BaseModel):
    id: int
    name: str
    asset_type: str
    serial_number: Optional[str] = None
    status: str = "active"
    maintenance_notes: Optional[str] = None
    venue_id: Optional[int] = None
    created_at: Optional[datetime] = None

    def is_available(self) -> bool:
        """Verifica si el asset está disponible."""
        return self.status == "active"

@dataclass
class ClassSession(BaseModel):
    id: int
    template_id: int
    venue_id: int
    start_time: datetime
    end_time: datetime
    capacity: int
    instructor_id: Optional[int] = None
    booked_count: int = 0
    status: str = "scheduled"
    notes: Optional[str] = None

    def display_time(self) -> str:
        """Retorna la hora formateada."""
        return self.start_time.strftime("%H:%M")

    def is_available(self) -> bool:
        """Verifica si hay cupos disponibles."""
        return self.booked_count < self.capacity and self.status == "scheduled"

@dataclass
class Reservation(BaseModel):
    id: int
    person_id: int
    session_id: int
    seat_id: Optional[int] = None
    status: str = "reserved"
    reserved_at: datetime = field(default_factory=datetime.now)
    checkin_at: Optional[datetime] = None
    checkout_at: Optional[datetime] = None
    source: str = "manual"

    # Related data from GraphQL
    person_name: Optional[str] = None
    seat_label: Optional[str] = None
    session_name: Optional[str] = None
    session_start: Optional[datetime] = None
    session_end: Optional[datetime] = None

    def is_active(self) -> bool:
        """Verifica si la reserva está activa."""
        return self.status in ["reserved", "checked_in"]

    def can_checkin(self) -> bool:
        """Verifica si se puede hacer check-in."""
        return self.status == "reserved"

    def can_cancel(self) -> bool:
        """Verifica si se puede cancelar."""
        return self.status in ["reserved", "waitlisted"]

@dataclass
class Payment(BaseModel):
    id: int
    person_id: int
    amount: float
    method: str  # cash, card, transfer, etc.
    subscription_id: Optional[int] = None
    paid_at: datetime = field(default_factory=datetime.now)
    provider: Optional[str] = None  # mercadopago, stripe, etc.
    provider_payment_id: Optional[str] = None
    external_reference: Optional[str] = None
    status: str = "COMPLETED"
    comment: Optional[str] = None
    recorded_by: Optional[int] = None

    # Relaciones opcionales
    member: Optional[Member] = None
    subscription: Optional[MembershipInfo] = None

    def amount_display(self) -> str:
        """Retorna el monto formateado."""
        return f"${self.amount:,.2f}"

# Modelos para métricas y dashboard
@dataclass
class DashboardMetrics(BaseModel):
    total_members: int = 0
    active_members: int = 0
    monthly_revenue: float = 0.0
    today_reservations: int = 0
    average_occupancy: float = 0.0
    new_members_month: int = 0

    def revenue_display(self) -> str:
        """Retorna los ingresos formateados."""
        return f"${self.monthly_revenue:,.2f}"

@dataclass
class SessionOccupancy(BaseModel):
    session_id: int
    session_name: str
    date: datetime
    total_capacity: int
    booked_count: int
    available_spots: int

    def occupancy_percentage(self) -> float:
        """Calcula el porcentaje de ocupación."""
        if self.total_capacity == 0:
            return 0.0
        return (self.booked_count / self.total_capacity) * 100

@dataclass
class Venue(BaseModel):
    id: int
    name: str
    capacity: int
    description: Optional[str] = None
    address: Optional[str] = None
    created_at: Optional[datetime] = None

@dataclass
class ClassType(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None

    def display_name(self) -> str:
        """Retorna el nombre para mostrar en UI."""
        return f"{self.name} ({self.code})"

@dataclass
class ClassTemplate(BaseModel):
    id: int
    class_type_id: int
    venue_id: int
    default_capacity: Optional[int]
    default_duration_min: int
    weekday: int  # 0=Sunday, 6=Saturday
    start_time_local: str
    instructor_id: Optional[int]
    name: Optional[str]
    is_active: bool

    # Related data from GraphQL
    class_type_name: Optional[str] = None
    venue_name: Optional[str] = None
    instructor_name: Optional[str] = None

    def weekday_name(self) -> str:
        """Retorna el nombre del día de la semana."""
        days = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
        return days[self.weekday] if 0 <= self.weekday <= 6 else "Desconocido"

    def display_name(self) -> str:
        """Retorna el nombre para mostrar en UI."""
        if self.name:
            return f"{self.name} - {self.weekday_name()} {self.start_time_local}"
        elif self.class_type_name:
            return f"{self.class_type_name} - {self.weekday_name()} {self.start_time_local}"
        else:
            return f"Clase - {self.weekday_name()} {self.start_time_local}"

    def display_time(self) -> str:
        """Retorna la hora formateada."""
        return self.start_time_local

    def requires_seats(self) -> bool:
        """Determina si esta clase requiere selección de asientos."""
        if not self.class_type_name:
            return False

        # Tipos de clase que requieren asientos
        seat_requiring_types = ['spinning', 'spin', 'cycling', 'ciclismo']
        return any(
            seat_type in self.class_type_name.lower()
            for seat_type in seat_requiring_types
        )

@dataclass
class Seat(BaseModel):
    id: int
    label: str
    venue_id: int
    is_active: bool
    seat_type_name: Optional[str] = None
    is_available: bool = True

    def display_name(self) -> str:
        """Retorna el nombre para mostrar en UI."""
        if self.seat_type_name:
            return f"{self.label} ({self.seat_type_name})"
        return self.label

@dataclass
class StandingBooking(BaseModel):
    id: int
    person_id: int
    subscription_id: int
    template_id: int
    seat_id: Optional[int]
    start_date: datetime
    end_date: datetime
    status: str  # active, paused, canceled
    created_at: datetime

    # Related data from GraphQL
    person_name: Optional[str] = None
    template_name: Optional[str] = None
    class_type_name: Optional[str] = None
    venue_name: Optional[str] = None
    seat_label: Optional[str] = None
    weekday: Optional[int] = None
    start_time_local: Optional[str] = None

    def is_active(self) -> bool:
        """Verifica si el standing booking está activo."""
        return self.status == 'active'

    def is_paused(self) -> bool:
        """Verifica si el standing booking está pausado."""
        return self.status == 'paused'

    def is_canceled(self) -> bool:
        """Verifica si el standing booking está cancelado."""
        return self.status == 'canceled'

    def status_display(self) -> str:
        """Retorna el estado en español."""
        status_map = {
            'active': 'Activo',
            'paused': 'Pausado',
            'canceled': 'Cancelado'
        }
        return status_map.get(self.status, self.status)

    def display_name(self) -> str:
        """Retorna el nombre para mostrar en UI."""
        if self.template_name:
            return self.template_name
        elif self.class_type_name and self.weekday is not None and self.start_time_local:
            days = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
            day_name = days[self.weekday] if 0 <= self.weekday <= 6 else "?"
            return f"{self.class_type_name} - {day_name} {self.start_time_local}"
        else:
            return f"Reservativo #{self.id}"

    def display_schedule(self) -> str:
        """Retorna el horario formateado."""
        if self.weekday is not None and self.start_time_local:
            days = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
            day_name = days[self.weekday] if 0 <= self.weekday <= 6 else "Desconocido"
            return f"{day_name} a las {self.start_time_local}"
        return "Horario no disponible"

    def display_seat(self) -> str:
        """Retorna información del asiento si aplica."""
        if self.seat_label:
            return f"Asiento: {self.seat_label}"
        return "Sin asiento asignado"

    def days_until_end(self) -> Optional[int]:
        """Calcula los días hasta el final del periodo."""
        if self.end_date:
            delta = self.end_date.date() - datetime.now().date()
            return max(0, delta.days)
        return None

@dataclass
class StandingBookingException(BaseModel):
    id: int
    standing_booking_id: int
    session_date: datetime
    action: str  # skip, reschedule
    new_session_id: Optional[int]
    notes: Optional[str]
    created_at: datetime

    def action_display(self) -> str:
        """Retorna la acción en español."""
        action_map = {
            'skip': 'Omitir',
            'reschedule': 'Reprogramar'
        }
        return action_map.get(self.action, self.action)

@dataclass
class MaterializationPreview(BaseModel):
    date: datetime
    session_id: int
    session_name: Optional[str]
    start_time: datetime
    status: str
    reason: str

    def status_display(self) -> str:
        """Retorna el estado en español."""
        status_map = {
            'will_create': 'Se creará',
            'existing': 'Ya existe',
            'blocked': 'Bloqueado',
            'skipped': 'Omitido',
            'rescheduled': 'Reprogramado'
        }
        return status_map.get(self.status, self.status)

    def display_time(self) -> str:
        """Retorna la hora formateada."""
        return self.start_time.strftime("%H:%M")

@dataclass
class MaterializationStats(BaseModel):
    processed_bookings: int
    created_reservations: int
    skipped_no_capacity: int
    skipped_seat_taken: int
    skipped_existing: int
    skipped_exceptions: int
    errors: List[str]

    def success_rate(self) -> float:
        """Calcula el porcentaje de éxito."""
        total = (self.created_reservations + self.skipped_no_capacity +
                self.skipped_seat_taken + self.skipped_existing + self.skipped_exceptions)
        if total == 0:
            return 0.0
        return (self.created_reservations / total) * 100

    def summary_text(self) -> str:
        """Retorna un resumen en texto."""
        return (f"Procesados: {self.processed_bookings}, "
                f"Creados: {self.created_reservations}, "
                f"Omitidos: {self.skipped_no_capacity + self.skipped_seat_taken + self.skipped_existing + self.skipped_exceptions}")

@dataclass
class TimeslotGroup(BaseModel):
    """
    Agrupamiento de plantillas de clase por horario recurrente.

    Representa un "horario único" que puede tener múltiples días de la semana.
    Por ejemplo: "Spinning — 08:00 (Sala A)" agrupa todas las plantillas de
    Spinning a las 8:00 AM en Sala A, sin importar el día de la semana.
    """
    key: str                                    # hash estable de la tupla de agrupación
    class_type_name: str                       # nombre del tipo de clase
    venue_name: str                            # nombre del venue/sala
    instructor_name: Optional[str]             # nombre del instructor (opcional)
    start_time_local: str                      # hora de inicio (ej: "08:00")
    template_ids: List[int] = field(default_factory=list)  # IDs de todas las plantillas del grupo
    templates: List[ClassTemplate] = field(default_factory=list)  # plantillas completas (opcional)

    def display_label(self) -> str:
        """
        Retorna la etiqueta para mostrar en combos.
        Formato: "{class_type_name} — {start_time_local} ({venue_name})"
        """
        return f"{self.class_type_name} — {self.start_time_local} ({self.venue_name})"

    def display_tooltip(self) -> str:
        """
        Retorna un tooltip con los días incluidos en el grupo.
        Formato: "Días: Lun, Mié, Vie"
        """
        if not self.templates:
            return f"Plantillas: {len(self.template_ids)} días"

        weekday_names = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
        days = []
        for template in self.templates:
            if hasattr(template, 'weekday') and template.weekday in weekday_names:
                day_name = weekday_names[template.weekday]
                if day_name not in days:
                    days.append(day_name)

        if days:
            return f"Días: {', '.join(sorted(days))}"
        return f"Plantillas: {len(self.template_ids)} días"

    def requires_seats(self) -> bool:
        """
        Determina si alguna plantilla del grupo requiere selección de asientos.
        """
        if self.templates:
            return any(template.requires_seats() for template in self.templates)

        # Fallback basado en el tipo de clase
        seat_requiring_types = ['spinning', 'spin', 'cycling', 'ciclismo']
        return any(
            seat_type in self.class_type_name.lower()
            for seat_type in seat_requiring_types
        )

    def get_weekdays(self) -> List[int]:
        """
        Retorna la lista de días de la semana (weekdays) incluidos en el grupo.
        """
        if self.templates:
            return [template.weekday for template in self.templates if hasattr(template, 'weekday')]
        return []

    def get_first_template(self) -> Optional[ClassTemplate]:
        """
        Retorna la primera plantilla del grupo (útil para obtener datos comunes).
        """
        return self.templates[0] if self.templates else None

    def template_for_weekday(self, weekday: int) -> Optional[ClassTemplate]:
        """Return the template scheduled for the given ISO weekday (1-7)."""
        if not self.templates:
            return None
        for template in self.templates:
            if getattr(template, "weekday", None) == weekday:
                return template
        return None

    def template_for_date(self, target_date: date) -> Optional[ClassTemplate]:
        """Resolve the template that matches (or the nearest after) the given date."""
        if not self.templates:
            return None
        weekday = target_date.isoweekday()
        exact = self.template_for_weekday(weekday)
        if exact is not None:
            return exact

        sortable = []
        for template in self.templates:
            tpl_weekday = getattr(template, "weekday", None)
            if tpl_weekday is None:
                continue
            delta = (tpl_weekday - weekday) % 7
            sortable.append((delta, template))

        if not sortable:
            return None

        sortable.sort(key=lambda item: item[0])
        return sortable[0][1]

    def supports_weekday(self, weekday: int) -> bool:
        """Return True if the group contains a template for the given weekday."""
        return self.template_for_weekday(weekday) is not None

# Enums for Standing Bookings
class StandingBookingStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELED = "canceled"

class ExceptionAction(Enum):
    SKIP = "skip"
    RESCHEDULE = "reschedule"

