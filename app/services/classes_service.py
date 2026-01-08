"""
Servicio moderno para gestión de clases y reservas.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ..core.logging import get_logger

logger = get_logger(__name__)

class ClassesService:
    """Servicio para operaciones con clases y reservas usando la nueva API."""

    def __init__(self, graphql_client):
        self.client = graphql_client
    
    async def get_available_sessions(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        class_type_id: Optional[int] = None,
        venue_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene sesiones disponibles con información de capacidad.

        Args:
            start_date: Fecha de inicio (por defecto, ahora)
            end_date: Fecha final (por defecto, 7 días adelante)
            class_type_id: Filtro por tipo de clase
            venue_id: Filtro por venue
        """
        try:
            if not start_date:
                start_date = datetime.now()
            if not end_date:
                end_date = start_date + timedelta(days=7)

            query = """
                query GetAvailableSessions($input: GetSessionsInput!) {
                    availableSessions(input: $input) {
                        sessions {
                            id
                            name
                            startAt
                            endAt
                            capacity
                            availableSpots
                            reservedCount
                            classTypeName
                            venueName
                            instructorName
                        }
                        totalCount
                    }
                }
            """

            variables = {
                'input': {
                    'startDate': start_date.isoformat(),
                    'endDate': end_date.isoformat(),
                    'classTypeId': class_type_id,
                    'venueId': venue_id
                }
            }

            result = await self.client.execute(query, variables)

            if result and 'availableSessions' in result:
                return result['availableSessions']['sessions']

            return []

        except Exception as e:
            logger.error(f"Error getting available sessions: {e}")
            return []
    
    async def get_available_seats(
        self,
        session_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtiene asientos disponibles para una sesión específica.

        Args:
            session_id: ID de la sesión
        """
        try:
            query = """
                query GetAvailableSeats($sessionId: Int!) {
                    availableSeats(sessionId: $sessionId) {
                        seats {
                            id
                            label
                            venueId
                            isActive
                            seatTypeName
                            isAvailable
                        }
                        availableCount
                        totalCount
                    }
                }
            """

            variables = {
                'sessionId': session_id
            }

            result = await self.client.execute(query, variables)

            if result and 'availableSeats' in result:
                return result['availableSeats']['seats']

            return []

        except Exception as e:
            logger.error(f"Error getting available seats: {e}")
            return []
    
    async def create_reservation(
        self,
        session_id: int,
        person_id: int,
        seat_id: Optional[int] = None,
        source: str = "manual"
    ) -> Dict[str, Any]:
        """Crea una nueva reserva moderna."""
        try:
            mutation = """
                mutation CreateReservation($input: CreateReservationInput!) {
                    createReservation(input: $input) {
                        success
                        reservation {
                            id
                            sessionId
                            personId
                            seatId
                            status
                            reservedAt
                            personName
                            seatLabel
                            sessionName
                            sessionStart
                            sessionEnd
                        }
                        message
                    }
                }
            """

            variables = {
                'input': {
                    'sessionId': session_id,
                    'personId': person_id,
                    'seatId': seat_id,
                    'source': source
                }
            }

            result = await self.client.execute(mutation, variables)

            if result and 'createReservation' in result:
                return result['createReservation']

            return {'success': False, 'message': 'Error al crear reserva'}

        except Exception as e:
            logger.error(f"Error creating reservation: {e}")
            return {'success': False, 'message': str(e)}
    
    async def cancel_reservation(self, reservation_id: int) -> Dict[str, Any]:
        """Cancela una reserva existente."""
        try:
            # Ensure reservation_id is an integer
            if reservation_id is None:
                return {'success': False, 'message': 'Invalid reservation ID'}

            try:
                reservation_id_int = int(reservation_id)
            except (TypeError, ValueError):
                logger.error(f"Invalid reservation ID: {reservation_id}")
                return {'success': False, 'message': 'Invalid reservation ID'}

            mutation = """
                mutation CancelReservation($reservationId: Int!) {
                    cancelReservation(reservationId: $reservationId) {
                        success
                        reservation {
                            id
                            status
                        }
                        message
                    }
                }
            """

            variables = {'reservationId': reservation_id_int}
            result = await self.client.execute(mutation, variables)

            if result and 'cancelReservation' in result:
                return result['cancelReservation']

            return {'success': False, 'message': 'Error al cancelar reserva'}

        except Exception as e:
            logger.error(f"Error canceling reservation {reservation_id}: {e}")
            return {'success': False, 'message': str(e)}
    
    async def get_person_reservations(
        self,
        person_id: int,
        include_past: bool = False,
        include_canceled: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Obtiene las reservas de una persona."""
        try:
            # Ensure person_id is an integer
            if person_id is None:
                return []

            try:
                person_id_int = int(person_id)
            except (TypeError, ValueError):
                logger.error(f"Invalid person ID: {person_id}")
                return []

            query = """
                query GetPersonReservations($personId: Int!, $includePast: Boolean!, $includeCanceled: Boolean!, $limit: Int!) {
                    personReservations(personId: $personId, includePast: $includePast, includeCanceled: $includeCanceled, limit: $limit) {
                        id
                        sessionId
                        personId
                        seatId
                        status
                        reservedAt
                        checkinAt
                        checkoutAt
                        source
                        personName
                        seatLabel
                        sessionName
                        sessionStart
                        sessionEnd
                    }
                }
            """

            variables = {
                'personId': person_id_int,
                'includePast': include_past,
                'includeCanceled': include_canceled,
                'limit': limit
            }

            result = await self.client.execute(query, variables)

            if result and 'personReservations' in result:
                return result['personReservations']

            return []

        except Exception as e:
            logger.error(f"Error getting person reservations: {e}")
            return []
    
    async def get_class_occupancy(
        self,
        fecha: datetime
    ) -> List[Dict[str, Any]]:
        """Obtiene la ocupación de todas las clases en una fecha."""
        try:
            query = """
                query GetClassOccupancy($fecha: DateTime!) {
                    classOccupancy(fecha: $fecha) {
                        class_id
                        hora
                        descripcion
                        total_lugares
                        lugares_ocupados
                        porcentaje_ocupacion
                        reservas_count
                    }
                }
            """
            
            variables = {'fecha': fecha.isoformat()}
            result = await self.client.execute(query, variables)
            
            if result and 'classOccupancy' in result:
                return result['classOccupancy']
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting class occupancy: {e}")
            return []
    
    async def check_in_reservation(
        self,
        reservation_id: int
    ) -> Dict[str, Any]:
        """Marca el check-in de una reserva."""
        try:
            mutation = """
                mutation CheckInReservation($reservationId: Int!) {
                    checkInReservation(reservationId: $reservationId) {
                        success
                        checkinTime
                        message
                    }
                }
            """

            variables = {'reservationId': reservation_id}
            result = await self.client.execute(mutation, variables)

            if result and 'checkInReservation' in result:
                return result['checkInReservation']

            return {'success': False, 'message': 'Error al registrar check-in'}

        except Exception as e:
            logger.error(f"Error checking in reservation: {e}")
            return {'success': False, 'message': str(e)}

    async def checkout_reservation(
        self,
        reservation_id: int
    ) -> Dict[str, Any]:
        """Marca el check-out de una reserva."""
        try:
            mutation = """
                mutation CheckoutReservation($reservationId: Int!) {
                    checkoutReservation(reservationId: $reservationId) {
                        success
                        checkinTime
                        message
                    }
                }
            """

            variables = {'reservationId': reservation_id}
            result = await self.client.execute(mutation, variables)

            if result and 'checkoutReservation' in result:
                return result['checkoutReservation']

            return {'success': False, 'message': 'Error al registrar check-out'}

        except Exception as e:
            logger.error(f"Error checking out reservation: {e}")
            return {'success': False, 'message': str(e)}
    
    async def get_upcoming_sessions(
        self,
        days_ahead: int = 7,
        class_type_id: Optional[int] = None,
        venue_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Obtiene sesiones próximas."""
        try:
            query = """
                query GetUpcomingSessions($daysAhead: Int!, $classTypeId: Int, $venueId: Int) {
                    upcomingSessions(daysAhead: $daysAhead, classTypeId: $classTypeId, venueId: $venueId) {
                        id
                        name
                        startAt
                        endAt
                        capacity
                        availableSpots
                        reservedCount
                        classTypeName
                        venueName
                        instructorName
                    }
                }
            """

            variables = {
                'daysAhead': days_ahead,
                'classTypeId': class_type_id,
                'venueId': venue_id
            }

            result = await self.client.execute(query, variables)

            if result and 'upcomingSessions' in result:
                return result['upcomingSessions']

            return []

        except Exception as e:
            logger.error(f"Error getting upcoming sessions: {e}")
            return []


    async def get_sessions_with_seats(
        self,
        *,
        date,
        venue_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Obtiene sesiones de un día con el estado de cada asiento y flag de vencimiento próximo."""
        try:
            query = """
                query SessionsWithSeats($date: Date!, $venueId: Int) {
                    sessionsWithSeats(date: $date, venueId: $venueId) {
                        id
                        name
                        startAt
                        endAt
                        capacity
                        venueId
                        templateId
                        classTypeName
                        seats {
                            seatId
                            label
                            status
                            willExpireSoon
                            occupant {
                                personId
                                fullName
                            }
                        }
                    }
                }
            """

            variables = {
                'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                'venueId': venue_id
            }

            result = await self.client.execute(query, variables)
            return (result or {}).get('sessionsWithSeats') or []
        except Exception as e:
            logger.error(f"Error getting sessions with seats: {e}")
            return []

    async def get_week_sessions_with_seats(
        self,
        *,
        start_date,
        end_date,
        class_type_id: Optional[int] = None,
        venue_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene sesiones de un rango de fechas (semana) con el estado de cada asiento.

        Args:
            start_date: Fecha de inicio de la semana
            end_date: Fecha de fin de la semana
            class_type_id: ID del tipo de clase para filtrar (opcional)
            venue_id: ID del venue para filtrar (opcional)

        Returns:
            Lista de sesiones con información de asientos
        """
        try:
            query = """
                query WeekSessionsWithSeats(
                    $startDate: Date!,
                    $endDate: Date!,
                    $classTypeId: Int,
                    $venueId: Int
                ) {
                    weekSessionsWithSeats(
                        startDate: $startDate,
                        endDate: $endDate,
                        classTypeId: $classTypeId,
                        venueId: $venueId
                    ) {
                        id
                        name
                        startAt
                        endAt
                        capacity
                        venueId
                        templateId
                        classTypeName
                        seats {
                            seatId
                            label
                            status
                            willExpireSoon
                            occupant {
                                personId
                                fullName
                            }
                        }
                    }
                }
            """

            variables = {
                'startDate': start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
                'endDate': end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date),
                'classTypeId': class_type_id,
                'venueId': venue_id
            }

            result = await self.client.execute(query, variables)
            return (result or {}).get('weekSessionsWithSeats') or []
        except Exception as e:
            logger.error(f"Error getting week sessions with seats: {e}")
            return []


