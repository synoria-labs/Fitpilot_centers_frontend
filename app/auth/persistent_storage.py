"""
Persistent Storage Module for FitPilot

This module provides secure persistent storage for authentication tokens
using the operating system's keyring service (Windows Credential Manager,
macOS Keychain, Linux Secret Service).
"""

import keyring
from typing import Optional
from ..core.logging import get_logger

logger = get_logger(__name__)

# Service name for keyring
SERVICE_NAME = "FitPilot"

# Key names for stored credentials
KEY_REFRESH_TOKEN = "refresh_token"
KEY_USERNAME = "username"


class PersistentStorage:
    """Manages persistent storage of authentication credentials using OS keyring."""

    @staticmethod
    def save_refresh_token(username: str, refresh_token: str) -> bool:
        """
        Save refresh token securely in the OS keyring.

        Args:
            username: The username associated with the token
            refresh_token: The refresh token to store

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Store the refresh token
            keyring.set_password(SERVICE_NAME, f"{username}_{KEY_REFRESH_TOKEN}", refresh_token)

            # Store the username so we can retrieve it later
            keyring.set_password(SERVICE_NAME, KEY_USERNAME, username)

            logger.info(f"Refresh token saved securely for user: {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to save refresh token: {e}")
            return False

    @staticmethod
    def load_refresh_token() -> Optional[tuple[str, str]]:
        """
        Load refresh token from the OS keyring.

        Returns:
            Optional[tuple[str, str]]: Tuple of (username, refresh_token) if found, None otherwise
        """
        try:
            # First, retrieve the stored username
            username = keyring.get_password(SERVICE_NAME, KEY_USERNAME)
            if not username:
                logger.debug("No stored username found in keyring")
                return None

            # Then retrieve the refresh token for that username
            refresh_token = keyring.get_password(SERVICE_NAME, f"{username}_{KEY_REFRESH_TOKEN}")
            if not refresh_token:
                logger.debug(f"No stored refresh token found for user: {username}")
                return None

            logger.info(f"Refresh token loaded for user: {username}")
            return (username, refresh_token)
        except Exception as e:
            logger.error(f"Failed to load refresh token: {e}")
            return None

    @staticmethod
    def clear_refresh_token() -> bool:
        """
        Clear the stored refresh token from the OS keyring.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the username first
            username = keyring.get_password(SERVICE_NAME, KEY_USERNAME)

            if username:
                # Delete the refresh token
                try:
                    keyring.delete_password(SERVICE_NAME, f"{username}_{KEY_REFRESH_TOKEN}")
                except keyring.errors.PasswordDeleteError:
                    logger.debug(f"No refresh token to delete for user: {username}")

                # Delete the username
                try:
                    keyring.delete_password(SERVICE_NAME, KEY_USERNAME)
                except keyring.errors.PasswordDeleteError:
                    logger.debug("No username to delete")

                logger.info(f"Refresh token cleared for user: {username}")
            else:
                logger.debug("No stored credentials found to clear")

            return True
        except Exception as e:
            logger.error(f"Failed to clear refresh token: {e}")
            return False

    @staticmethod
    def has_stored_session() -> bool:
        """
        Check if there's a stored session in the keyring.

        Returns:
            bool: True if a stored session exists, False otherwise
        """
        try:
            username = keyring.get_password(SERVICE_NAME, KEY_USERNAME)
            if not username:
                return False

            refresh_token = keyring.get_password(SERVICE_NAME, f"{username}_{KEY_REFRESH_TOKEN}")
            return refresh_token is not None
        except Exception as e:
            logger.error(f"Failed to check for stored session: {e}")
            return False


# Convenience functions for backward compatibility
def save_refresh_token(username: str, refresh_token: str) -> bool:
    """Save refresh token securely."""
    return PersistentStorage.save_refresh_token(username, refresh_token)


def load_refresh_token() -> Optional[tuple[str, str]]:
    """Load refresh token from storage."""
    return PersistentStorage.load_refresh_token()


def clear_refresh_token() -> bool:
    """Clear stored refresh token."""
    return PersistentStorage.clear_refresh_token()


def has_stored_session() -> bool:
    """Check if a stored session exists."""
    return PersistentStorage.has_stored_session()
