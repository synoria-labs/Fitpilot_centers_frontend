"""Servicio para la configuración del chatbot de WhatsApp (LangChain/Anthropic).

Envuelve la query/mutation GraphQL ``chatbotConfig`` / ``saveChatbotConfig`` que el backend
expone para editar, en tiempo real desde el frontend, el system prompt, la información de
negocio y los toggles del agente. Devuelve dicts normalizados (snake_case) para la vista.
"""
from typing import Any, Dict, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


_CONFIG_FIELDS = """
    id
    enabled
    requireConfirmation
    model
    systemPrompt
    businessName
    address
    operatingHours
    phone
    policies
    tone
    extraInfo
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
        "business_name": node.get("businessName") or "",
        "address": node.get("address") or "",
        "operating_hours": node.get("operatingHours") or "",
        "phone": node.get("phone") or "",
        "policies": node.get("policies") or "",
        "tone": node.get("tone") or "",
        "extra_info": node.get("extraInfo") or "",
    }


class ChatbotConfigService:
    """Servicio para leer/guardar la configuración del chatbot."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    async def get_config(self) -> Optional[Dict[str, Any]]:
        query = f"""
            query ChatbotConfig {{
                chatbotConfig {{
                    {_CONFIG_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query)
        if result and result.get("chatbotConfig") is not None:
            return _map_config(result["chatbotConfig"])
        return None

    async def save_config(
        self,
        enabled: bool,
        require_confirmation: bool,
        model: Optional[str],
        system_prompt: Optional[str],
        business_name: Optional[str] = None,
        address: Optional[str] = None,
        operating_hours: Optional[str] = None,
        phone: Optional[str] = None,
        policies: Optional[str] = None,
        tone: Optional[str] = None,
        extra_info: Optional[str] = None,
    ) -> Dict[str, Any]:
        mutation = f"""
            mutation SaveChatbotConfig($input: SaveChatbotConfigInput!) {{
                saveChatbotConfig(input: $input) {{
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
                "businessName": business_name,
                "address": address,
                "operatingHours": operating_hours,
                "phone": phone,
                "policies": policies,
                "tone": tone,
                "extraInfo": extra_info,
            }
        }
        result = await self.client.execute(mutation, variables)
        payload = (result or {}).get("saveChatbotConfig")
        if not payload:
            return {"success": False, "error": "Sin respuesta del servidor", "config": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "config": _map_config(payload.get("config")),
        }
