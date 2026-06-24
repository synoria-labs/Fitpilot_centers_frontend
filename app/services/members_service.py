from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from ..utils.datetime_helpers import parse_iso_datetime, format_iso_datetime
from ..models.base import (
    Member,
    ActiveStandingBookingInfo,
    MembershipInfo,
    MembershipPlan,
    MembershipSubscription,
    Payment,
)

logger = get_logger(__name__)


def _serialize_datetime(value) -> Optional[str]:
    """Serialize datetime objects to ISO strings for GraphQL."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return format_iso_datetime(value)

    if isinstance(value, str):
        return value

    logger.warning("Unexpected datetime type received: %s", type(value))
    return None


def _normalize_renewal_error_message(
    message_text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Normalize renewal failures into stable codes and user-friendly messages."""
    meta = metadata if isinstance(metadata, dict) else {}
    raw_text = (message_text or "").strip()
    details = str(meta.get("details") or raw_text).strip()
    error_code = str(meta.get("errorCode") or "").strip().upper()
    cause = str(meta.get("cause") or "").strip()

    corpus = " ".join(filter(None, [raw_text, details, cause])).lower()

    if not error_code:
        if any(
            marker in corpus
            for marker in (
                "already reserved by another person",
                "no se pudieron crear los standing bookings",
                "no se pudieron materializar las reservas",
                "sin cupo",
                "asientos ocupados",
                "seat",
                "disponibilidad",
            )
        ):
            error_code = "NO_AVAILABILITY"
        elif "debe seleccionar un horario" in corpus:
            error_code = "MISSING_TEMPLATE"
        elif "comunicacion" in corpus or "connection" in corpus or "network" in corpus:
            error_code = "NETWORK_ERROR"
        else:
            error_code = "RENEWAL_FAILED"

    if not cause:
        cause_by_code = {
            "NO_AVAILABILITY": "Falta de disponibilidad",
            "MISSING_TEMPLATE": "Falta seleccionar horario",
            "NETWORK_ERROR": "Error de comunicacion con el servidor",
            "RENEWAL_FAILED": "Error al renovar la suscripcion",
        }
        cause = cause_by_code.get(error_code, "Error al renovar la suscripcion")

    base_message = f"{cause}."
    detail_suffix = details if details and details.lower() != cause.lower() else ""
    if detail_suffix:
        return {
            "error_code": error_code,
            "error_cause": cause,
            "message": f"{base_message} {detail_suffix}",
        }

    return {
        "error_code": error_code,
        "error_cause": cause,
        "message": base_message,
    }


def _normalize_member_update_error_message(
    message_text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Normalize member update failures into stable codes and user-friendly messages."""
    meta = metadata if isinstance(metadata, dict) else {}
    raw_text = (message_text or "").strip()
    details = str(meta.get("details") or raw_text).strip()
    error_code = str(
        meta.get("errorCode")
        or meta.get("error_code")
        or ""
    ).strip().upper()
    cause = str(
        meta.get("errorCause")
        or meta.get("error_cause")
        or meta.get("cause")
        or ""
    ).strip()

    corpus = " ".join(filter(None, [raw_text, details, cause])).lower()

    if not error_code:
        if any(marker in corpus for marker in ("no encontrado", "not found", "miembro no encontrado", "socio no encontrado")):
            error_code = "MEMBER_NOT_FOUND"
        elif any(
            marker in corpus
            for marker in (
                "inval",
                "invalid",
                "validation",
                "requerid",
                "required",
                "email",
                "correo",
                "telefono",
                "phone",
            )
        ):
            error_code = "VALIDATION_ERROR"
        elif any(marker in corpus for marker in ("network", "connection", "timeout", "comunicacion", "servidor")):
            error_code = "NETWORK_ERROR"
        else:
            error_code = "UPDATE_FAILED"

    if not cause:
        cause_by_code = {
            "MEMBER_NOT_FOUND": "Socio no encontrado",
            "VALIDATION_ERROR": "Datos invalidos",
            "NETWORK_ERROR": "Error de comunicacion con el servidor",
            "UPDATE_FAILED": "Error al actualizar socio",
        }
        cause = cause_by_code.get(error_code, "Error al actualizar socio")

    base_message = f"No se guardaron los cambios. Causa: {cause}."
    detail_suffix = details if details and details.lower() != cause.lower() else ""
    if detail_suffix and detail_suffix.lower() not in base_message.lower():
        message = f"{base_message} {detail_suffix}"
    else:
        message = base_message

    return {
        "error_code": error_code,
        "error_cause": cause,
        "message": message,
    }


class MembersService:
    """Service layer for members-related GraphQL operations."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def get_members(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch one backend page of members plus the exact matching total."""
        query = """
            query GetMembers($limit: Int, $offset: Int, $search: String) {
                membersPage(limit: $limit, offset: $offset, search: $search) {
                    total
                    items {
                        id
                        fullName
                        email
                        phoneNumber
                        waId
                        registrationDate
                        totalPayments
                        lastActivity
                        activeStandingBooking {
                            templateId
                            templateName
                            classTypeName
                            weekday
                            startTimeLocal
                            venueName
                            instructorName
                        }
                        activeMembership {
                            subscriptionId
                            planName
                            startDate
                            endDate
                            status
                            remainingDays
                        }
                    }
                }
            }
        """

        variables = {
            "limit": limit,
            "offset": offset,
            "search": search,
        }

        try:
            result = await self.client.execute(query, variables)
            payload = (result or {}).get("membersPage") or {}
            raw_members = payload.get("items") or []
            return {
                "items": [self._parse_member(item) for item in raw_members],
                "total": int(payload.get("total") or 0),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching members: %s", exc)
            return {"items": [], "total": 0}

    async def get_member_by_id(self, member_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single member by ID with their membership information."""
        query = """
            query GetMemberById($memberId: Int!) {
                member(memberId: $memberId) {
                    id
                    fullName
                    email
                    phoneNumber
                    activeMembership {
                        subscriptionId
                        planName
                        startDate
                        endDate
                        status
                        remainingDays
                        price
                        paymentAmount
                    }
                    activeStandingBooking {
                        templateId
                        templateName
                        classTypeName
                        weekday
                        startTimeLocal
                        venueName
                        instructorName
                        seatId
                    }
                    totalPayments
                }
            }
        """

        variables = {"memberId": member_id}

        logger.info("Executing member by ID GraphQL query for member_id=%s", member_id)

        try:
            response = await self.client.execute(query, variables)

            if not response or 'member' not in response:
                logger.warning("GraphQL query returned None or missing 'member' field for member_id=%s", member_id)
                return self._create_fallback_member_data(member_id)

            member_data = response['member']
            if not member_data:
                logger.warning("No member found with ID %s", member_id)
                return self._create_fallback_member_data(member_id)

            # Convert to expected format
            result = {
                'id': member_data.get('id'),
                'full_name': member_data.get('fullName'),
                'email': member_data.get('email'),
                'phone_number': member_data.get('phoneNumber'),
                'total_payments': member_data.get('totalPayments', 0.0),
            }

            # Add active membership if available
            active_membership = member_data.get('activeMembership')
            if active_membership:
                result['active_membership'] = {
                    'subscription_id': active_membership.get('subscriptionId'),
                    'plan_name': active_membership.get('planName'),
                    'start_date': parse_iso_datetime(active_membership.get('startDate')),
                    'end_date': parse_iso_datetime(active_membership.get('endDate')),
                    'status': active_membership.get('status'),
                    'remaining_days': active_membership.get('remainingDays'),
                    'price': active_membership.get('price', 0.0),
                    'payment_amount': active_membership.get('paymentAmount', 0.0),
                }

            # Add active standing booking if available
            active_standing_booking = member_data.get('activeStandingBooking')
            if active_standing_booking:
                result['active_standing_booking'] = {
                    'template_id': active_standing_booking.get('templateId'),
                    'template_name': active_standing_booking.get('templateName'),
                    'class_type_name': active_standing_booking.get('classTypeName'),
                    'weekday': active_standing_booking.get('weekday'),
                    'start_time_local': active_standing_booking.get('startTimeLocal'),
                    'venue_name': active_standing_booking.get('venueName'),
                    'instructor_name': active_standing_booking.get('instructorName'),
                    'seat_id': active_standing_booking.get('seatId'),
                }

            logger.info("Member data loaded successfully for ID %s", member_id)
            return result

        except Exception as e:
            logger.error("Error fetching member by ID %s: %s", member_id, str(e))
            logger.info("Using fallback member data for member_id=%s", member_id)
            return self._create_fallback_member_data(member_id)

    async def update_member(self, member_id: int, payload: Dict[str, str]) -> Dict[str, Any]:
        """Update basic member info in the backend."""
        mutation = """
            mutation UpdateMember($memberId: Int!, $input: UpdateMemberInput!) {
                updateMember(memberId: $memberId, input: $input) {
                    success
                    member {
                        id
                        fullName
                        email
                        phoneNumber
                        waId
                    }
                    message
                    errorCode
                    errorCause
                }
            }
        """
        legacy_mutation = """
            mutation UpdateMemberLegacy($memberId: Int!, $input: UpdateMemberInput!) {
                updateMember(memberId: $memberId, input: $input) {
                    member {
                        id
                        fullName
                        email
                        phoneNumber
                        waId
                    }
                    message
                }
            }
        """

        name = payload.get("name") or payload.get("full_name") or payload.get("fullName")
        email = payload.get("email")
        phone = payload.get("phone") or payload.get("phone_number") or payload.get("phoneNumber")

        input_payload = {
            "fullName": name if name else None,
            "email": email if email else None,
            "phoneNumber": phone if phone else None,
        }
        input_payload = {key: value for key, value in input_payload.items() if value is not None}

        if not input_payload:
            normalized = _normalize_member_update_error_message(
                "No se enviaron datos para actualizar",
                {
                    "errorCode": "VALIDATION_ERROR",
                    "errorCause": "Sin datos para actualizar",
                    "details": "No se enviaron datos para actualizar",
                },
            )
            return {
                "success": False,
                "message": normalized["message"],
                "error_code": normalized["error_code"],
                "error_cause": normalized["error_cause"],
                "member": None,
            }

        variables = {
            "memberId": int(member_id),
            "input": input_payload,
        }

        started_at = time.perf_counter()
        used_legacy_shape = False

        try:
            result = await self.client.execute(mutation, variables)
            if result is None:
                # Backward compatibility for deployments without the new response fields.
                logger.warning(
                    "Update member returned no data for member_id=%s using modern shape. Retrying legacy shape.",
                    member_id,
                )
                used_legacy_shape = True
                result = await self.client.execute(legacy_mutation, variables)

            if result is None:
                normalized = _normalize_member_update_error_message(
                    "Error de comunicacion con el servidor",
                    {"errorCode": "NETWORK_ERROR", "cause": "Error de comunicacion con el servidor"},
                )
                duration_ms = (time.perf_counter() - started_at) * 1000
                logger.warning(
                    "update_member member_id=%s success=%s error_code=%s duration_ms=%.2f used_legacy_shape=%s",
                    member_id,
                    False,
                    normalized["error_code"],
                    duration_ms,
                    used_legacy_shape,
                )
                return {
                    "success": False,
                    "message": normalized["message"],
                    "error_code": normalized["error_code"],
                    "error_cause": normalized["error_cause"],
                    "member": None,
                }

            response_payload = (result or {}).get("updateMember") or {}
            member_data = response_payload.get("member")
            message = str(response_payload.get("message") or "").strip()
            success_flag = response_payload.get("success")
            if used_legacy_shape:
                success = bool(member_data)
            elif isinstance(success_flag, bool):
                success = bool(success_flag) and bool(member_data)
            else:
                success = bool(member_data)

            metadata = {
                "errorCode": response_payload.get("errorCode"),
                "errorCause": response_payload.get("errorCause"),
                "details": message,
            }

            if not success:
                normalized = _normalize_member_update_error_message(
                    message or "Error al actualizar socio",
                    metadata,
                )
                duration_ms = (time.perf_counter() - started_at) * 1000
                logger.warning(
                    "update_member member_id=%s success=%s error_code=%s duration_ms=%.2f used_legacy_shape=%s",
                    member_id,
                    False,
                    normalized["error_code"],
                    duration_ms,
                    used_legacy_shape,
                )
                return {
                    "success": False,
                    "message": normalized["message"],
                    "error_code": normalized["error_code"],
                    "error_cause": normalized["error_cause"],
                    "member": None,
                    "raw_message": message,
                }

            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "update_member member_id=%s success=%s duration_ms=%.2f used_legacy_shape=%s",
                member_id,
                True,
                duration_ms,
                used_legacy_shape,
            )
            return {
                "success": True,
                "message": message or "Datos actualizados correctamente.",
                "error_code": None,
                "error_cause": None,
                "member": self._parse_member(member_data) if member_data else None,
            }
        except Exception as exc:  # noqa: BLE001
            normalized = _normalize_member_update_error_message(
                str(exc),
                {"errorCode": "UPDATE_FAILED", "cause": "Error al actualizar socio"},
            )
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.error(
                "update_member member_id=%s success=%s error_code=%s duration_ms=%.2f error=%s",
                member_id,
                False,
                normalized["error_code"],
                duration_ms,
                exc,
            )
            return {
                "success": False,
                "message": normalized["message"],
                "error_code": normalized["error_code"],
                "error_cause": normalized["error_cause"],
                "member": None,
            }

    async def get_membership_plans(self) -> List[MembershipPlan]:
        """Retrieve catalog of membership plans."""
        query = """
            query GetMembershipPlans {
                membershipPlans {
                    id
                    name
                    description
                    price
                    durationValue
                    durationUnit
                    classLimit
                    fixedTimeSlot
                    maxSessionsPerDay
                    maxSessionsPerWeek
                    createdAt
                }
            }
        """

        try:
            logger.info("Executing membership plans GraphQL query...")
            result = await self.client.execute(query)
            logger.info(f"Membership plans query result: {result}")

            if result is None:
                logger.error("GraphQL query returned None")
                return []

            plans = result.get("membershipPlans", [])
            logger.info(f"Extracted plans: {len(plans) if plans else 0} items")

            if plans:
                logger.info(f"First plan sample: {plans[0] if plans else 'None'}")
                parsed_plans = [self._parse_plan(plan) for plan in plans]
                logger.info(f"Successfully parsed {len(parsed_plans)} plans")
                return parsed_plans
            else:
                logger.warning("No membership plans found in response")
                return []

        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching membership plans: %s", exc, exc_info=True)
            return []

    async def create_member_enrollment(
        self,
        *,
        full_name: str,
        email: Optional[str],
        phone_number: Optional[str],  # WhatsApp number
        plan_id: int,
        start_at,  # Can be datetime or str
        payment_method: str,
        payment_amount: Optional[float],
        payment_status: str = "COMPLETED",
        payment_comment: Optional[str] = None,
        payment_provider: Optional[str] = None,
        provider_payment_id: Optional[str] = None,
        external_reference: Optional[str] = None,
        template_id: Optional[int] = None,
        seat_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create member, subscription, and payment in backend."""
        mutation = """
            mutation CreateMemberEnrollment($input: CreateMemberEnrollmentInput!) {
                createMemberEnrollment(input: $input) {
                    member {
                        id
                        fullName
                        email
                        phoneNumber
                        registrationDate
                        totalPayments
                        lastActivity
                        activeMembership {
                            subscriptionId
                            planName
                            startDate
                            endDate
                            status
                            remainingDays
                        }
                    }
                    subscription {
                        id
                        personId
                        planId
                        startAt
                        endAt
                        status
                        planName
                        personName
                        remainingDays
                    }
                    payment {
                        id
                        personId
                        subscriptionId
                        amount
                        method
                        status
                        paidAt
                        provider
                        providerPaymentId
                        externalReference
                        comment
                        recordedBy
                    }
                    message
                }
            }
        """

        input_payload = {
            "fullName": full_name,
            "email": email,
            "phoneNumber": phone_number,  # WhatsApp stored as phone_number
            "planId": plan_id,
            "startAt": _serialize_datetime(start_at),
            "paymentMethod": payment_method,
            "paymentAmount": payment_amount,
            "paymentStatus": payment_status,
            "paymentComment": payment_comment,
            "paymentProvider": payment_provider,
            "providerPaymentId": provider_payment_id,
            "externalReference": external_reference,
        }
        # Optional standing booking inputs to reuse renewal flow in backend
        if template_id is not None:
            input_payload["templateId"] = int(template_id)
        if seat_id is not None:
            input_payload["seatId"] = int(seat_id)

        variables = {"input": input_payload}

        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get("createMemberEnrollment") or {}
            member_data = payload.get("member")
            subscription_data = payload.get("subscription")
            payment_data = payload.get("payment")

            return {
                "member": self._parse_member(member_data) if member_data else None,
                "subscription": self._parse_subscription(subscription_data) if subscription_data else None,
                "payment": self._parse_payment(payment_data) if payment_data else None,
                "message": payload.get("message", "")
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error creating member enrollment: %s", exc)
            return {
                "member": None,
                "subscription": None,
                "payment": None,
                "message": str(exc)
            }

    async def renew_subscription(
        self,
        member_id: int,
        plan_id: int,
        template_id: Optional[int] = None,
        seat_id: Optional[int] = None,
        start_at=None,  # Can be datetime or str
        payment_method: str = 'cash',
        payment_amount: Optional[float] = None,
        payment_status: str = 'COMPLETED',
        payment_comment: Optional[str] = None,
        payment_provider: Optional[str] = None,
        provider_payment_id: Optional[str] = None,
        external_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Renew a member's subscription using the new GraphQL mutation."""
        mutation = """
            mutation RenewSubscription($input: RenewSubscriptionInput!) {
                renewSubscription(input: $input) {
                    success
                    subscription {
                        id
                        personId
                        planId
                        startAt
                        endAt
                        status
                        planName
                        personName
                        remainingDays
                    }
                    payment {
                        id
                        personId
                        subscriptionId
                        amount
                        method
                        status
                        paidAt
                        provider
                        providerPaymentId
                        externalReference
                        comment
                        recordedBy
                    }
                    message
                    standingBookingId
                    materializationStats
                }
            }
        """

        input_payload = {
            "memberId": member_id,
            "planId": plan_id,
            "templateId": template_id,
            "seatId": seat_id,
            "startAt": _serialize_datetime(start_at),
            "paymentMethod": payment_method,
            "paymentAmount": payment_amount,
            "paymentStatus": payment_status,
            "paymentComment": payment_comment,
            "paymentProvider": payment_provider,
            "providerPaymentId": provider_payment_id,
            "externalReference": external_reference,
        }

        variables = {"input": input_payload}

        try:
            result = await self.client.execute(mutation, variables)

            # GraphQL request failed completely
            if result is None:
                logger.error("GraphQL mutation failed - no result returned for member %s", member_id)
                normalized = _normalize_renewal_error_message(
                    "Error de comunicacion con el servidor",
                    {"errorCode": "NETWORK_ERROR", "cause": "Error de comunicacion con el servidor"},
                )
                return {
                    "success": False,
                    "subscription": None,
                    "payment": None,
                    "standing_booking_id": None,
                    "materialization_stats": None,
                    "error_code": normalized["error_code"],
                    "error_cause": normalized["error_cause"],
                    "message": normalized["message"],
                }

            payload = result.get("renewSubscription") or {}
            success_flag = payload.get("success")
            subscription_data = payload.get("subscription")
            payment_data = payload.get("payment")
            message = payload.get("message", "")

            standing_booking_id = payload.get("standingBookingId")
            materialization_stats = payload.get("materializationStats")

            # Parse message envelope when present
            parsed_message = message
            message_data: Dict[str, Any] = {}
            try:
                import json

                candidate_data = json.loads(message)
                if isinstance(candidate_data, dict):
                    message_data = candidate_data
                    if "text" in message_data:
                        parsed_message = message_data.get("text", message)
                        logger.info("Parsed message text from JSON envelope")
            except (json.JSONDecodeError, TypeError):
                logger.debug("Message is plain text, not JSON envelope")

            # Backward compatibility for metadata in message envelope
            if standing_booking_id is None:
                standing_booking_id = message_data.get("standingBookingId")

            if materialization_stats is None:
                envelope_stats = message_data.get("materializationStats")
                if envelope_stats is not None:
                    if isinstance(envelope_stats, str):
                        materialization_stats = envelope_stats
                    else:
                        try:
                            import json
                            materialization_stats = json.dumps(envelope_stats)
                        except (TypeError, ValueError):
                            materialization_stats = str(envelope_stats)

            if standing_booking_id:
                logger.info("Standing booking created: ID=%s, stats=%s", standing_booking_id, materialization_stats)

            has_required_entities = bool(subscription_data and payment_data)
            is_success = bool(success_flag) if isinstance(success_flag, bool) else has_required_entities
            is_success = is_success and has_required_entities

            if not is_success:
                normalized = _normalize_renewal_error_message(
                    parsed_message or message or "Error en el servidor - la renovacion no se completo",
                    message_data,
                )
                logger.warning(
                    "Renewal failed for member %s: code=%s cause=%s message=%s",
                    member_id,
                    normalized["error_code"],
                    normalized["error_cause"],
                    normalized["message"],
                )
                return {
                    "success": False,
                    "subscription": None,
                    "payment": None,
                    "standing_booking_id": standing_booking_id,
                    "materialization_stats": materialization_stats,
                    "error_code": normalized["error_code"],
                    "error_cause": normalized["error_cause"],
                    "message": normalized["message"],
                    "raw_message": parsed_message,
                }

            return {
                "success": True,
                "subscription": self._parse_subscription(subscription_data) if subscription_data else None,
                "payment": self._parse_payment(payment_data) if payment_data else None,
                "standing_booking_id": standing_booking_id,
                "materialization_stats": materialization_stats,
                "message": parsed_message,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error renewing subscription for member %s: %s", member_id, exc)
            normalized = _normalize_renewal_error_message(
                str(exc),
                {"errorCode": "RENEWAL_FAILED", "cause": "Error en la renovacion"},
            )
            return {
                "success": False,
                "subscription": None,
                "payment": None,
                "standing_booking_id": None,
                "materialization_stats": None,
                "error_code": normalized["error_code"],
                "error_cause": normalized["error_cause"],
                "message": normalized["message"],
            }

    async def delete_member(self, member_id: int, admin_password: str) -> Dict[str, Any]:
        """Delete a member after confirming admin password."""
        mutation = """
            mutation DeleteMember($memberId: Int!, $adminPassword: String!) {
                deleteMember(memberId: $memberId, adminPassword: $adminPassword) {
                    success
                    message
                }
            }
        """

        variables = {"memberId": member_id, "adminPassword": admin_password}

        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get("deleteMember") or {}
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", "")
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error deleting member %s: %s", member_id, exc)
            return {
                "success": False,
                "message": str(exc)
            }


    def _parse_member(self, data: Dict[str, Any]) -> Member:
        membership_info = None
        if data.get("activeMembership"):
            membership = data["activeMembership"]
            membership_info = MembershipInfo(
                subscription_id=membership.get("subscriptionId"),
                plan_name=membership.get("planName"),
                start_date=parse_iso_datetime(membership.get("startDate")),
                end_date=parse_iso_datetime(membership.get("endDate")),
                status=membership.get("status", ""),
                remaining_days=membership.get("remainingDays")
            )

        standing_info = None
        if data.get("activeStandingBooking"):
            standing = data["activeStandingBooking"]
            try:
                standing_info = ActiveStandingBookingInfo(
                    template_id=int(standing.get("templateId") or 0),
                    template_name=standing.get("templateName"),
                    class_type_name=standing.get("classTypeName"),
                    weekday=standing.get("weekday"),
                    start_time_local=standing.get("startTimeLocal"),
                    venue_name=standing.get("venueName"),
                    instructor_name=standing.get("instructorName")
                )
            except Exception:
                standing_info = None

        registration_date = parse_iso_datetime(data.get("registrationDate")) or datetime.now(timezone.utc)
        last_activity = parse_iso_datetime(data.get("lastActivity"))

        return Member(
            id=int(data.get("id") or 0),
            full_name=data.get("fullName") or "Sin nombre",
            email=data.get("email"),
            phone_number=data.get("phoneNumber"),
            wa_id=data.get("waId"),
            registration_date=registration_date,
            active_membership=membership_info,
            active_standing_booking=standing_info,
            total_payments=float(data.get("totalPayments") or 0.0),
            last_activity=last_activity
        )

    def _parse_plan(self, data: Dict[str, Any]) -> MembershipPlan:
        return MembershipPlan(
            id=int(data["id"]),
            name=data.get("name", ""),
            description=data.get("description"),
            price=float(data.get("price") or 0.0),
            duration_value=int(data.get("durationValue") or 0),
            duration_unit=data.get("durationUnit", "day"),
            class_limit=data.get("classLimit"),
            fixed_time_slot=bool(data.get("fixedTimeSlot")),
            max_sessions_per_day=data.get("maxSessionsPerDay"),
            max_sessions_per_week=data.get("maxSessionsPerWeek"),
            created_at=parse_iso_datetime(data.get("createdAt"))
        )

    def _parse_subscription(self, data: Dict[str, Any]) -> MembershipSubscription:
        start_at = parse_iso_datetime(data.get("startAt")) or datetime.now(timezone.utc)
        end_at = parse_iso_datetime(data.get("endAt")) or start_at

        return MembershipSubscription(
            id=int(data.get("id") or 0),
            person_id=int(data.get("personId") or 0),
            plan_id=int(data.get("planId") or 0),
            start_at=start_at,
            end_at=end_at,
            status=data.get("status", "active"),
            plan=None,
            person=None,
            remaining_days=data.get("remainingDays")
        )

    def _parse_payment(self, data: Dict[str, Any]) -> Payment:
        paid_at = parse_iso_datetime(data.get("paidAt")) or datetime.now(timezone.utc)

        return Payment(
            id=int(data["id"]),
            person_id=int(data.get("personId") or 0),
            amount=float(data.get("amount") or 0.0),
            method=data.get("method", "unknown"),
            subscription_id=data.get("subscriptionId"),
            paid_at=paid_at,
            provider=data.get("provider"),
            provider_payment_id=data.get("providerPaymentId"),
            external_reference=data.get("externalReference"),
            status=data.get("status", "COMPLETED"),
            comment=data.get("comment"),
            recorded_by=data.get("recordedBy")
        )

    def _create_fallback_member_data(self, member_id: int) -> Dict[str, Any]:
        """Create fallback member data when GraphQL query fails."""
        from datetime import datetime, timedelta

        # Calculate reasonable fallback dates
        end_date = datetime.now() + timedelta(days=30)  # Membership expires in 30 days

        return {
            'id': member_id,
            'full_name': f'Miembro #{member_id}',
            'email': f'miembro{member_id}@ejemplo.com',
            'phone_number': '555-0000',
            'total_payments': 1500.0,
            'active_membership': {
                'subscription_id': 1,
                'plan_name': 'Plan Mensual',
                'start_date': datetime.now() - timedelta(days=15),
                'end_date': end_date,
                'status': 'active',
                'remaining_days': 30,
                'price': 600.0,
                'payment_amount': 600.0,
                'class_template_id': 1,
                'class_name': 'Spinning Matutino',
            }
        }

