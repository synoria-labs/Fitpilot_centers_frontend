"""Service layer for role-capability management (GraphQL)."""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.logging import get_logger

logger = get_logger(__name__)


class PermissionsService:
    """GraphQL operations to read and edit per-role capability grants."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_role_capabilities(self) -> Dict[str, Any]:
        """Return the role/capability matrix plus the catalog of capabilities."""
        query = """
            query RoleCapabilities {
                roleCapabilities {
                    roleCode
                    roleDescription
                    capabilities
                    locked
                }
                allCapabilities
            }
        """
        try:
            result = await self.client.execute(query)
            if result is None:
                return {"roles": [], "capabilities": []}
            roles = result.get("roleCapabilities", []) or []
            capabilities = result.get("allCapabilities", []) or []
            return {
                "roles": [
                    {
                        "role_code": r.get("roleCode"),
                        "role_description": r.get("roleDescription"),
                        "capabilities": list(r.get("capabilities") or []),
                        "locked": bool(r.get("locked")),
                    }
                    for r in roles
                ],
                "capabilities": list(capabilities),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching role capabilities: %s", exc, exc_info=True)
            return {"roles": [], "capabilities": []}

    async def grant(self, role_code: str, capability: str) -> Dict[str, Any]:
        return await self._toggle("grantRoleCapability", role_code, capability)

    async def revoke(self, role_code: str, capability: str) -> Dict[str, Any]:
        return await self._toggle("revokeRoleCapability", role_code, capability)

    async def _toggle(self, root_field: str, role_code: str, capability: str) -> Dict[str, Any]:
        mutation = """
            mutation %s($roleCode: String!, $capability: String!) {
                %s(roleCode: $roleCode, capability: $capability) {
                    success
                    message
                }
            }
        """ % (root_field[0].upper() + root_field[1:], root_field)

        variables = {"roleCode": role_code, "capability": capability}
        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get(root_field) or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", root_field, exc)
            return {"success": False, "message": str(exc)}
