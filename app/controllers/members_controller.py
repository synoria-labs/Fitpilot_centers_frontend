"""Controller orchestrating member list operations for the members tab."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QDialog

from ..viewmodels.members_state import (
    BasicInfoPayload,
    MemberDetailState,
    MemberListState,
    MemberSummary,
    map_members,
)
from ..core.logging import get_logger
from ..views.dialogs.new_subscription_dialog import NewSubscriptionDialog
from .base_controller import BaseController


logger = get_logger(__name__)


class MembersController(BaseController):
    """Coordinates service calls and exposes view-friendly signals."""

    state_changed = Signal(object)  # MemberListState
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    basic_info_update_started = Signal(int)
    basic_info_update_succeeded = Signal(object, str)  # MemberSummary, message
    basic_info_update_failed = Signal(str)
    delete_started = Signal(int)
    delete_succeeded = Signal(int, str)
    delete_failed = Signal(int, str)
    delete_finished = Signal(int)

    def __init__(
        self,
        members_service: Any,
        standing_bookings_service: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._members_service = members_service
        self._standing_bookings_service = standing_bookings_service
        self._state = MemberListState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def state(self) -> MemberListState:
        return self._state

    def load_members(self, search: Optional[str] = None, limit: int = 100, offset: int = 0) -> None:
        """Fetch members from backend with optional filters."""
        if not self._members_service:
            logger.error("Members service not available in controller")
            self.error_occurred.emit("Servicio no disponible")
            return

        logger.info("Loading members search=%s limit=%s offset=%s", search, limit, offset)

        self._update_state(self._state.with_loading(True).with_search(search))

        self._execute_authenticated_operation(
            self._members_service,
            "get_members",
            self._on_members_loaded,
            self._on_members_error,
            limit=limit,
            offset=offset,
            search=search,
        )

    def refresh_members(self) -> None:
        """Reload members using the last known search criteria."""
        self.load_members(self._state.search)

    def get_member_detail(self, member_id: Optional[int]) -> MemberDetailState:
        summary = next((item for item in self._state.members if item.member_id == member_id), None)
        return MemberDetailState.from_summary(summary)

    def handle_new_member_request(self) -> None:
        """Handle request to create a new member by opening the subscription dialog."""
        logger.info("Opening new subscription dialog")

        if not self._members_service:
            logger.error("Members service not available for new member creation")
            self.error_occurred.emit("Servicio no disponible")
            return

        # Create controller first, then pass to dialog
        from ..controllers.new_subscription_controller import NewSubscriptionController
        controller = NewSubscriptionController(
            members_service=self._members_service,
            standing_bookings_service=self._standing_bookings_service,
            parent=self
        )

        dialog = NewSubscriptionDialog(
            controller=controller,
            parent=self.parent()
        )

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            logger.info("New member subscription created successfully")
            # Refresh the members list to show the new member
            self.refresh_members()
        else:
            logger.debug("New member subscription dialog was canceled")

    def update_basic_info(self, member_id: int, payload: BasicInfoPayload) -> None:
        """Update base member information via service."""
        if not payload.is_valid():
            logger.debug("Rejected basic info update due to invalid payload")
            self.basic_info_update_failed.emit("Completa los datos requeridos antes de guardar.")
            return

        update_method_name, args, kwargs = self._prepare_update_call(member_id, payload.to_dict())

        if update_method_name is None:
            logger.info("No update method available, applying payload locally")
            summary = self._apply_basic_info_locally(member_id, payload.to_dict())
            if summary is None:
                self.basic_info_update_failed.emit("No se pudo actualizar la informacion del socio.")
                return
            self.basic_info_update_succeeded.emit(summary, "Cambios actualizados localmente.")
            self._emit_state()
            return

        self.basic_info_update_started.emit(member_id)

        # Create wrapper for success callback with member_id and payload bound
        def on_success(result: Any) -> None:
            self._on_basic_info_update_success(member_id, payload.to_dict(), result)

        self._execute_authenticated_operation(
            self._members_service,
            update_method_name,
            on_success,
            self._on_basic_info_update_error,
            *args,
            **kwargs,
        )

    def delete_member(self, member_id: int, admin_password: str) -> None:
        """Delete a member using admin password confirmation."""
        if not admin_password:
            self.delete_failed.emit(member_id, "La contrasena de administrador es obligatoria.")
            return

        delete_method = getattr(self._members_service, "delete_member", None)
        if not callable(delete_method):
            self.delete_failed.emit(member_id, "La operacion de borrado no esta disponible.")
            return

        self.delete_started.emit(member_id)

        # Create wrappers for callbacks with member_id bound
        def on_success(payload: Any) -> None:
            self._on_delete_success(member_id, payload)

        def on_error(error: str) -> None:
            self._on_delete_error(member_id, error)

        self._execute_authenticated_operation(
            self._members_service,
            "delete_member",
            on_success,
            on_error,
            member_id=member_id,
            admin_password=admin_password,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _update_state(self, new_state: MemberListState) -> None:
        self._state = new_state
        self.loading_changed.emit(self._state.loading)
        self._emit_state()

    def _emit_state(self) -> None:
        self.state_changed.emit(self._state)

    @Slot(object)
    def _on_members_loaded(self, result: Any) -> None:
        logger.info("Members controller received result of type %s", type(result))

        if isinstance(result, dict):
            items = result.get("items", [])
            total = result.get("total", len(items))
        else:
            items = result or []
            total = len(items)

        summaries = map_members(items)
        logger.debug("Members mapped to %s summaries", len(summaries))

        state = self._state.with_members(summaries, total).with_loading(False)
        self._state = state
        self.loading_changed.emit(False)
        self._emit_state()

    @Slot(str)
    def _on_members_error(self, error: str) -> None:
        logger.error("Members loading failed: %s", error)
        state = self._state.with_members([], 0).with_loading(False)
        self._state = state
        self.loading_changed.emit(False)
        self._emit_state()
        self.error_occurred.emit(error or "No se pudieron cargar los socios.")

    def _prepare_update_call(self, member_id: int, payload: Dict[str, str]) -> tuple[Optional[str], list[Any], Dict[str, Any]]:
        candidates = [
            "update_member_basic_info",
            "update_member",
            "update_member_info",
        ]

        update_method_name = next(
            (name for name in candidates if callable(getattr(self._members_service, name, None))),
            None,
        )

        if update_method_name is None:
            return None, [], {}

        method = getattr(self._members_service, update_method_name)

        args: list[Any] = []
        kwargs: Dict[str, Any] = {}

        try:
            signature = inspect.signature(method)
            params = signature.parameters

            if "member_id" in params:
                kwargs["member_id"] = member_id
            elif "id" in params:
                kwargs["id"] = member_id
            else:
                args.append(member_id)

            if "payload" in params:
                kwargs["payload"] = payload
            elif "data" in params:
                kwargs["data"] = payload
            elif "member_data" in params:
                kwargs["member_data"] = payload
            elif "info" in params:
                kwargs["info"] = payload
            else:
                args.append(payload)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            logger.debug("Falling back to positional arguments for member update method")
            args = [member_id, payload]

        return update_method_name, args, kwargs

    @Slot(int, dict, object)
    def _on_basic_info_update_success(self, member_id: int, payload: Dict[str, str], result: Any) -> None:
        message = "No se guardaron los cambios. Causa: respuesta no confirmada por el servidor."
        success = False

        if isinstance(result, dict):
            message = result.get("message") or message
            success_flag = result.get("success")
            success = bool(success_flag) if isinstance(success_flag, bool) else False

        if not success:
            self.basic_info_update_failed.emit(message)
            return

        exists_locally = any(item.member_id == member_id for item in self._state.members)
        summary: Optional[MemberSummary]
        if exists_locally:
            summary = self._apply_basic_info_locally(member_id, payload)
            if summary is not None:
                self._emit_state()
            else:
                logger.info(
                    "Local update target missing unexpectedly for member_id=%s; using backend/payload summary.",
                    member_id,
                )
                summary = self._build_summary_from_update_result(member_id, payload, result)
        else:
            logger.info(
                "save success with member outside current dataset -> skipping local patch member_id=%s",
                member_id,
            )
            summary = self._build_summary_from_update_result(member_id, payload, result)

        self.basic_info_update_succeeded.emit(summary, message)

    @Slot(str)
    def _on_basic_info_update_error(self, error_message: str) -> None:
        logger.error("Basic info update failed: %s", error_message)
        self.basic_info_update_failed.emit(error_message or "Ocurri un error al actualizar los datos.")

    def _build_summary_from_update_result(
        self,
        member_id: int,
        payload: Dict[str, str],
        result: Any,
    ) -> MemberSummary:
        member_payload = None
        if isinstance(result, dict):
            member_payload = result.get("member")

        if isinstance(member_payload, dict):
            normalized_member = dict(member_payload)
            if normalized_member.get("id") is None and normalized_member.get("member_id") is None:
                normalized_member["id"] = member_id
            if normalized_member.get("full_name") is None and normalized_member.get("name") is None:
                normalized_member["full_name"] = normalized_member.get("fullName")
            if normalized_member.get("phone_number") is None and normalized_member.get("phone") is None:
                normalized_member["phone_number"] = normalized_member.get("phoneNumber")
            if normalized_member.get("active_membership") is None and normalized_member.get("activeMembership") is not None:
                normalized_member["active_membership"] = normalized_member.get("activeMembership")
            if (
                normalized_member.get("active_standing_booking") is None
                and normalized_member.get("activeStandingBooking") is not None
            ):
                normalized_member["active_standing_booking"] = normalized_member.get("activeStandingBooking")
            return MemberSummary.from_member(normalized_member)

        if member_payload is not None:
            try:
                return MemberSummary.from_member(member_payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not map backend member payload for member_id=%s. Falling back to request payload. error=%s",
                    member_id,
                    exc,
                )

        fallback_payload = {
            "id": member_id,
            "full_name": payload.get("name", ""),
            "email": payload.get("email", ""),
            "phone_number": payload.get("phone", ""),
        }
        return MemberSummary.from_member(fallback_payload)

    def _apply_basic_info_locally(self, member_id: int, payload: Dict[str, str]) -> Optional[MemberSummary]:
        updated_summary: Optional[MemberSummary] = None
        updated_members = []

        for summary in self._state.members:
            if summary.member_id != member_id:
                updated_members.append(summary)
                continue

            source = summary.source
            if isinstance(source, dict):
                source["full_name"] = payload["name"]
                source["name"] = payload["name"]
                source["email"] = payload["email"]
                source["mail"] = payload["email"]
                source["phone_number"] = payload["phone"]
                source["phone"] = payload["phone"]
            else:
                if hasattr(source, "full_name"):
                    setattr(source, "full_name", payload["name"])
                if hasattr(source, "email"):
                    setattr(source, "email", payload["email"])
                if hasattr(source, "phone_number"):
                    setattr(source, "phone_number", payload["phone"])
                if hasattr(source, "phone"):
                    setattr(source, "phone", payload["phone"])

            updated_summary = MemberSummary.from_member(source)
            updated_members.append(updated_summary)

        if updated_summary is None:
            logger.info(
                "Local member patch skipped; member_id=%s is not present in current dataset",
                member_id,
            )
            return None

        self._state = replace(self._state, members=tuple(updated_members))
        return updated_summary

    @Slot(int, object)
    def _on_delete_success(self, member_id: int, payload: Any) -> None:
        success = False
        message = "No se pudo eliminar al socio."

        if isinstance(payload, dict):
            success = bool(payload.get("success"))
            message = payload.get("message") or message

        if success:
            self._state = self._state.remove_member(member_id)
            self.delete_succeeded.emit(member_id, message)
            self._emit_state()
        else:
            self.delete_failed.emit(member_id, message)

        self.delete_finished.emit(member_id)

    @Slot(int, str)
    def _on_delete_error(self, member_id: int, error: str) -> None:
        logger.error("Member delete failed %s: %s", member_id, error)
        self.delete_failed.emit(member_id, error or "Hubo un error al eliminar al socio.")
        self.delete_finished.emit(member_id)
