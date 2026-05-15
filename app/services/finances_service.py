"""GraphQL adapter for the Finances tab (payments + metrics).

Reads go through ``CacheService`` (memory-only, short TTLs) and writes invalidate
the relevant patterns so the panel stays consistent without manual refresh.
"""
from typing import Any, Dict, Optional

from ..core import get_logger
from ..graphql.client import GraphQLClient
from .cache_service import CacheService

logger = get_logger(__name__)


# Cache TTLs (seconds). Short on purpose: payments are operational data, the
# user expects edits to show up almost immediately.
_PAYMENTS_LIST_TTL = 30
_PAYMENT_METRICS_TTL = 60


def _none_token(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


class FinancesService:
    def __init__(
        self,
        graphql_client: GraphQLClient,
        cache_service: Optional[CacheService] = None,
    ):
        self.client = graphql_client
        # CacheService is a singleton; if not injected we still get the same
        # in-memory cache as the rest of the app.
        self._cache = cache_service or CacheService()

    # ------------------------------------------------------------------ keys

    @staticmethod
    def _payments_list_key(
        *,
        limit: int,
        offset: int,
        search: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        status: Optional[str],
        method: Optional[str],
    ) -> str:
        return (
            "payments_list:"
            f"start={_none_token(start_date)}:end={_none_token(end_date)}:"
            f"status={_none_token(status)}:method={_none_token(method)}:"
            f"search={_none_token(search)}:limit={limit}:offset={offset}"
        )

    @staticmethod
    def _payment_metrics_key(
        *,
        start_date: Optional[str],
        end_date: Optional[str],
        status: Optional[str],
        method: Optional[str],
    ) -> str:
        return (
            "payment_metrics:"
            f"start={_none_token(start_date)}:end={_none_token(end_date)}:"
            f"status={_none_token(status)}:method={_none_token(method)}"
        )

    def _invalidate_caches(self) -> None:
        """Drop every cached payments list and metrics result."""
        self._cache.invalidate_pattern("payments_list:")
        self._cache.invalidate_pattern("payment_metrics:")

    # ------------------------------------------------------------------ reads

    async def get_payments(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch a page of payments + the total matching the filter set.

        Returns ``{"items": [...], "total": int}`` (already unwrapped).
        Cached in-memory for 30 s; mutations invalidate the cache.
        """
        cache_key = self._payments_list_key(
            limit=limit,
            offset=offset,
            search=search,
            start_date=start_date,
            end_date=end_date,
            status=status,
            method=method,
        )
        cached = self._cache.get(cache_key, max_age=_PAYMENTS_LIST_TTL)
        if cached is not None:
            return cached

        query = """
        query GetPayments(
            $limit: Int!,
            $offset: Int!,
            $search: String,
            $startDate: DateTime,
            $endDate: DateTime,
            $status: String,
            $method: String
        ) {
            payments(
                limit: $limit,
                offset: $offset,
                search: $search,
                startDate: $startDate,
                endDate: $endDate,
                status: $status,
                method: $method
            ) {
                total
                items {
                    id
                    personId
                    personName
                    amount
                    method
                    status
                    paidAt
                    comment
                }
            }
        }
        """
        variables = {
            "limit": limit,
            "offset": offset,
            "search": search,
            "startDate": start_date,
            "endDate": end_date,
            "status": status,
            "method": method,
        }
        result = await self.client.execute(query, variables)
        payload = (result or {}).get("payments") or {}
        unwrapped = {
            "items": payload.get("items", []),
            "total": int(payload.get("total", 0)),
        }
        # Memory-only cache: payments mutate often enough that on-disk
        # persistence across restarts would be misleading.
        self._cache.set(cache_key, unwrapped, persist=False)
        return unwrapped

    async def get_payment_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch aggregated metrics for the finances panel.

        Cached in-memory for 60 s.
        """
        cache_key = self._payment_metrics_key(
            start_date=start_date, end_date=end_date, status=status, method=method
        )
        cached = self._cache.get(cache_key, max_age=_PAYMENT_METRICS_TTL)
        if cached is not None:
            return cached

        query = """
        query GetPaymentMetrics(
            $startDate: DateTime,
            $endDate: DateTime,
            $status: String,
            $method: String
        ) {
            paymentMetrics(
                startDate: $startDate,
                endDate: $endDate,
                status: $status,
                method: $method
            ) {
                totalAmount
                totalCount
                avgAmount
                completedAmount
                pendingCount
                pendingAmount
                failedCount
                refundedCount
                orphanCount
                duplicateSuspectCount
                byMethod { method count total }
                byPlan { planId planName count total }
                byStatus { status count total }
                dailySeries { day count total }
            }
        }
        """
        variables = {
            "startDate": start_date,
            "endDate": end_date,
            "status": status,
            "method": method,
        }
        result = await self.client.execute(query, variables)
        metrics = (result or {}).get("paymentMetrics") or {}
        self._cache.set(cache_key, metrics, persist=False)
        return metrics

    # ------------------------------------------------------------------ writes

    async def update_payment(
        self,
        payment_id: int,
        amount: Optional[float] = None,
        method: Optional[str] = None,
        status: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing payment and invalidate the read caches."""
        mutation = """
        mutation UpdatePayment($input: UpdatePaymentInput!) {
            updatePayment(input: $input) {
                success
                message
                payment {
                    id
                    amount
                    method
                    status
                    comment
                }
            }
        }
        """
        input_data: Dict[str, Any] = {"paymentId": payment_id}
        if amount is not None:
            input_data["amount"] = amount
        if method is not None:
            input_data["method"] = method
        if status is not None:
            input_data["status"] = status
        if comment is not None:
            input_data["comment"] = comment

        variables = {"input": input_data}
        result = await self.client.execute(mutation, variables)
        self._invalidate_caches()
        return result

    async def delete_payment(self, payment_id: int) -> Dict[str, Any]:
        """Delete a payment and invalidate the read caches."""
        mutation = """
        mutation DeletePayment($paymentId: Int!) {
            deletePayment(paymentId: $paymentId) {
                success
                message
            }
        }
        """
        variables = {"paymentId": payment_id}
        result = await self.client.execute(mutation, variables)
        self._invalidate_caches()
        return result
