"""
In-memory session cache for JWT tokens issued by the backend.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


class SessionStore:
    """Keeps the authenticated session tokens in memory."""

    def __init__(self) -> None:
        self._current_session: Optional[Dict[str, Any]] = None

    def _decode_expiration(self, token: str) -> Optional[datetime]:
        """Extracts the ``exp`` claim from a JWT without verifying it."""
        if not token:
            return None

        try:
            payload_segment = token.split(".")[1]
            padding = "=" * (-len(payload_segment) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
            claims = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            logger.debug(f"Cannot decode token expiration: {exc}")
            return None

        exp = claims.get("exp")
        if exp is None:
            return None

        try:
            return datetime.fromtimestamp(float(exp), tz=timezone.utc)
        except Exception:
            return None

    def save_session(self, access_token: str, refresh_token: str, user_data: Dict[str, Any]) -> None:
        """Stores the active session data including tokens as fallback."""

        self._current_session = {
            "access_token": access_token,  # Store as fallback (cookies are primary)
            "refresh_token": refresh_token,  # Store as fallback (cookies are primary)
            "user": user_data,
            "access_expires_at": self._decode_expiration(access_token),
            "refresh_expires_at": self._decode_expiration(refresh_token),
            "created_at": datetime.now(timezone.utc),
        }

        username = user_data.get("username", "unknown") if user_data else "unknown"
        logger.info(f"Session cached for user: {username} (tokens stored as fallback)")

    def get_access_token(self) -> Optional[str]:
        """Returns access token fallback (cookies are primary)."""
        if self._current_session:
            token = self._current_session.get("access_token")
            if token:
                logger.debug("Access token retrieved from session store fallback")
                return token
        return None

    def get_refresh_token(self) -> Optional[str]:
        """Returns refresh token fallback (cookies are primary)."""
        if self._current_session:
            token = self._current_session.get("refresh_token")
            if token:
                logger.debug("Refresh token retrieved from session store fallback")
                return token
        return None

    def update_access_token(self, new_token: str) -> None:
        """Updates access token in session store fallback."""
        if self._current_session:
            self._current_session["access_token"] = new_token
            self._current_session["access_expires_at"] = self._decode_expiration(new_token)
            logger.debug("Access token updated in session store")

    def update_refresh_token(self, new_refresh: Optional[str]) -> None:
        """Updates refresh token in session store fallback."""
        if self._current_session and new_refresh:
            self._current_session["refresh_token"] = new_refresh
            self._current_session["refresh_expires_at"] = self._decode_expiration(new_refresh)
            logger.debug("Refresh token updated in session store")

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Returns the cached user payload."""
        if self._current_session:
            return self._current_session.get("user")
        return None

    def is_authenticated(self) -> bool:
        """Indicates whether user is authenticated (has session data)."""
        return (self._current_session is not None and
                self._current_session.get("user") is not None)

    def needs_refresh(self) -> bool:
        """Token refresh is handled automatically by HTTP-only cookies."""
        return False

    def clear(self) -> None:
        """Drops every cached token and user detail."""
        self._current_session = None
        logger.info("Session cache cleared")

    def get_user_role(self) -> Optional[str]:
        """Reads the role value from the cached user payload."""
        user = self.get_current_user()
        if user:
            return user.get("role", "usuario")
        return None

    def has_permission(self, required_role: str) -> bool:
        """Checks whether the stored role matches the required hierarchy level."""
        current_role = self.get_user_role()
        if not current_role:
            return False

        role_hierarchy = {
            "admin": 3,
            "Administrador": 3,  # compatibility with API text
            "recepcionista": 2,
            "usuario": 1,
        }

        current_level = role_hierarchy.get(current_role, 0)
        required_level = role_hierarchy.get(required_role, 999)
        return current_level >= required_level
