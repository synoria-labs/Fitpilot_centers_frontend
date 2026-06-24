"""Step-up (2-step) verification service for the desktop center frontend.

Wraps the ``requestStepUpVerification`` and ``verifyStepUp`` GraphQL
mutations exposed by the gym backend so sensitive actions (password
reset, self-update) can demand an email proof before being executed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


class VerificationService:
    """GraphQL wrapper around the gym step-up mutations (email channel)."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    async def request_email_step_up(self) -> Dict[str, Any]:
        """Ask the backend to send a 6-digit code to the authenticated user's email.

        Returns a normalized dict with:
            - success (bool)
            - verificationId (str|None)
            - maskedDestination (str|None)
            - nextCooldownSeconds (int|None)
            - message (str)
        """
        mutation = """
            mutation RequestStepUp($channel: String!) {
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
        try:
            result = await self.client.execute(
                mutation, {"channel": "email"}
            )
            payload = (result or {}).get("requestStepUpVerification") or {}
            return {
                "success": bool(payload.get("success")),
                "verificationId": payload.get("verificationId"),
                "channel": payload.get("channel"),
                "maskedDestination": payload.get("maskedDestination"),
                "nextCooldownSeconds": payload.get("nextCooldownSeconds"),
                "message": payload.get("message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("request_step_up failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "verificationId": None,
                "channel": "email",
                "maskedDestination": None,
                "nextCooldownSeconds": None,
                "message": f"No se pudo solicitar la verificación: {exc}",
            }

    async def verify_step_up_code(
        self, verification_id: str, code: str
    ) -> Dict[str, Any]:
        """Submit the OTP code; on success returns the single-use proof.

        Returns a normalized dict with:
            - success (bool)
            - proof (str|None)  <- pass this to sensitive mutations as stepUpProof
            - message (str)
        """
        if not verification_id or not code:
            return {
                "success": False,
                "proof": None,
                "message": "Código o verificación inválidos",
            }
        mutation = """
            mutation VerifyStepUp($verificationId: String!, $code: String!) {
                verifyStepUp(verificationId: $verificationId, code: $code) {
                    success
                    proof
                    message
                }
            }
        """
        try:
            result = await self.client.execute(
                mutation,
                {"verificationId": verification_id, "code": code},
            )
            payload = (result or {}).get("verifyStepUp") or {}
            return {
                "success": bool(payload.get("success")),
                "proof": payload.get("proof"),
                "message": payload.get("message", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("verify_step_up failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "proof": None,
                "message": f"No se pudo verificar el código: {exc}",
            }
