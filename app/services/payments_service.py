"""
Servicio para gestión de pagos y membresías.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ..core.logging import get_logger

logger = get_logger(__name__)

class PaymentsService:
    """Servicio para operaciones con pagos y membresías."""
    
    def __init__(self, graphql_client):
        self.client = graphql_client
    
    async def get_packages(self) -> List[Dict[str, Any]]:
        """Obtiene todas las membresias disponibles."""
        try:
            query = """
                query GetMembershipPlans {
                    membershipPlans {
                        id
                        name
                        price
                        description
                        durationValue
                        durationUnit
                        classLimit
                        fixedTimeSlot
                        maxSessionsPerDay
                        maxSessionsPerWeek
                    }
                }
            """

            result = await self.client.execute(query)

            if result and 'membershipPlans' in result:
                return result['membershipPlans']

            return []
            
        except Exception as e:
            logger.error(f"Error getting packages: {e}")
            return []
    
    async def create_payment(
        self,
        person_id: int,
        subscription_id: Optional[int],
        amount: float,
        method: str = "cash",
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Crea un nuevo pago."""
        try:
            mutation = """
                mutation CreatePayment($input: CreatePaymentInput!) {
                    createPayment(input: $input) {
                        success
                        payment {
                            id
                            amount
                            paidAt
                            method
                            provider
                            providerPaymentId
                            externalReference
                            status
                            comment
                            person {
                                id
                                fullName
                                email
                                phoneNumber
                            }
                            subscription {
                                id
                                startAt
                                endAt
                                status
                                plan {
                                    name
                                    price
                                }
                            }
                        }
                        message
                    }
                }
            """

            variables = {
                'input': {
                    'personId': person_id,
                    'subscriptionId': subscription_id,
                    'amount': amount,
                    'method': method,
                    'comment': comment,
                    'paidAt': datetime.now().isoformat()
                }
            }

            result = await self.client.execute(mutation, variables)

            if result and 'createPayment' in result:
                return result['createPayment']

            return {'success': False, 'message': 'Error al crear pago'}

        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return {'success': False, 'message': str(e)}
    
    async def get_payments(
        self,
        person_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Obtiene pagos con filtros opcionales."""
        try:
            # Ensure person_id is an integer if provided
            if person_id is not None:
                person_id = int(person_id)
            query = """
                query GetPayments(
                    $personId: Int
                    $startDate: DateTime
                    $endDate: DateTime
                    $limit: Int!
                    $offset: Int!
                ) {
                    payments(
                        personId: $personId
                        startDate: $startDate
                        endDate: $endDate
                        limit: $limit
                        offset: $offset
                    ) {
                        items {
                            id
                            amount
                            paidAt
                            method
                            provider
                            providerPaymentId
                            externalReference
                            status
                            comment
                            person {
                                id
                                fullName
                                email
                                phoneNumber
                            }
                            subscription {
                                id
                                startAt
                                endAt
                                status
                                plan {
                                    name
                                    price
                                }
                            }
                        }
                        total
                    }
                }
            """

            variables = {
                'personId': person_id,
                'startDate': start_date.isoformat() if start_date else None,
                'endDate': end_date.isoformat() if end_date else None,
                'limit': limit,
                'offset': offset
            }

            result = await self.client.execute(query, variables)

            if result and 'payments' in result:
                return result['payments']['items']

            return []

        except Exception as e:
            logger.error(f"Error getting payments: {e}")
            return []
    
    async def get_payment_by_id(self, payment_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Obtiene un pago por ID."""
        try:
            # Ensure payment_id is valid
            if payment_id is None:
                return None
            payment_id = int(payment_id)
            query = """
                query GetPayment($id: Int!) {
                    payment(id: $id) {
                        id
                        amount
                        paidAt
                        method
                        provider
                        providerPaymentId
                        externalReference
                        status
                        comment
                        person {
                            id
                            fullName
                            email
                            phoneNumber
                        }
                        subscription {
                            id
                            startAt
                            endAt
                            status
                            plan {
                                id
                                name
                                price
                                durationValue
                                durationUnit
                            }
                        }
                    }
                }
            """
            
            variables = {'id': payment_id}
            result = await self.client.execute(query, variables)
            
            if result and 'payment' in result:
                return result['payment']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting payment {payment_id}: {e}")
            return None
    
    async def cancel_payment(self, payment_id: Optional[int]) -> Dict[str, Any]:
        """Cancela un pago."""
        try:
            # Ensure payment_id is valid
            if payment_id is None:
                return {'success': False, 'message': 'Invalid payment ID'}
            payment_id = int(payment_id)
            mutation = """
                mutation CancelPayment($id: Int!) {
                    cancelPayment(id: $id) {
                        success
                        message
                    }
                }
            """
            
            variables = {'id': payment_id}
            result = await self.client.execute(mutation, variables)
            
            if result and 'cancelPayment' in result:
                return result['cancelPayment']
            
            return {'success': False, 'message': 'Error al cancelar pago'}
            
        except Exception as e:
            logger.error(f"Error canceling payment: {e}")
            return {'success': False, 'message': str(e)}
    
    async def renew_membership(
        self,
        person_id: int,
        plan_id: int,
        method: str = "cash"
    ) -> Dict[str, Any]:
        """Renueva la membresía de una persona."""
        try:
            mutation = """
                mutation RenewMembership($input: RenewMembershipInput!) {
                    renewMembership(input: $input) {
                        success
                        payment {
                            id
                            amount
                            paidAt
                        }
                        subscription {
                            startAt
                            endAt
                            status
                        }
                        message
                    }
                }
            """

            variables = {
                'input': {
                    'personId': person_id,
                    'planId': plan_id,
                    'method': method
                }
            }

            result = await self.client.execute(mutation, variables)

            if result and 'renewMembership' in result:
                return result['renewMembership']

            return {'success': False, 'message': 'Error al renovar membresía'}

        except Exception as e:
            logger.error(f"Error renewing membership: {e}")
            return {'success': False, 'message': str(e)}
    
    async def get_payment_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Obtiene un resumen de pagos."""
        try:
            if not start_date:
                # Por defecto, último mes
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()
            
            query = """
                query GetPaymentSummary($startDate: DateTime!, $endDate: DateTime!) {
                    paymentSummary(startDate: $startDate, endDate: $endDate) {
                        totalAmount
                        paymentCount
                        averagePayment
                        byMethod {
                            method
                            count
                            total
                        }
                        byPlan {
                            planName
                            count
                            total
                        }
                        dailyTotals {
                            date
                            total
                            count
                        }
                    }
                }
            """
            
            variables = {
                'startDate': start_date.isoformat(),
                'endDate': end_date.isoformat()
            }
            
            result = await self.client.execute(query, variables)
            
            if result and 'paymentSummary' in result:
                return result['paymentSummary']
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting payment summary: {e}")
            return {}
    
    async def get_expiring_subscriptions(
        self,
        days_before: int = 7
    ) -> List[Dict[str, Any]]:
        """Obtiene suscripciones próximas a vencer o vencidas."""
        try:
            query = """
                query GetExpiringSubscriptions($daysBefore: Int!) {
                    expiringSubscriptions(daysBefore: $daysBefore) {
                        personId
                        person {
                            fullName
                            phoneNumber
                            email
                        }
                        endAt
                        daysRemaining
                        plan {
                            name
                        }
                    }
                }
            """

            variables = {'daysBefore': days_before}
            result = await self.client.execute(query, variables)

            if result and 'expiringSubscriptions' in result:
                return result['expiringSubscriptions']

            return []

        except Exception as e:
            logger.error(f"Error getting expiring subscriptions: {e}")
            return []