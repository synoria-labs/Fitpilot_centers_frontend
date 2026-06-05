"""
Servicio para gestión de plantillas WhatsApp (Meta Cloud API).

Envuelve las queries/mutations GraphQL del backend para administrar las plantillas
(`app.whatsapp_templates`) con sincronización a Meta y envío de prueba de plantillas
aprobadas. Devuelve dicts normalizados (snake_case) para el controller/vista.
"""
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


# Campos comunes que pedimos para una plantilla.
_TEMPLATE_FIELDS = """
    id
    templateName
    templateNamespace
    templateLanguage
    templateStatus
    category
    metaTemplateId
    components
    createdAt
    updatedAt
"""


def _map_template(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normaliza un nodo GraphQL (camelCase) a dict snake_case para la UI."""
    if not node:
        return None
    return {
        "id": node.get("id"),
        "template_name": node.get("templateName"),
        "template_namespace": node.get("templateNamespace"),
        "template_language": node.get("templateLanguage"),
        "template_status": node.get("templateStatus"),
        "category": node.get("category"),
        "meta_template_id": node.get("metaTemplateId"),
        "components": node.get("components"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
    }


class WhatsAppService:
    """Servicio para operaciones con plantillas de WhatsApp."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    async def get_templates(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene las plantillas almacenadas localmente."""
        query = f"""
            query GetTemplates($search: String) {{
                whatsappTemplates(search: $search) {{
                    {_TEMPLATE_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query, {"search": search})
        if result and result.get("whatsappTemplates") is not None:
            return [_map_template(n) for n in result["whatsappTemplates"]]
        return []

    async def sync_templates(self) -> List[Dict[str, Any]]:
        """Sincroniza desde Meta y devuelve la lista local actualizada."""
        mutation = f"""
            mutation SyncTemplates {{
                syncWhatsappTemplates {{
                    {_TEMPLATE_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(mutation)
        if result and result.get("syncWhatsappTemplates") is not None:
            return [_map_template(n) for n in result["syncWhatsappTemplates"]]
        return []

    async def create_template(
        self,
        name: str,
        language: str,
        category: str,
        body_text: str,
        body_examples: Optional[List[str]] = None,
        footer_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Crea una plantilla en Meta y la guarda localmente."""
        mutation = f"""
            mutation CreateTemplate($input: CreateTemplateInput!) {{
                createWhatsappTemplate(input: $input) {{
                    success
                    error
                    template {{ {_TEMPLATE_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "name": name,
                "language": language,
                "category": category,
                "bodyText": body_text,
                "bodyExamples": body_examples or [],
                "footerText": footer_text,
            }
        }
        result = await self.client.execute(mutation, variables)
        return self._map_result(result, "createWhatsappTemplate")

    async def update_template(
        self,
        template_id: int,
        body_text: str,
        body_examples: Optional[List[str]] = None,
        footer_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edita los components de una plantilla (Meta vuelve a revisar -> PENDING)."""
        mutation = f"""
            mutation UpdateTemplate($input: UpdateTemplateInput!) {{
                updateWhatsappTemplate(input: $input) {{
                    success
                    error
                    template {{ {_TEMPLATE_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "id": template_id,
                "bodyText": body_text,
                "bodyExamples": body_examples or [],
                "footerText": footer_text,
            }
        }
        result = await self.client.execute(mutation, variables)
        return self._map_result(result, "updateWhatsappTemplate")

    async def delete_template(self, template_id: int) -> Dict[str, Any]:
        """Elimina la plantilla en Meta y localmente."""
        mutation = """
            mutation DeleteTemplate($id: Int!) {
                deleteWhatsappTemplate(id: $id) {
                    success
                    error
                }
            }
        """
        result = await self.client.execute(mutation, {"id": template_id})
        return self._map_result(result, "deleteWhatsappTemplate")

    async def send_template_test(
        self,
        phone: str,
        template_id: int,
        body_params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Envía una plantilla aprobada al número indicado."""
        mutation = """
            mutation SendTemplateTest($input: SendTemplateTestInput!) {
                sendTemplateTest(input: $input) {
                    success
                    error
                    message { id waMessageId }
                }
            }
        """
        variables = {
            "input": {
                "phone": phone,
                "templateId": template_id,
                "bodyParams": body_params or [],
            }
        }
        result = await self.client.execute(mutation, variables)
        if result and result.get("sendTemplateTest") is not None:
            return result["sendTemplateTest"]
        return {"success": False, "error": "Error al enviar la plantilla"}

    @staticmethod
    def _map_result(result: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
        """Normaliza un *Result (success/error/template) a dict para la UI."""
        payload = result.get(key) if result else None
        if not payload:
            return {"success": False, "error": "Sin respuesta del servidor", "template": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "template": _map_template(payload.get("template")),
        }
