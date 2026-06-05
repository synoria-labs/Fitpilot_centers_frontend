"""GraphQL adapter for the Dashboard tab.

Single ``get_dashboard_metrics`` method that fetches all 6 KPIs + the 4 chart
series in one round trip. Caches by (start, end) for 60 s via ``CacheService``.

The previous version of this file held 8 GraphQL queries (GetDashboardMetrics,
GetRevenueChart, GetOccupancyChart, etc.) that referenced operations the
backend never implemented; that dead code is replaced.
"""
from typing import Any, Dict, Optional

from ..core.logging import get_logger
from ..graphql.client import GraphQLClient
from .cache_service import CacheService

logger = get_logger(__name__)


_DASHBOARD_METRICS_TTL = 60  # seconds


def _none_token(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


class DashboardService:
    def __init__(
        self,
        graphql_client: GraphQLClient,
        cache_service: Optional[CacheService] = None,
    ):
        self.client = graphql_client
        self._cache = cache_service or CacheService()

    @staticmethod
    def _metrics_cache_key(
        *, start_date: Optional[str], end_date: Optional[str]
    ) -> str:
        return (
            "dashboard_metrics:"
            f"start={_none_token(start_date)}:end={_none_token(end_date)}"
        )

    def invalidate(self) -> None:
        """Drop every cached dashboard metrics result.

        Public hook for upstream services that mutate domain data the dashboard
        summarizes (payments, subscriptions, members). Wiring is left to the
        consumers.
        """
        self._cache.invalidate_pattern("dashboard_metrics:")

    async def get_dashboard_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch all dashboard KPIs + chart series.

        Returns the inner ``dashboardMetrics`` object as a dict. Cached
        in-memory for 60 s.
        """
        cache_key = self._metrics_cache_key(start_date=start_date, end_date=end_date)
        cached = self._cache.get(cache_key, max_age=_DASHBOARD_METRICS_TTL)
        if cached is not None:
            return cached

        query = """
        query GetDashboardMetrics(
            $startDate: DateTime,
            $endDate: DateTime
        ) {
            dashboardMetrics(
                startDate: $startDate,
                endDate: $endDate
            ) {
                totalMembers
                activeMembers
                newMembers
                periodReservations
                periodRevenue
                avgOccupancy
                totalMembersPrev
                activeMembersPrev
                newMembersPrev
                reservationsPrev
                revenuePrev
                avgOccupancyPrev
                revenueByDay { day count total }
                occupancyByClass { className capacity reserved occupancyPct }
                newMembersByDay { day count total }
                membershipDistribution { planId planName count total }
            }
        }
        """
        variables = {"startDate": start_date, "endDate": end_date}
        result = await self.client.execute(query, variables)
        metrics = (result or {}).get("dashboardMetrics") or {}
        self._cache.set(cache_key, metrics, persist=False)
        return metrics
