"""GraphQL adapter for the cash register (caja) + corte de caja."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


_SESSION_FIELDS = """
    id
    openedBy
    openedAt
    openingFloat
    closedBy
    closedAt
    status
    expectedCash
    countedCash
    difference
    notes
"""

_REPORT_FIELDS = """
    sessionId
    status
    openedBy
    openedAt
    closedAt
    openingFloat
    salesCount
    salesTotal
    cashIn
    cashOut
    cashSalesTotal
    computedExpectedCash
    expectedCash
    countedCash
    difference
    byMethod { method count total }
"""


class CashRegisterService:
    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_open_cash_session(self) -> Optional[Dict[str, Any]]:
        query = """
            query OpenCashSession { openCashSession { %s } }
        """ % _SESSION_FIELDS
        try:
            result = await self.client.execute(query)
            return (result or {}).get("openCashSession")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching open cash session: %s", exc)
            return None

    async def get_cash_session_report(self, cash_session_id: int) -> Optional[Dict[str, Any]]:
        query = """
            query CashSessionReport($cashSessionId: Int!) {
                cashSessionReport(cashSessionId: $cashSessionId) { %s }
            }
        """ % _REPORT_FIELDS
        try:
            result = await self.client.execute(query, {"cashSessionId": int(cash_session_id)})
            return (result or {}).get("cashSessionReport")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching cash session report %s: %s", cash_session_id, exc)
            return None

    async def open_cash_session(
        self, opening_float: float = 0, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        mutation = """
            mutation OpenCashSession($input: OpenCashSessionInput!) {
                openCashSession(input: $input) {
                    success
                    message
                    session { %s }
                }
            }
        """ % _SESSION_FIELDS
        input_payload: Dict[str, Any] = {"openingFloat": float(opening_float or 0)}
        if notes:
            input_payload["notes"] = notes
        return await self._run_session_mutation(mutation, {"input": input_payload}, "openCashSession")

    async def close_cash_session(
        self, cash_session_id: int, counted_cash: float, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        mutation = """
            mutation CloseCashSession($input: CloseCashSessionInput!) {
                closeCashSession(input: $input) {
                    success
                    message
                    session { %s }
                }
            }
        """ % _SESSION_FIELDS
        input_payload: Dict[str, Any] = {
            "cashSessionId": int(cash_session_id),
            "countedCash": float(counted_cash or 0),
        }
        if notes:
            input_payload["notes"] = notes
        return await self._run_session_mutation(mutation, {"input": input_payload}, "closeCashSession")

    async def record_cash_movement(
        self,
        cash_session_id: int,
        direction: str,
        amount: float,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        mutation = """
            mutation RecordCashMovement($input: CashMovementInput!) {
                recordCashMovement(input: $input) {
                    success
                    message
                    movement { id direction amount reason createdAt }
                }
            }
        """
        input_payload: Dict[str, Any] = {
            "cashSessionId": int(cash_session_id),
            "direction": direction,
            "amount": float(amount or 0),
        }
        if reason:
            input_payload["reason"] = reason
        try:
            result = await self.client.execute(mutation, {"input": input_payload})
            payload = (result or {}).get("recordCashMovement") or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "movement": payload.get("movement"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error recording cash movement: %s", exc)
            return {"success": False, "message": str(exc), "movement": None}

    async def _run_session_mutation(
        self, mutation: str, variables: Dict[str, Any], root_field: str
    ) -> Dict[str, Any]:
        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get(root_field) or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "session": payload.get("session"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", root_field, exc)
            return {"success": False, "message": str(exc), "session": None}
