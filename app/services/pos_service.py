"""GraphQL adapter for the POS (sales / tickets)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from ..utils.datetime_helpers import format_iso_datetime

logger = get_logger(__name__)


_SALE_FIELDS = """
    id
    personId
    personName
    cashSessionId
    status
    subtotal
    total
    amountPaid
    changeDue
    note
    createdAt
    completedAt
    lineItems {
        id
        lineType
        description
        quantity
        unitPrice
        lineTotal
        planId
        subscriptionId
    }
    payments {
        id
        method
        amount
    }
"""


def _line_to_input(line: Dict[str, Any]) -> Dict[str, Any]:
    """Map a snake_case line dict to the GraphQL SaleLineInputType (camelCase)."""
    start_at = line.get("start_at")
    payload = {
        "lineType": line.get("line_type"),
        "description": line.get("description"),
        "quantity": int(line.get("quantity") or 1),
        "unitPrice": line.get("unit_price"),
        "discount": line.get("discount") or 0,
        "planId": line.get("plan_id"),
        "memberId": line.get("member_id"),
        "fullName": line.get("full_name"),
        "email": line.get("email"),
        "phoneNumber": line.get("phone_number"),
        "startAt": format_iso_datetime(start_at) if start_at else None,
        "templateId": line.get("template_id"),
        "seatId": line.get("seat_id"),
        "productId": line.get("product_id"),
    }
    return {k: v for k, v in payload.items() if v is not None}


def _tender_to_input(tender: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "method": tender.get("method"),
        "amount": float(tender.get("amount") or 0),
        "provider": tender.get("provider"),
        "providerPaymentId": tender.get("provider_payment_id"),
        "externalReference": tender.get("external_reference"),
    }
    return {k: v for k, v in payload.items() if v is not None}


class PosService:
    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def create_sale(
        self,
        line_items: List[Dict[str, Any]],
        payments: List[Dict[str, Any]],
        person_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        mutation = """
            mutation CreateSale($input: CreateSaleInput!) {
                createSale(input: $input) {
                    success
                    message
                    sale { %s }
                }
            }
        """ % _SALE_FIELDS

        input_payload: Dict[str, Any] = {
            "lineItems": [_line_to_input(li) for li in line_items],
            "payments": [_tender_to_input(t) for t in payments],
        }
        if person_id is not None:
            input_payload["personId"] = int(person_id)
        if note:
            input_payload["note"] = note

        try:
            result = await self.client.execute(mutation, {"input": input_payload})
            payload = (result or {}).get("createSale") or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "sale": payload.get("sale"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error creating sale: %s", exc, exc_info=True)
            return {"success": False, "message": str(exc), "sale": None}

    async def get_sales(
        self,
        limit: int = 100,
        offset: int = 0,
        cash_session_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            query GetSales(
                $limit: Int!, $offset: Int!, $cashSessionId: Int,
                $status: String, $startDate: DateTime, $endDate: DateTime
            ) {
                sales(
                    limit: $limit, offset: $offset, cashSessionId: $cashSessionId,
                    status: $status, startDate: $startDate, endDate: $endDate
                ) { %s }
            }
        """ % _SALE_FIELDS
        variables = {
            "limit": limit,
            "offset": offset,
            "cashSessionId": cash_session_id,
            "status": status,
            "startDate": start_date,
            "endDate": end_date,
        }
        try:
            result = await self.client.execute(query, variables)
            return (result or {}).get("sales") or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching sales: %s", exc)
            return []

    async def get_sale(self, sale_id: int) -> Optional[Dict[str, Any]]:
        query = """
            query GetSale($saleId: Int!) {
                sale(saleId: $saleId) { %s }
            }
        """ % _SALE_FIELDS
        try:
            result = await self.client.execute(query, {"saleId": int(sale_id)})
            return (result or {}).get("sale")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching sale %s: %s", sale_id, exc)
            return None

    async def void_sale(self, sale_id: int) -> Dict[str, Any]:
        mutation = """
            mutation VoidSale($saleId: Int!) {
                voidSale(saleId: $saleId) {
                    success
                    message
                    sale { id status }
                }
            }
        """
        try:
            result = await self.client.execute(mutation, {"saleId": int(sale_id)})
            payload = (result or {}).get("voidSale") or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "sale": payload.get("sale"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error voiding sale %s: %s", sale_id, exc)
            return {"success": False, "message": str(exc), "sale": None}
