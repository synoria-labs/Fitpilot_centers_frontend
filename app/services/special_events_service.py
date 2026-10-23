"""Servicio para «Eventos especiales» (clases únicas con cupo y precio propios).

Envuelve las queries/mutations ``specialEvents``, ``specialEvent``, la vista previa y la
aplicación de la sustitución de un horario regular, la restitución, el seguimiento de clientes
desplazados y la gestión de participantes. Todas las mutations devuelven el detalle recalculado
del evento, así que la pantalla se repinta con lo que el servidor acaba de decidir.

Las fechas y horas viajan como texto local de la sede ("2026-10-30", "19:00"): la conversión a
UTC la hace el servidor con la zona horaria del evento, nunca la PC.
"""
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)

_NO_RESPONSE = "Sin respuesta del servidor"

_EVENT_FIELDS = """
    id name description includes address venueId venueName venueAddress classTypeId
    instructorId instructorName timezone startAt endAt localDate localStartTime localEndTime
    scheduleLabel price currency capacity holdMinutes status sold held available salesOpen
    salesClosedReason publishBlockers paymentsReady paymentsWarning activeTakeovers
    pendingFollowUps cancelReason publishedAt canceledAt createdAt
    seats { seatId label status }
    linkedCampaigns { id name status }
"""

_ORDER_FIELDS = """
    id participantName participantPhone personId seatId seatLabel status channel amount currency
    paymentMethod paidAt holdExpiresAt mpStatus mpPaymentId reviewReason cancelReason refundedAt
    notes createdAt
"""

_DISPLACEMENT_FIELDS = """
    id eventId eventName sessionId sessionName sessionStartAt sessionLabel sessionStatus personId
    personName phone seatLabel reservationId reservationStatus reservationSource planName
    membershipEndsAt reason followUpStatus notifiedAt notifiedByName notificationChannel
    notificationNotes compensationType compensationNotes resolvedAt resolvedByName
    restorationStatus restorationNote restoredAt
"""

_DETAIL_FIELDS = f"""
    event {{ {_EVENT_FIELDS} }}
    orders {{ {_ORDER_FIELDS} }}
    displacements {{ {_DISPLACEMENT_FIELDS} }}
    takeovers {{
        id sessionId sessionName sessionLabel status previousStatus reason appliedAt
        appliedByName restoredAt restoredByName
    }}
"""

_RESULT_FIELDS = f"success error message detail {{ {_DETAIL_FIELDS} }}"


def _snake(name: str) -> str:
    out = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _to_snake(node: Any) -> Any:
    """camelCase -> snake_case recursively (the GraphQL layer is the only camelCase source)."""
    if isinstance(node, dict):
        return {_snake(k): _to_snake(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_to_snake(v) for v in node]
    return node


def map_event(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    event = _to_snake(node)
    event["id"] = int(event["id"])
    event["price"] = float(event.get("price") or 0)
    event["seats"] = event.get("seats") or []
    event["publish_blockers"] = event.get("publish_blockers") or []
    event["linked_campaigns"] = event.get("linked_campaigns") or []
    return event


def map_detail(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    detail = _to_snake(node)
    detail["event"] = map_event(node.get("event"))
    detail["orders"] = detail.get("orders") or []
    detail["displacements"] = detail.get("displacements") or []
    detail["takeovers"] = detail.get("takeovers") or []
    return detail


class SpecialEventsService:
    """Servicio de eventos especiales (requiere la capacidad ``manage_special_events``)."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    # ------------------------------------------------------------------ reads
    async def list_events(self, include_past: bool = False) -> List[Dict[str, Any]]:
        query = f"""
            query SpecialEvents($includePast: Boolean!) {{
                specialEvents(includePast: $includePast) {{ {_EVENT_FIELDS} }}
            }}
        """
        result = await self.client.execute(query, {"includePast": include_past})
        if result is None:
            raise RuntimeError(self._error())
        return [map_event(n) for n in result.get("specialEvents") or []]

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        query = f"""
            query SpecialEvent($id: Int!) {{ specialEvent(id: $id) {{ {_DETAIL_FIELDS} }} }}
        """
        result = await self.client.execute(query, {"id": int(event_id)})
        if result is None:
            raise RuntimeError(self._error())
        return map_detail(result.get("specialEvent"))

    async def get_form_options(self) -> Optional[Dict[str, Any]]:
        query = """
            query SpecialEventFormOptions {
                specialEventFormOptions {
                    defaultTimezone paymentsReady paymentsWarning
                    venues { id name address seats { seatId label status } }
                    instructors { id name }
                    classTypes { id name }
                }
            }
        """
        result = await self.client.execute(query)
        if result is None:
            raise RuntimeError(self._error())
        return _to_snake(result.get("specialEventFormOptions"))

    async def takeover_preview(self, event_id: int) -> Optional[Dict[str, Any]]:
        query = """
            query TakeoverPreview($id: Int!) {
                specialEventTakeoverPreview(eventId: $id) {
                    eventId pendingSessionIds affectedClients blockers summary
                    sessions {
                        sessionId name label status capacity takenByThisEvent
                        clients {
                            personId personName phone reservationStatus source seatLabel
                            planName membershipEndsAt withoutReservation
                        }
                    }
                }
            }
        """
        result = await self.client.execute(query, {"id": int(event_id)})
        if result is None:
            raise RuntimeError(self._error())
        return _to_snake(result.get("specialEventTakeoverPreview"))

    async def restore_preview(self, event_id: int) -> Optional[Dict[str, Any]]:
        query = """
            query RestorePreview($id: Int!) {
                specialEventRestorePreview(eventId: $id) {
                    eventId sessionLabels blockers summary
                    decisions { displacementId personName sessionId restore reason }
                }
            }
        """
        result = await self.client.execute(query, {"id": int(event_id)})
        if result is None:
            raise RuntimeError(self._error())
        return _to_snake(result.get("specialEventRestorePreview"))

    async def list_campaigns(self) -> List[Dict[str, Any]]:
        query = """
            query CampaignsForEvents { campaigns(limit: 100) { id name status specialEventId } }
        """
        result = await self.client.execute(query)
        if result is None:
            raise RuntimeError(self._error())
        return [_to_snake(c) for c in result.get("campaigns") or []]

    # ------------------------------------------------------------------ writes
    async def create_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation CreateSpecialEvent($input: SpecialEventInput!) {{
                createSpecialEvent(input: $input) {{ {_RESULT_FIELDS} }}
            }}
        """
        return self._result(
            await self.client.execute(mutation, {"input": self._input(data)}), "createSpecialEvent"
        )

    async def update_event(self, event_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation UpdateSpecialEvent($id: Int!, $input: SpecialEventInput!) {{
                updateSpecialEvent(id: $id, input: $input) {{ {_RESULT_FIELDS} }}
            }}
        """
        variables = {"id": int(event_id), "input": self._input(data)}
        return self._result(await self.client.execute(mutation, variables), "updateSpecialEvent")

    async def publish_event(self, event_id: int) -> Dict[str, Any]:
        return await self._simple("publishSpecialEvent", "id: $id", {"id": int(event_id)}, "$id: Int!")

    async def unpublish_event(self, event_id: int) -> Dict[str, Any]:
        return await self._simple("unpublishSpecialEvent", "id: $id", {"id": int(event_id)}, "$id: Int!")

    async def cancel_event(self, event_id: int, reason: str) -> Dict[str, Any]:
        return await self._simple(
            "cancelSpecialEvent", "id: $id, reason: $reason",
            {"id": int(event_id), "reason": reason}, "$id: Int!, $reason: String!",
        )

    async def apply_takeover(self, event_id: int, session_ids: List[int], reason: Optional[str] = None) -> Dict[str, Any]:
        return await self._simple(
            "applySpecialEventTakeover", "eventId: $id, sessionIds: $ids, reason: $reason",
            {"id": int(event_id), "ids": [int(s) for s in session_ids], "reason": reason},
            "$id: Int!, $ids: [Int!]!, $reason: String",
        )

    async def restore_schedule(self, event_id: int) -> Dict[str, Any]:
        return await self._simple(
            "restoreRegularSchedule", "eventId: $id", {"id": int(event_id)}, "$id: Int!"
        )

    async def add_participant(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation AddParticipant($input: AddParticipantInput!) {{
                addSpecialEventParticipant(input: $input) {{ {_RESULT_FIELDS} }}
            }}
        """
        variables = {
            "input": {
                "eventId": int(data["event_id"]),
                "participantName": data.get("participant_name") or "",
                "participantPhone": data.get("participant_phone") or "",
                "paymentMethod": data.get("payment_method") or "cash",
                "amount": data.get("amount"),
                "seatId": data.get("seat_id"),
                "notes": data.get("notes"),
            }
        }
        return self._result(await self.client.execute(mutation, variables), "addSpecialEventParticipant")

    async def cancel_order(self, order_id: int, reason: str) -> Dict[str, Any]:
        return await self._simple(
            "cancelSpecialEventOrder", "orderId: $id, reason: $reason",
            {"id": int(order_id), "reason": reason}, "$id: Int!, $reason: String",
        )

    async def refund_order(self, order_id: int, reason: str) -> Dict[str, Any]:
        return await self._simple(
            "refundSpecialEventOrder", "orderId: $id, reason: $reason",
            {"id": int(order_id), "reason": reason}, "$id: Int!, $reason: String",
        )

    async def link_campaign(self, campaign_id: int, event_id: Optional[int]) -> Dict[str, Any]:
        return await self._simple(
            "linkCampaignToSpecialEvent", "campaignId: $cid, eventId: $eid",
            {"cid": int(campaign_id), "eid": event_id}, "$cid: Int!, $eid: Int",
        )

    async def update_follow_up(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = f"""
            mutation FollowUp($input: DisplacementFollowUpInput!) {{
                updateDisplacementFollowUp(input: $input) {{
                    success error displacement {{ {_DISPLACEMENT_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "displacementId": int(data["displacement_id"]),
                "notified": data.get("notified"),
                "notificationChannel": data.get("notification_channel"),
                "notificationNotes": data.get("notification_notes"),
                "compensationType": data.get("compensation_type"),
                "compensationNotes": data.get("compensation_notes"),
                "resolved": data.get("resolved"),
            }
        }
        result = await self.client.execute(mutation, variables)
        payload = (result or {}).get("updateDisplacementFollowUp")
        if not payload:
            return {"success": False, "error": self._error(), "displacement": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "displacement": _to_snake(payload.get("displacement")),
        }

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _input(data: Dict[str, Any]) -> Dict[str, Any]:
        """Only the keys the form provides (None = no change on update)."""
        mapping = {
            "name": "name",
            "description": "description",
            "includes": "includes",
            "address": "address",
            "venue_id": "venueId",
            "class_type_id": "classTypeId",
            "instructor_id": "instructorId",
            "timezone": "timezone",
            "local_date": "localDate",
            "start_time": "startTime",
            "end_time": "endTime",
            "price": "price",
            "capacity": "capacity",
            "seat_ids": "seatIds",
            "hold_minutes": "holdMinutes",
        }
        return {gql: data[key] for key, gql in mapping.items() if data.get(key) is not None}

    async def _simple(self, field: str, args: str, variables: Dict[str, Any], decl: str) -> Dict[str, Any]:
        mutation = f"mutation Op({decl}) {{ {field}({args}) {{ {_RESULT_FIELDS} }} }}"
        return self._result(await self.client.execute(mutation, variables), field)

    def _result(self, result: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
        payload = (result or {}).get(key)
        if not payload:
            return {"success": False, "error": self._error(), "message": None, "detail": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "message": payload.get("message"),
            "detail": map_detail(payload.get("detail")),
        }

    def _error(self) -> str:
        # Read right after the await: the GraphQL client is shared between screens.
        return getattr(self.client, "last_error", None) or _NO_RESPONSE
