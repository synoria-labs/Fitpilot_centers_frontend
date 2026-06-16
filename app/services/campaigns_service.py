"""Servicio para la feature de Campañas de marketing por WhatsApp.

Envuelve las queries/mutations GraphQL del backend (módulo ``campaigns``) que crean campañas
de difusión con segmentación, las envían reutilizando la infraestructura de WhatsApp, y miden
entrega + conversión. Devuelve dicts normalizados (snake_case) para el controller/vista.
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

_CAMPAIGN_FIELDS = f"""
    id
    name
    description
    objective
    status
    audienceSpec
    templateId
    paramMapping
    headerMediaUrl
    headerMediaAssetId
    marketingCampaignId
    scheduledAt
    sendLocalTime
    conversionWindowDays
    conversionMetric
    recencyBlockDays
    throttlePerMinute
    startedAt
    finishedAt
    createdAt
    updatedAt
    template {{ {_TEMPLATE_FIELDS} }}
"""

_METRICS_FIELDS = """
    targeted
    pending
    sent
    delivered
    read
    replied
    failed
    skipped
    optedOut
    converted
    deliveryRate
    readRate
    replyRate
    conversionRate
    revenueRecovered
"""

_RUN_FIELDS = """
    success
    paused
    dryRun
    targeted
    pending
    sent
    failed
    skipped
    renderedPreview
    error
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


def _map_campaign(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "description": node.get("description"),
        "objective": node.get("objective"),
        "status": node.get("status"),
        "audience_spec": node.get("audienceSpec"),
        "template_id": node.get("templateId"),
        "param_mapping": list(node.get("paramMapping") or []),
        "header_media_url": node.get("headerMediaUrl"),
        "header_media_asset_id": node.get("headerMediaAssetId"),
        "marketing_campaign_id": node.get("marketingCampaignId"),
        "scheduled_at": node.get("scheduledAt"),
        "send_local_time": bool(node.get("sendLocalTime")),
        "conversion_window_days": node.get("conversionWindowDays"),
        "conversion_metric": node.get("conversionMetric"),
        "recency_block_days": node.get("recencyBlockDays"),
        "throttle_per_minute": node.get("throttlePerMinute"),
        "started_at": node.get("startedAt"),
        "finished_at": node.get("finishedAt"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "template": _map_template(node.get("template")),
    }


def _map_metrics(node: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    node = node or {}
    return {
        "targeted": node.get("targeted", 0),
        "pending": node.get("pending", 0),
        "sent": node.get("sent", 0),
        "delivered": node.get("delivered", 0),
        "read": node.get("read", 0),
        "replied": node.get("replied", 0),
        "failed": node.get("failed", 0),
        "skipped": node.get("skipped", 0),
        "opted_out": node.get("optedOut", 0),
        "converted": node.get("converted", 0),
        "delivery_rate": node.get("deliveryRate", 0.0),
        "read_rate": node.get("readRate", 0.0),
        "reply_rate": node.get("replyRate", 0.0),
        "conversion_rate": node.get("conversionRate", 0.0),
        "revenue_recovered": node.get("revenueRecovered", 0.0),
    }


def _map_run(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return {"success": False, "error": "Sin respuesta del servidor"}
    return {
        "success": bool(payload.get("success")),
        "paused": bool(payload.get("paused")),
        "dry_run": bool(payload.get("dryRun")),
        "targeted": payload.get("targeted", 0),
        "pending": payload.get("pending", 0),
        "sent": payload.get("sent", 0),
        "failed": payload.get("failed", 0),
        "skipped": payload.get("skipped", 0),
        "rendered_preview": payload.get("renderedPreview"),
        "error": payload.get("error"),
    }


class CampaignsService:
    """Servicio para leer/crear/enviar campañas de marketing por WhatsApp."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    # ------------------------------------------------------------------ reads
    async def list_campaigns(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = f"""
            query Campaigns($status: String) {{
                campaigns(status: $status, limit: 200) {{
                    {_CAMPAIGN_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query, {"status": status})
        nodes = (result or {}).get("campaigns") or []
        return [_map_campaign(n) for n in nodes if n]

    async def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        query = f"""
            query Campaign($id: Int!) {{
                campaign(id: $id) {{ {_CAMPAIGN_FIELDS} }}
            }}
        """
        result = await self.client.execute(query, {"id": campaign_id})
        return _map_campaign((result or {}).get("campaign"))

    async def get_catalog(self) -> Dict[str, Any]:
        query = """
            query CampaignCatalog {
                campaignCatalog {
                    objectives { key label variables }
                    predicates { type label kind options hint }
                    variables { key label sample }
                }
            }
        """
        result = await self.client.execute(query)
        node = (result or {}).get("campaignCatalog") or {}
        return {
            "objectives": node.get("objectives") or [],
            "predicates": node.get("predicates") or [],
            "variables": node.get("variables") or [],
        }

    async def get_approved_templates(self) -> List[Dict[str, Any]]:
        query = f"""
            query GetTemplates {{
                whatsappTemplates {{ {_TEMPLATE_FIELDS} }}
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

    async def preview_audience(self, audience_spec: Dict[str, Any]) -> Dict[str, Any]:
        query = """
            query PreviewAudience($spec: JSON) {
                previewAudience(audienceSpec: $spec) { count sample }
            }
        """
        result = await self.client.execute(query, {"spec": audience_spec})
        node = (result or {}).get("previewAudience") or {}
        return {"count": node.get("count", 0), "sample": list(node.get("sample") or [])}

    async def get_metrics(self, campaign_id: int) -> Dict[str, Any]:
        query = f"""
            query CampaignMetrics($id: Int!) {{
                campaignMetrics(campaignId: $id) {{ {_METRICS_FIELDS} }}
            }}
        """
        result = await self.client.execute(query, {"id": campaign_id})
        return _map_metrics((result or {}).get("campaignMetrics"))

    async def list_recipients(
        self, campaign_id: int, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
            query CampaignRecipients($id: Int!, $status: String) {
                campaignRecipients(campaignId: $id, status: $status, limit: 500) {
                    id personId phoneE164 status skipReason waMessageId
                    sentAt deliveredAt readAt repliedAt converted convertedAt error
                }
            }
        """
        result = await self.client.execute(query, {"id": campaign_id, "status": status})
        nodes = (result or {}).get("campaignRecipients") or []
        return [
            {
                "id": n.get("id"),
                "person_id": n.get("personId"),
                "phone_e164": n.get("phoneE164"),
                "status": n.get("status"),
                "skip_reason": n.get("skipReason"),
                "wa_message_id": n.get("waMessageId"),
                "sent_at": n.get("sentAt"),
                "delivered_at": n.get("deliveredAt"),
                "read_at": n.get("readAt"),
                "replied_at": n.get("repliedAt"),
                "converted": bool(n.get("converted")),
                "converted_at": n.get("convertedAt"),
                "error": n.get("error"),
            }
            for n in nodes
            if n
        ]

    # -------------------------------------------------------------- mutations
    async def create_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation CreateCampaign($input: CreateCampaignInput!) {{
                createCampaign(input: $input) {{
                    success error campaign {{ {_CAMPAIGN_FIELDS} }}
                }}
            }}
        """
        result = await self.client.execute(mutation, {"input": payload})
        node = (result or {}).get("createCampaign")
        if not node:
            return {"success": False, "error": "Sin respuesta del servidor", "campaign": None}
        return {
            "success": bool(node.get("success")),
            "error": node.get("error"),
            "campaign": _map_campaign(node.get("campaign")),
        }

    async def update_campaign(self, campaign_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation UpdateCampaign($id: Int!, $input: UpdateCampaignInput!) {{
                updateCampaign(id: $id, input: $input) {{
                    success error campaign {{ {_CAMPAIGN_FIELDS} }}
                }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id, "input": payload})
        node = (result or {}).get("updateCampaign")
        if not node:
            return {"success": False, "error": "Sin respuesta del servidor", "campaign": None}
        return {
            "success": bool(node.get("success")),
            "error": node.get("error"),
            "campaign": _map_campaign(node.get("campaign")),
        }

    async def delete_campaign(self, campaign_id: int) -> Dict[str, Any]:
        mutation = """
            mutation DeleteCampaign($id: Int!) {
                deleteCampaign(id: $id) { success error }
            }
        """
        result = await self.client.execute(mutation, {"id": campaign_id})
        return (result or {}).get("deleteCampaign") or {"success": False, "error": "Sin respuesta"}

    async def build_audience(self, campaign_id: int) -> Dict[str, Any]:
        mutation = f"""
            mutation BuildAudience($id: Int!) {{
                buildCampaignAudience(id: $id) {{ {_RUN_FIELDS} }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id})
        return _map_run((result or {}).get("buildCampaignAudience"))

    async def schedule_campaign(
        self, campaign_id: int, scheduled_at: str, send_local_time: bool = False
    ) -> Dict[str, Any]:
        mutation = f"""
            mutation ScheduleCampaign($id: Int!, $at: DateTime!, $local: Boolean!) {{
                scheduleCampaign(id: $id, scheduledAt: $at, sendLocalTime: $local) {{
                    success error campaign {{ {_CAMPAIGN_FIELDS} }}
                }}
            }}
        """
        variables = {"id": campaign_id, "at": scheduled_at, "local": send_local_time}
        result = await self.client.execute(mutation, variables)
        node = (result or {}).get("scheduleCampaign")
        if not node:
            return {"success": False, "error": "Sin respuesta del servidor", "campaign": None}
        return {
            "success": bool(node.get("success")),
            "error": node.get("error"),
            "campaign": _map_campaign(node.get("campaign")),
        }

    async def trigger_campaign(self, campaign_id: int, dry_run: bool = False) -> Dict[str, Any]:
        mutation = f"""
            mutation TriggerCampaign($id: Int!, $dry: Boolean!) {{
                triggerCampaign(id: $id, dryRun: $dry) {{ {_RUN_FIELDS} }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id, "dry": dry_run})
        return _map_run((result or {}).get("triggerCampaign"))

    async def _simple_status_mutation(self, name: str, campaign_id: int) -> Dict[str, Any]:
        mutation = f"""
            mutation Act($id: Int!) {{
                {name}(id: $id) {{ success error campaign {{ {_CAMPAIGN_FIELDS} }} }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id})
        node = (result or {}).get(name)
        if not node:
            return {"success": False, "error": "Sin respuesta del servidor", "campaign": None}
        return {
            "success": bool(node.get("success")),
            "error": node.get("error"),
            "campaign": _map_campaign(node.get("campaign")),
        }

    async def pause_campaign(self, campaign_id: int) -> Dict[str, Any]:
        return await self._simple_status_mutation("pauseCampaign", campaign_id)

    async def cancel_campaign(self, campaign_id: int) -> Dict[str, Any]:
        return await self._simple_status_mutation("cancelCampaign", campaign_id)

    async def resume_campaign(self, campaign_id: int) -> Dict[str, Any]:
        mutation = f"""
            mutation Resume($id: Int!) {{
                resumeCampaign(id: $id) {{ {_RUN_FIELDS} }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id})
        return _map_run((result or {}).get("resumeCampaign"))

    async def retry_failures(self, campaign_id: int) -> Dict[str, Any]:
        mutation = f"""
            mutation Retry($id: Int!) {{
                retryCampaignFailures(id: $id) {{ {_RUN_FIELDS} }}
            }}
        """
        result = await self.client.execute(mutation, {"id": campaign_id})
        return _map_run((result or {}).get("retryCampaignFailures"))
