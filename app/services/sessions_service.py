"""
Servicio para gestión de sesiones de usuario.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..core.logging import get_logger
from ..utils.datetime_helpers import parse_iso_datetime

logger = get_logger(__name__)


class SessionsService:
    """Servicio para gestionar sesiones de usuario."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    async def get_my_sessions(self) -> List[Dict[str, Any]]:
        """Obtiene las sesiones activas del usuario autenticado."""
        query = """
        query GetMySessions {
            mySessions {
                id
                sessionId
                deviceName
                ipAddress
                userAgent
                lastActiveAt
                createdAt
                revokedAt
                isCurrent
            }
        }
        """

        try:
            result = await self.client.execute(query)

            if not result:
                logger.error("Failed to fetch user sessions")
                return []

            sessions = result.get("mySessions", [])
            logger.info(f"Fetched {len(sessions)} user sessions")

            # Convertir las sesiones a formato más amigable
            parsed_sessions = []
            for session in sessions:
                parsed = {
                    "id": session.get("id"),
                    "session_id": session.get("sessionId"),
                    "device_name": session.get("deviceName") or "Dispositivo desconocido",
                    "ip_address": session.get("ipAddress") or "N/A",
                    "user_agent": session.get("userAgent") or "",
                    "last_active_at": parse_iso_datetime(session.get("lastActiveAt")),
                    "created_at": parse_iso_datetime(session.get("createdAt")),
                    "revoked_at": parse_iso_datetime(session.get("revokedAt")),
                    "is_current": session.get("isCurrent", False),
                }
                parsed_sessions.append(parsed)

            # Ordenar por última actividad (sesión actual primero, luego por fecha)
            parsed_sessions.sort(
                key=lambda s: (not s["is_current"], s["last_active_at"] or datetime.min),
                reverse=True
            )

            return parsed_sessions

        except Exception as e:
            logger.error(f"Error fetching user sessions: {e}")
            return []

    async def revoke_session(self, session_id: str) -> bool:
        """Revoca una sesión específica."""
        mutation = """
        mutation RevokeSession($input: RevokeSessionInput!) {
            revokeSession(input: $input)
        }
        """

        variables = {
            "input": {
                "sessionId": session_id
            }
        }

        try:
            result = await self.client.execute(mutation, variables)

            if result and result.get("revokeSession"):
                logger.info(f"Session {session_id[:8]}... revoked successfully")
                return True
            else:
                logger.error(f"Failed to revoke session {session_id[:8]}...")
                return False

        except Exception as e:
            logger.error(f"Error revoking session {session_id[:8]}...: {e}")
            return False

    def format_last_active(self, last_active: Optional[datetime]) -> str:
        """Formatea la última actividad de forma legible."""
        if not last_active:
            return "Nunca"

        now = datetime.now(last_active.tzinfo)
        diff = now - last_active

        if diff.days > 30:
            return f"Hace {diff.days // 30} meses"
        elif diff.days > 0:
            return f"Hace {diff.days} días"
        elif diff.seconds > 3600:
            return f"Hace {diff.seconds // 3600} horas"
        elif diff.seconds > 60:
            return f"Hace {diff.seconds // 60} minutos"
        else:
            return "Ahora"

    def get_device_icon(self, device_name: str) -> str:
        """Retorna un ícono Unicode según el tipo de dispositivo."""
        device_lower = device_name.lower()

        if "iphone" in device_lower or "ios" in device_lower:
            return "📱"  # iPhone
        elif "android" in device_lower:
            return "📱"  # Android
        elif "windows" in device_lower:
            return "💻"  # Windows
        elif "mac" in device_lower or "darwin" in device_lower:
            return "💻"  # Mac
        elif "linux" in device_lower:
            return "💻"  # Linux
        else:
            return "🖥️"  # Dispositivo genérico
