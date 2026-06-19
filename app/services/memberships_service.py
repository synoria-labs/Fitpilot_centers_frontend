"""Service layer for membership-plan catalog CRUD (GraphQL)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from ..utils.datetime_helpers import parse_iso_datetime
from ..models.base import MembershipPlan

logger = get_logger(__name__)


_PLAN_FIELDS = """
    id
    name
    description
    price
    durationValue
    durationUnit
    classLimit
    planType
    fixedTimeSlot
    isActive
    maxSessionsPerDay
    maxSessionsPerWeek
    createdAt
"""


class MembershipsService:
    """GraphQL operations to manage the membership-plan catalog."""

    def __init__(self, graphql_client) -> None:
        self.client = graphql_client

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_plan(self, data: Dict[str, Any]) -> MembershipPlan:
        return MembershipPlan(
            id=int(data["id"]),
            name=data.get("name", ""),
            description=data.get("description"),
            price=float(data.get("price") or 0.0),
            duration_value=int(data.get("durationValue") or 0),
            duration_unit=data.get("durationUnit", "day"),
            class_limit=data.get("classLimit"),
            plan_type=data.get("planType", "fixed_schedule"),
            fixed_time_slot=bool(data.get("fixedTimeSlot")),
            is_active=bool(data.get("isActive", True)),
            max_sessions_per_day=data.get("maxSessionsPerDay"),
            max_sessions_per_week=data.get("maxSessionsPerWeek"),
            created_at=parse_iso_datetime(data.get("createdAt")),
        )

    def _input_from_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map a dialog dict to a GraphQL input payload (camelCase)."""
        payload: Dict[str, Any] = {
            "name": data.get("name"),
            "price": float(data.get("price") or 0),
            "durationValue": int(data.get("duration_value") or 0),
            "durationUnit": data.get("duration_unit") or "day",
            "description": data.get("description") or None,
            "classLimit": data.get("class_limit"),
            "planType": data.get("plan_type") or "fixed_schedule",
            "maxSessionsPerDay": data.get("max_sessions_per_day"),
            "maxSessionsPerWeek": data.get("max_sessions_per_week"),
        }
        if "is_active" in data and data.get("is_active") is not None:
            payload["isActive"] = bool(data.get("is_active"))
        return payload

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    async def get_plans(self, include_inactive: bool = True) -> List[MembershipPlan]:
        """Fetch the full plan catalog (includes inactive plans by default)."""
        query = """
            query GetMembershipPlans($includeInactive: Boolean) {
                membershipPlans(includeInactive: $includeInactive) {
                    %s
                }
            }
        """ % _PLAN_FIELDS

        try:
            result = await self.client.execute(query, {"includeInactive": include_inactive})
            if result is None:
                logger.error("membershipPlans query returned None")
                return []
            plans = result.get("membershipPlans", []) or []
            return [self._parse_plan(plan) for plan in plans]
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching membership plans: %s", exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    async def create_plan(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation CreateMembershipPlan($input: CreateMembershipPlanInput!) {
                createMembershipPlan(input: $input) {
                    success
                    message
                    plan { %s }
                }
            }
        """ % _PLAN_FIELDS

        variables = {"input": self._input_from_data(data)}
        return await self._run_plan_mutation(mutation, variables, "createMembershipPlan")

    async def update_plan(self, plan_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
            mutation UpdateMembershipPlan($input: UpdateMembershipPlanInput!) {
                updateMembershipPlan(input: $input) {
                    success
                    message
                    plan { %s }
                }
            }
        """ % _PLAN_FIELDS

        payload = self._input_from_data(data)
        payload["planId"] = int(plan_id)
        variables = {"input": payload}
        return await self._run_plan_mutation(mutation, variables, "updateMembershipPlan")

    async def set_plan_active(self, plan_id: int, is_active: bool) -> Dict[str, Any]:
        mutation = """
            mutation SetMembershipPlanActive($planId: Int!, $isActive: Boolean!) {
                setMembershipPlanActive(planId: $planId, isActive: $isActive) {
                    success
                    message
                    plan { %s }
                }
            }
        """ % _PLAN_FIELDS

        variables = {"planId": int(plan_id), "isActive": bool(is_active)}
        return await self._run_plan_mutation(mutation, variables, "setMembershipPlanActive")

    async def _run_plan_mutation(
        self, mutation: str, variables: Dict[str, Any], root_field: str
    ) -> Dict[str, Any]:
        try:
            result = await self.client.execute(mutation, variables)
            payload = (result or {}).get(root_field) or {}
            plan_data = payload.get("plan")
            return {
                "success": bool(payload.get("success")),
                "message": payload.get("message", ""),
                "plan": self._parse_plan(plan_data) if plan_data else None,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", root_field, exc)
            return {"success": False, "message": str(exc), "plan": None}
