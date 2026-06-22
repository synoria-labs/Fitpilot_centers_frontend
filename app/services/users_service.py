"""Service layer for user (login account) management (GraphQL)."""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.logging import get_logger
from ..utils.datetime_helpers import parse_iso_datetime
from ..models.base import AppUser, AppRole

logger = get_logger(__name__)


_USER_FIELDS = """
    accountId
    personId
    username
    isActive
    fullName
    email
    phoneNumber
    createdAt
    roles {
        id
        code
        description
    }
"""


class UsersService:
    """GraphQL operations to manage login accounts (staff users) and their roles."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_role(self, data: Dict[str, Any]) -> AppRole:
        return AppRole(
            id=int(data["id"]),
            code=data.get("code", ""),
            description=data.get("description"),
        )

    def _parse_user(self, data: Dict[str, Any]) -> AppUser:
        return AppUser(
            account_id=int(data["accountId"]),
            person_id=int(data["personId"]),
            username=data.get("username", ""),
            is_active=bool(data.get("isActive", True)),
            full_name=data.get("fullName"),
            email=data.get("email"),
            phone_number=data.get("phoneNumber"),
            created_at=parse_iso_datetime(data.get("createdAt")),
            roles=[self._parse_role(r) for r in (data.get("roles") or [])],
        )

    def _input_from_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map a dialog dict to a GraphQL input payload (camelCase)."""
        return {
            "fullName": data.get("full_name"),
            "username": data.get("username"),
            "email": data.get("email") or None,
            "phoneNumber": data.get("phone_number") or None,
            "roleIds": [int(r) for r in (data.get("role_ids") or [])],
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    async def get_users(self, include_inactive: bool = True) -> List[AppUser]:
        """Fetch all login accounts (includes inactive by default)."""
        query = """
            query AppUsers($includeInactive: Boolean) {
                appUsers(includeInactive: $includeInactive) {
                    %s
                }
            }
        """ % _USER_FIELDS

        try:
            result = await self.client.execute(query, {"includeInactive": include_inactive})
            if result is None:
                logger.error("appUsers query returned None")
                return []
            users = result.get("appUsers", []) or []
            return [self._parse_user(u) for u in users]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching users: %s", exc, exc_info=True)
            return []

    async def get_roles(self) -> List[AppRole]:
        """Fetch the available roles to assign to users."""
        query = """
            query Roles {
                roles { id code description }
            }
        """
        try:
            result = await self.client.execute(query)
            if result is None:
                return []
            roles = result.get("roles", []) or []
            return [self._parse_role(r) for r in roles]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching roles: %s", exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    async def create_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation CreateUser($input: CreateUserInput!) {
                createUser(input: $input) {
                    success
                    message
                    user { %s }
                }
            }
        """ % _USER_FIELDS

        payload = self._input_from_data(data)
        payload["password"] = data.get("password") or ""
        variables = {"input": payload}
        return await self._run_user_mutation(mutation, variables, "createUser")

    async def update_user(self, account_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation UpdateUser($input: UpdateUserInput!) {
                updateUser(input: $input) {
                    success
                    message
                    user { %s }
                }
            }
        """ % _USER_FIELDS

        payload = self._input_from_data(data)
        payload["accountId"] = int(account_id)
        if "is_active" in data and data.get("is_active") is not None:
            payload["isActive"] = bool(data.get("is_active"))
        variables = {"input": payload}
        return await self._run_user_mutation(mutation, variables, "updateUser")

    async def set_user_active(self, account_id: int, is_active: bool) -> Dict[str, Any]:
        mutation = """
            mutation SetUserActive($accountId: Int!, $isActive: Boolean!) {
                setUserActive(accountId: $accountId, isActive: $isActive) {
                    success
                    message
                    user { %s }
                }
            }
        """ % _USER_FIELDS

        variables = {"accountId": int(account_id), "isActive": bool(is_active)}
        return await self._run_user_mutation(mutation, variables, "setUserActive")

    async def reset_password(self, account_id: int, password: str) -> Dict[str, Any]:
        mutation = """
            mutation ResetUserPassword($accountId: Int!, $password: String!) {
                resetUserPassword(accountId: $accountId, password: $password) {
                    success
                    message
                }
            }
        """

        variables = {"accountId": int(account_id), "password": password}
        return await self._run_user_mutation(mutation, variables, "resetUserPassword")

    async def _run_user_mutation(
        self, mutation: str, variables: Dict[str, Any], root_field: str
    ) -> Dict[str, Any]:
        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get(root_field) or {}
            user_data = payload.get("user")
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "user": self._parse_user(user_data) if user_data else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", root_field, exc)
            return {"success": False, "message": str(exc), "user": None}
