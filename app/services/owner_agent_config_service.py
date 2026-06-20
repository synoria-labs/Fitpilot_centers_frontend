"""GraphQL service for the owner/admin WhatsApp agent configuration."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


_CONFIG_FIELDS = """
    id
    enabled
    requireConfirmation
    model
    systemPrompt
    historyLimit
    maxTokens
    serverEnabled
"""

_PHONE_FIELDS = """
    id
    label
    phoneNumber
    normalizedWaId
    enabled
    createdBy
"""


def _map_config(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "enabled": bool(node.get("enabled")),
        "require_confirmation": bool(node.get("requireConfirmation")),
        "model": node.get("model") or "claude-sonnet-4-6",
        "system_prompt": node.get("systemPrompt") or "",
        "history_limit": int(node.get("historyLimit") or 30),
        "max_tokens": int(node.get("maxTokens") or 1024),
        "server_enabled": bool(node.get("serverEnabled")),
    }


def _map_phone(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "label": node.get("label") or "",
        "phone_number": node.get("phoneNumber") or "",
        "normalized_wa_id": node.get("normalizedWaId") or "",
        "enabled": bool(node.get("enabled")),
        "created_by": node.get("createdBy"),
    }


class OwnerAgentConfigService:
    """Read/write owner-agent configuration through GraphQL."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_config_bundle(self) -> Dict[str, Any]:
        query = f"""
            query OwnerAgentConfigBundle {{
                ownerAgentConfig {{ {_CONFIG_FIELDS} }}
                ownerAgentAuthorizedPhones {{ {_PHONE_FIELDS} }}
            }}
        """
        result = await self.client.execute(query)
        return {
            "config": _map_config((result or {}).get("ownerAgentConfig")),
            "phones": [
                phone
                for phone in (
                    _map_phone(node)
                    for node in ((result or {}).get("ownerAgentAuthorizedPhones") or [])
                )
                if phone is not None
            ],
        }

    async def save_config(
        self,
        *,
        enabled: bool,
        require_confirmation: bool,
        model: Optional[str],
        system_prompt: Optional[str],
        history_limit: int,
        max_tokens: int,
    ) -> Dict[str, Any]:
        mutation = f"""
            mutation SaveOwnerAgentConfig($input: SaveOwnerAgentConfigInput!) {{
                saveOwnerAgentConfig(input: $input) {{
                    success
                    error
                    config {{ {_CONFIG_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "enabled": enabled,
                "requireConfirmation": require_confirmation,
                "model": model,
                "systemPrompt": system_prompt,
                "historyLimit": history_limit,
                "maxTokens": max_tokens,
            }
        }
        result = await self.client.execute(mutation, variables)
        payload = (result or {}).get("saveOwnerAgentConfig") or {}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "config": _map_config(payload.get("config")),
        }

    async def add_phone(
        self, *, label: str, phone_number: str, enabled: bool = True
    ) -> Dict[str, Any]:
        mutation = f"""
            mutation AddOwnerAgentPhone($input: AddOwnerAgentAuthorizedPhoneInput!) {{
                addOwnerAgentAuthorizedPhone(input: $input) {{
                    success
                    error
                    phone {{ {_PHONE_FIELDS} }}
                }}
            }}
        """
        result = await self.client.execute(
            mutation,
            {"input": {"label": label, "phoneNumber": phone_number, "enabled": enabled}},
        )
        payload = (result or {}).get("addOwnerAgentAuthorizedPhone") or {}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "phone": _map_phone(payload.get("phone")),
        }

    async def update_phone(
        self,
        *,
        phone_id: int,
        label: Optional[str] = None,
        phone_number: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        mutation = f"""
            mutation UpdateOwnerAgentPhone($input: UpdateOwnerAgentAuthorizedPhoneInput!) {{
                updateOwnerAgentAuthorizedPhone(input: $input) {{
                    success
                    error
                    phone {{ {_PHONE_FIELDS} }}
                }}
            }}
        """
        payload: Dict[str, Any] = {"phoneId": int(phone_id)}
        if label is not None:
            payload["label"] = label
        if phone_number is not None:
            payload["phoneNumber"] = phone_number
        if enabled is not None:
            payload["enabled"] = bool(enabled)
        result = await self.client.execute(mutation, {"input": payload})
        node = (result or {}).get("updateOwnerAgentAuthorizedPhone") or {}
        return {
            "success": bool(node.get("success")),
            "error": node.get("error"),
            "phone": _map_phone(node.get("phone")),
        }

    async def disable_phone(self, *, phone_id: int) -> Dict[str, Any]:
        mutation = f"""
            mutation DisableOwnerAgentPhone($phoneId: Int!) {{
                disableOwnerAgentAuthorizedPhone(phoneId: $phoneId) {{
                    success
                    error
                    phone {{ {_PHONE_FIELDS} }}
                }}
            }}
        """
        result = await self.client.execute(mutation, {"phoneId": int(phone_id)})
        payload = (result or {}).get("disableOwnerAgentAuthorizedPhone") or {}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "phone": _map_phone(payload.get("phone")),
        }
