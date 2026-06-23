"""GraphQL adapter for the product catalog / inventory."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)

_PRODUCT_FIELDS = "id name sku price trackStock stockQty isActive"


class ProductsService:
    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_products(
        self, include_inactive: bool = True, search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
            query Products($includeInactive: Boolean!, $search: String) {
                products(includeInactive: $includeInactive, search: $search) { %s }
            }
        """ % _PRODUCT_FIELDS
        try:
            result = await self.client.execute(
                query, {"includeInactive": include_inactive, "search": search}
            )
            return (result or {}).get("products") or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching products: %s", exc)
            return []

    async def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation CreateProduct($input: CreateProductInput!) {
                createProduct(input: $input) { success message product { %s } }
            }
        """ % _PRODUCT_FIELDS
        return await self._run(mutation, {"input": self._input(data)}, "createProduct")

    async def update_product(self, product_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation UpdateProduct($input: UpdateProductInput!) {
                updateProduct(input: $input) { success message product { %s } }
            }
        """ % _PRODUCT_FIELDS
        payload = self._input(data)
        payload["productId"] = int(product_id)
        return await self._run(mutation, {"input": payload}, "updateProduct")

    async def set_product_active(self, product_id: int, is_active: bool) -> Dict[str, Any]:
        mutation = """
            mutation SetProductActive($productId: Int!, $isActive: Boolean!) {
                setProductActive(productId: $productId, isActive: $isActive) {
                    success message product { %s }
                }
            }
        """ % _PRODUCT_FIELDS
        return await self._run(
            mutation, {"productId": int(product_id), "isActive": bool(is_active)}, "setProductActive"
        )

    @staticmethod
    def _input(data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "name": data.get("name"),
            "price": float(data.get("price") or 0),
            "sku": data.get("sku") or None,
            "trackStock": bool(data.get("track_stock")),
            "stockQty": data.get("stock_qty"),
        }
        if "is_active" in data and data.get("is_active") is not None:
            payload["isActive"] = bool(data.get("is_active"))
        return {k: v for k, v in payload.items() if v is not None or k in ("sku", "stockQty")}

    async def _run(self, mutation: str, variables: Dict[str, Any], root: str) -> Dict[str, Any]:
        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get(root) or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "product": payload.get("product"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", root, exc)
            return {"success": False, "message": str(exc), "product": None}
