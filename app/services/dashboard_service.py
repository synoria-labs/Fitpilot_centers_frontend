"""
Servicio para métricas y dashboard.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from ..core.logging import get_logger

logger = get_logger(__name__)

class DashboardService:
    """Servicio para obtener métricas del dashboard."""
    
    def __init__(self, graphql_client):
        self.client = graphql_client
    
    async def get_general_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas generales del negocio."""
        try:
            query = """
                query GetDashboardMetrics {
                    dashboardMetrics {
                        total_socios
                        socios_activos
                        ingresos_mes_actual
                        ingresos_mes_anterior
                        reservas_hoy
                        reservas_semana
                        ocupacion_promedio
                        nuevos_socios_mes
                        tasa_renovacion
                        clases_mas_populares {
                            clase
                            promedio_asistencia
                        }
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'dashboardMetrics' in result:
                return result['dashboardMetrics']
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting dashboard metrics: {e}")
            return {}
    
    async def get_revenue_chart(
        self,
        period: str = "monthly",
        months: int = 6
    ) -> Dict[str, Any]:
        """Obtiene datos para gráfica de ingresos."""
        try:
            query = """
                query GetRevenueChart($period: String!, $months: Int!) {
                    revenueChart(period: $period, months: $months) {
                        labels
                        datasets {
                            label
                            data
                            backgroundColor
                            borderColor
                        }
                    }
                }
            """
            
            variables = {
                'period': period,
                'months': months
            }
            
            result = await self.client.execute(query, variables)
            
            if result and 'revenueChart' in result:
                return result['revenueChart']
            
            return {'labels': [], 'datasets': []}
            
        except Exception as e:
            logger.error(f"Error getting revenue chart: {e}")
            return {'labels': [], 'datasets': []}
    
    async def get_occupancy_chart(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """Obtiene datos de ocupación por clase."""
        try:
            query = """
                query GetOccupancyChart($days: Int!) {
                    occupancyChart(days: $days) {
                        labels
                        datasets {
                            label
                            data
                            backgroundColor
                            borderColor
                        }
                    }
                }
            """
            
            variables = {'days': days}
            result = await self.client.execute(query, variables)
            
            if result and 'occupancyChart' in result:
                return result['occupancyChart']
            
            return {'labels': [], 'datasets': []}
            
        except Exception as e:
            logger.error(f"Error getting occupancy chart: {e}")
            return {'labels': [], 'datasets': []}
    
    async def get_members_distribution(self) -> Dict[str, Any]:
        """Obtiene distribución de membresías."""
        try:
            query = """
                query GetMembersDistribution {
                    membersDistribution {
                        labels
                        data
                        colors
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'membersDistribution' in result:
                return result['membersDistribution']
            
            return {'labels': [], 'data': [], 'colors': []}
            
        except Exception as e:
            logger.error(f"Error getting members distribution: {e}")
            return {'labels': [], 'data': [], 'colors': []}
    
    async def get_attendance_trends(
        self,
        weeks: int = 4
    ) -> Dict[str, Any]:
        """Obtiene tendencias de asistencia."""
        try:
            query = """
                query GetAttendanceTrends($weeks: Int!) {
                    attendanceTrends(weeks: $weeks) {
                        week_labels
                        by_day {
                            day
                            attendances
                        }
                        by_hour {
                            hour
                            average_attendance
                        }
                    }
                }
            """
            
            variables = {'weeks': weeks}
            result = await self.client.execute(query, variables)
            
            if result and 'attendanceTrends' in result:
                return result['attendanceTrends']
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting attendance trends: {e}")
            return {}
    
    async def get_payment_methods_summary(self) -> List[Dict[str, Any]]:
        """Obtiene resumen de métodos de pago."""
        try:
            query = """
                query GetPaymentMethodsSummary {
                    paymentMethodsSummary {
                        method
                        count
                        total_amount
                        percentage
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'paymentMethodsSummary' in result:
                return result['paymentMethodsSummary']
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting payment methods summary: {e}")
            return []
    
    async def get_alerts(self) -> List[Dict[str, Any]]:
        """Obtiene alertas y notificaciones importantes."""
        try:
            query = """
                query GetAlerts {
                    alerts {
                        id
                        type
                        severity
                        title
                        message
                        created_at
                        action_required
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'alerts' in result:
                return result['alerts']
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return []
    
    async def get_quick_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas rápidas para el header."""
        try:
            query = """
                query GetQuickStats {
                    quickStats {
                        active_now
                        next_class_time
                        next_class_occupancy
                        pending_payments
                        expiring_members
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'quickStats' in result:
                return result['quickStats']
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting quick stats: {e}")
            return {}
