"""
Servicio para la configuración de notificaciones automáticas de WhatsApp.

Envuelve las queries/mutations GraphQL del backend que asocian cada evento de negocio
(nuevo registro, recordatorio de renovación, confirmación de renovación, membresía vencida)
con una plantilla aprobada de Meta y un mapeo de variables editable desde el frontend.
Devuelve dicts normalizados (snake_case) para el controller/vista.
"""
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


_TEMPLATE_FIELDS = """
    id
    templateName
    templateLanguage
    templateStatus
    category
    metaTemplateId
    defaultHeaderMediaAssetId
    components
"""

_MEDIA_ASSET_FIELDS = """
    id
    mediaKind
    displayName
    originalFilename
    mimeType
    fileExt
    fileSize
    sha256
    storageKey
    publicUrl
    status
    createdAt
    updatedAt
"""

_SETTING_FIELDS = f"""
    eventType
    label
    supportsOffsets
    enabled
    templateId
    paramMapping
    headerMediaUrl
    headerMediaAssetId
    offsetsDays
    template {{ {_TEMPLATE_FIELDS} }}
"""


def _map_template(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "template_name": node.get("templateName"),
        "template_language": node.get("templateLanguage"),
        "template_status": node.get("templateStatus"),
        "category": node.get("category"),
        "meta_template_id": node.get("metaTemplateId"),
        "default_header_media_asset_id": node.get("defaultHeaderMediaAssetId"),
        "components": node.get("components"),
    }


def _map_asset(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "media_kind": node.get("mediaKind"),
        "display_name": node.get("displayName"),
        "original_filename": node.get("originalFilename"),
        "mime_type": node.get("mimeType"),
        "file_ext": node.get("fileExt"),
        "file_size": node.get("fileSize"),
        "sha256": node.get("sha256"),
        "storage_key": node.get("storageKey"),
        "public_url": node.get("publicUrl"),
        "status": node.get("status"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
    }


def _map_setting(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "event_type": node.get("eventType"),
        "label": node.get("label"),
        "supports_offsets": bool(node.get("supportsOffsets")),
        "enabled": bool(node.get("enabled")),
        "template_id": node.get("templateId"),
        "param_mapping": list(node.get("paramMapping") or []),
        "header_media_url": node.get("headerMediaUrl"),
        "header_media_asset_id": node.get("headerMediaAssetId"),
        "offsets_days": list(node.get("offsetsDays") or []),
        "template": _map_template(node.get("template")),
    }


def _map_catalog(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "event_type": node.get("eventType"),
        "label": node.get("label"),
        "supports_offsets": bool(node.get("supportsOffsets")),
        "variables": [
            {
                "key": v.get("key"),
                "label": v.get("label"),
                "sample": v.get("sample"),
            }
            for v in (node.get("variables") or [])
        ],
    }


class WhatsAppNotificationsService:
    """Servicio para la configuración de notificaciones automáticas."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    async def get_settings(self) -> List[Dict[str, Any]]:
        """Devuelve la configuración de los eventos (siempre los 4, con defaults)."""
        query = f"""
            query NotificationSettings {{
                notificationSettings {{
                    {_SETTING_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query)
        if result and result.get("notificationSettings") is not None:
            return [_map_setting(n) for n in result["notificationSettings"]]
        return []

    async def get_catalog(self) -> List[Dict[str, Any]]:
        """Devuelve los eventos y las variables disponibles para cada uno."""
        query = """
            query NotificationCatalog {
                notificationCatalog {
                    eventType
                    label
                    supportsOffsets
                    variables { key label sample }
                }
            }
        """
        result = await self.client.execute(query)
        if result and result.get("notificationCatalog") is not None:
            return [_map_catalog(n) for n in result["notificationCatalog"]]
        return []

    async def get_approved_templates(self) -> List[Dict[str, Any]]:
        """Plantillas locales aprobadas por Meta (las únicas que se pueden enviar)."""
        query = f"""
            query GetTemplates {{
                whatsappTemplates {{
                    {_TEMPLATE_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query)
        nodes = (result or {}).get("whatsappTemplates") or []
        templates = [_map_template(n) for n in nodes]
        return [
            t
            for t in templates
            if (t.get("template_status") or "").upper() == "APPROVED"
            and t.get("meta_template_id")
        ]

    async def save_setting(
        self,
        event_type: str,
        enabled: bool,
        template_id: Optional[int],
        param_mapping: List[str],
        header_media_url: Optional[str] = None,
        header_media_asset_id: Optional[int] = None,
        offsets_days: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Crea o actualiza la configuración de un evento."""
        mutation = f"""
            mutation SaveNotificationSetting($input: SaveNotificationSettingInput!) {{
                saveNotificationSetting(input: $input) {{
                    success
                    error
                    setting {{ {_SETTING_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "eventType": event_type,
                "enabled": enabled,
                "templateId": template_id,
                "paramMapping": param_mapping or [],
                "headerMediaUrl": header_media_url,
                "headerMediaAssetId": header_media_asset_id,
                "offsetsDays": offsets_days or [],
            }
        }
        result = await self.client.execute(mutation, variables)
        payload = (result or {}).get("saveNotificationSetting")
        if not payload:
            return {"success": False, "error": "Sin respuesta del servidor", "setting": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "setting": _map_setting(payload.get("setting")),
        }

    async def get_media_assets(
        self,
        kind: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = f"""
            query GetWhatsappMediaAssets($kind: String, $search: String) {{
                whatsappMediaAssets(kind: $kind, search: $search, status: "active") {{
                    {_MEDIA_ASSET_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query, {"kind": kind, "search": search})
        nodes = (result or {}).get("whatsappMediaAssets") or []
        return [_map_asset(n) for n in nodes if n]

    async def upload_media_asset(
        self,
        file_path: str,
        kind: str,
        display_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        mutation = f"""
            mutation UploadWhatsappMediaAsset(
                $file: Upload!,
                $kind: WhatsAppMediaKind!,
                $displayName: String
            ) {{
                uploadWhatsappMediaAsset(file: $file, kind: $kind, displayName: $displayName) {{
                    {_MEDIA_ASSET_FIELDS}
                }}
            }}
        """
        variables = {"kind": (kind or "").upper(), "displayName": display_name}
        result = await self.client.execute_multipart(
            mutation,
            variables,
            file_path=file_path,
            file_variable="file",
        )
        return _map_asset((result or {}).get("uploadWhatsappMediaAsset"))

    async def run_sweep(self) -> Dict[str, Any]:
        """Ejecuta el barrido de recordatorios/vencidos de inmediato."""
        mutation = """
            mutation RunNotificationSweep {
                runNotificationSweep {
                    success
                    sent
                    skipped
                    failed
                    error
                }
            }
        """
        result = await self.client.execute(mutation)
        payload = (result or {}).get("runNotificationSweep")
        if not payload:
            return {"success": False, "error": "Sin respuesta del servidor"}
        return payload
