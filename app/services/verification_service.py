"""Service layer for step-up (2-step) verification (GraphQL).

Client for the backend's step-up flow: request a one-time code to the
authenticated user's own email/phone, verify it, and obtain a single-use proof
that is then passed as ``stepUpProof`` to a sensitive mutation (e.g. resetting a
user's password). The backend gates these actions behind ``STEP_UP_ENABLED``.
"""
from __future__ import annotations

from typing import Any, Dict

from ..core.logging import get_logger

logger = get_logger(__name__)


class VerificationService:
    """GraphQL operations to satisfy a step-up (2FA) challenge."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def request_step_up(self, channel: str = "email") -> Dict[str, Any]:
        """Ask the backend to send a step-up code to the caller's own contact.

        The backend resolves the destination (email/phone) from the authenticated
        session, so no destination is sent from the client.
        """
        mutation = """
            mutation RequestStepUpVerification($channel: String!) {
                requestStepUpVerification(channel: $channel) {
                    success
                    verificationId
                    channel
                    maskedDestination
                    nextCooldownSeconds
                    message
                }
            }
        """
        variables = {"channel": channel}
        try:
            result = await self.client.execute(mutation, variables)
            if result is None:
                return {
                    "success": False,
                    "verification_id": None,
                    "channel": channel,
                    "masked_destination": None,
                    "next_cooldown_seconds": None,
                    "message": getattr(self.client, "last_error", None)
                    or "No se pudo contactar el servicio de verificación",
                }
            payload = result.get("requestStepUpVerification") or {}
            return {
                "success": bool(payload.get("success")),
                "verification_id": payload.get("verificationId"),
                "channel": payload.get("channel"),
                "masked_destination": payload.get("maskedDestination"),
                "next_cooldown_seconds": payload.get("nextCooldownSeconds"),
                "message": payload.get("message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error requesting step-up verification: %s", exc)
            return {
                "success": False,
                "verification_id": None,
                "channel": channel,
                "masked_destination": None,
                "next_cooldown_seconds": None,
                "message": str(exc),
            }

    async def verify_step_up(self, verification_id: str, code: str) -> Dict[str, Any]:
        """Check the code; on success returns a single-use ``proof`` string."""
        mutation = """
            mutation VerifyStepUp($verificationId: String!, $code: String!) {
                verifyStepUp(verificationId: $verificationId, code: $code) {
                    success
                    proof
                    message
                }
            }
        """
        variables = {"verificationId": verification_id, "code": code}
        try:
            result = await self.client.execute(mutation, variables)
            if result is None:
                return {
                    "success": False,
                    "proof": None,
                    "message": getattr(self.client, "last_error", None)
                    or "No se pudo contactar el servicio de verificación",
                }
            payload = result.get("verifyStepUp") or {}
            return {
                "success": bool(payload.get("success")),
                "proof": payload.get("proof"),
                "message": payload.get("message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error verifying step-up code: %s", exc)
            return {"success": False, "proof": None, "message": str(exc)}
