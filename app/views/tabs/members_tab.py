"""Members tab view."""

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QTimer,
    Signal,
    Slot,
    QEvent,
    QRect,
    Qt,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QPalette 

from ...controllers.members_controller import MembersController
from ...core import container, get_logger
from ...viewmodels.members_state import (
    BasicInfoPayload,
    MemberDetailState,
    MemberListState,
    MemberSummary,
)
from ..dialogs.admin_password_dialog import AdminPasswordDialog
from ..dialogs.reschedule_standing_booking_dialog import RescheduleStandingBookingDialog
from ..dialogs.renew_subscription_dialog import RenewSubscriptionDialog
from ...controllers.renew_subscription_controller import RenewSubscriptionController
from .members.member_detail_card import MemberDetailCard
from .members.member_table_widget import MemberTableWidget
from ...utils.dialog_helpers import show_error, show_info, show_warning


logger = get_logger(__name__)


class MembersTab(QWidget):
    """Widget used to list and search gym members following MVC separation."""

    search_requested = Signal(str)
    member_selected = Signal(int)
    new_member_requested = Signal()
    renew_members_requested = Signal(int)
    renewal_submitted = Signal(dict)

    def __init__(self) -> None:
        super().__init__()

        logger.info("Initializing MembersTab")

        try:
            members_service = container.get("members_service")
            standing_bookings_service = container.get("standing_bookings_service")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve services from container: %s", exc)
            raise

        self.controller = MembersController(members_service, standing_bookings_service, self)

        self.members_service = members_service
        self.standing_bookings_service = standing_bookings_service

        self._state: MemberListState = self.controller.state()
        self._loading: bool = False
        self._card_visible: bool = False
        self._card_width: int = 320
        self._pending_delete_member_id: Optional[int] = None
        self._delete_in_progress: bool = False
        self._basic_update_in_progress: bool = False
        self._current_member_id: Optional[int] = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self._perform_search)

        self._requested_search: Optional[str] = None
        self._pending_search_operation: Optional[object] = None  # Track pending search operations

        self._build_ui()
        self._connect_signals()

        # --- NUEVO: click-away global para cerrar panel fuera de tabla/tarjeta
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        logger.info("Requesting initial members load")
        self.controller.load_members()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        toolbar_layout = QHBoxLayout()
        search_label = QLabel("Buscar:")
        toolbar_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nombre, telefono o email...")
        toolbar_layout.addWidget(self.search_input)

        toolbar_layout.addStretch()

        self.new_button = QPushButton("+ Nuevo Socio")
        toolbar_layout.addWidget(self.new_button)

        self.renew_button = QPushButton("Renovar suscripcion")
        self.renew_button.setEnabled(False)
        toolbar_layout.addWidget(self.renew_button)

        layout.addLayout(toolbar_layout)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.member_table = MemberTableWidget(self)
        content_layout.addWidget(self.member_table, 1)

        self.side_card_container = QWidget(self)
        self.side_card_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.side_card_container.setMinimumWidth(0)
        self.side_card_container.setMaximumWidth(0)
        self.side_card_container.setVisible(False)

        side_card_layout = QVBoxLayout(self.side_card_container)
        side_card_layout.setContentsMargins(0, 0, 0, 0)
        side_card_layout.setSpacing(0)

        self.side_card_frame = QFrame(self.side_card_container)
        self.side_card_frame.setFrameShape(QFrame.Shape.StyledPanel)

        palette = QApplication.palette()
        background_color = palette.color(QPalette.ColorRole.Base).name()
        border_color = palette.color(QPalette.ColorRole.Mid).name()
        self.side_card_frame.setStyleSheet(
            f"#memberCardFrame {{background-color: {background_color}; "
            f"border: 1px solid {border_color}; border-radius: 8px;}}"
        )
        self.side_card_frame.setObjectName("memberCardFrame")
        self.side_card_frame.setFixedWidth(self._card_width)

        frame_layout = QVBoxLayout(self.side_card_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self.member_card = MemberDetailCard(self.side_card_frame)
        frame_layout.addWidget(self.member_card)

        side_card_layout.addWidget(self.side_card_frame)
        content_layout.addWidget(self.side_card_container)
        layout.addLayout(content_layout)

        status_layout = QHBoxLayout()
        self.status_label = QLabel("0 socios")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Prepare animations
        self.side_card_opacity = QGraphicsOpacityEffect()
        self.side_card_frame.setGraphicsEffect(self.side_card_opacity)
        self.side_card_opacity.setOpacity(0.0)

        self.card_animation = QPropertyAnimation(self.side_card_container, b"maximumWidth")
        self.card_animation.setDuration(280)
        self.card_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.opacity_animation = QPropertyAnimation(self.side_card_opacity, b"opacity")
        self.opacity_animation.setDuration(280)
        self.opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._card_animation_group = QParallelAnimationGroup(self)
        self._card_animation_group.addAnimation(self.card_animation)
        self._card_animation_group.addAnimation(self.opacity_animation)

    def _connect_signals(self) -> None:
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.new_button.clicked.connect(self.new_member_requested.emit)
        self.new_member_requested.connect(self.controller.handle_new_member_request)
        self.renew_button.clicked.connect(self._on_renew_clicked)

        self.member_table.selection_changed.connect(self._on_table_selection_changed)
        self.member_table.activated.connect(self._on_table_activated)

        self.member_card.save_requested.connect(self._on_basic_info_save_requested)
        self.member_card.delete_requested.connect(self._on_delete_requested)
        self.member_card.edit_mode_changed.connect(self._on_edit_mode_changed)
        self.member_card.reschedule_requested.connect(self._on_reschedule_requested)

        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.loading_changed.connect(self._on_loading_changed)
        self.controller.error_occurred.connect(self._on_error)

        self.controller.basic_info_update_started.connect(self._on_basic_info_update_started)
        self.controller.basic_info_update_succeeded.connect(self._on_basic_info_update_succeeded)
        self.controller.basic_info_update_failed.connect(self._on_basic_info_update_failed)

        self.controller.delete_started.connect(self._on_delete_started)
        self.controller.delete_succeeded.connect(self._on_delete_succeeded)
        self.controller.delete_failed.connect(self._on_delete_failed)
        self.controller.delete_finished.connect(self._on_delete_finished)

    # ------------------------------------------------------------------
    # Controller callbacks
    # ------------------------------------------------------------------
    @Slot(object)
    def _on_state_changed(self, state: MemberListState) -> None:
        logger.debug("MembersTab received state update with %s members", len(state.members))
        previous_id = self._current_member_id if self._current_member_id else None
        self._state = state

        self.member_table.populate(state.members)
        if previous_id:
            restored = self.member_table.select_member(previous_id)
            if not restored:
                logger.info(
                    "selected member not present after state refresh -> clearing selection/card member_id=%s",
                    previous_id,
                )
                self._current_member_id = None
                self.member_selected.emit(-1)
                self.member_card.reset()
                self._hide_member_card()
        else:
            self.member_table.select_member(None)

        self._update_status_label(state)
        self._update_action_buttons()

    @Slot(bool)
    def _on_loading_changed(self, loading: bool) -> None:
        self._loading = loading
        if self._basic_update_in_progress:
            self.member_table.setEnabled(False)
            self.search_input.setEnabled(False)
            self.new_button.setEnabled(False)
            self.renew_button.setEnabled(False)
            if loading:
                self.status_label.setText("Guardando cambios...")
            else:
                self._update_action_buttons()
                self._update_status_label(self._state)
            return

        # Mantener el buscador habilitado durante las cargas para no perder el foco al tipear.
        # Solo se deshabilita cuando la tarjeta está en modo edición.
        self.search_input.setEnabled(not self.member_card.is_editing())
        self.new_button.setEnabled(not loading)
        self.member_table.setEnabled(not loading and not self.member_card.is_editing())
        if loading:
            self.renew_button.setEnabled(False)
            self.status_label.setText("Cargando socios...")
        else:
            self._update_action_buttons()
            self._update_status_label(self._state)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        show_warning(self, message or "No se pudieron cargar los socios.", title="Socios")

    @Slot(int)
    def _on_basic_info_update_started(self, member_id: int) -> None:  # noqa: ARG002
        self._basic_update_in_progress = True
        self.member_card.set_loading(True)
        self.member_table.setEnabled(False)
        self.search_input.setEnabled(False)
        self.new_button.setEnabled(False)
        self.renew_button.setEnabled(False)

    @Slot(object, str)
    def _on_basic_info_update_succeeded(self, summary: MemberSummary, message: str) -> None:
        self.member_card.set_loading(False)
        is_member_visible = any(item.member_id == summary.member_id for item in self._state.members)

        if is_member_visible:
            self.member_table.upsert_member(summary)
            selected = self.member_table.select_member(summary.member_id)
            self.member_card.set_state(MemberDetailState.from_summary(summary))
            if selected and summary.member_id:
                self._current_member_id = summary.member_id
                self.member_selected.emit(summary.member_id)
                self._show_member_card()
        else:
            logger.info(
                "save success with member outside current dataset -> refresh requested member_id=%s",
                summary.member_id,
            )
            self._current_member_id = None
            self.member_selected.emit(-1)
            self.member_card.reset()
            self.member_table.select_member(None)
            self._hide_member_card()
            self.controller.refresh_members()

        self._basic_update_in_progress = False
        self.member_table.setEnabled(not self._loading and not self.member_card.is_editing() and not self._delete_in_progress)
        self.search_input.setEnabled(not self._loading and not self.member_card.is_editing())
        self.new_button.setEnabled(not self._loading and not self._delete_in_progress)
        self._update_action_buttons()
        if message:
            show_info(self, message, title="Editar socio")

    @Slot(str)
    def _on_basic_info_update_failed(self, message: str) -> None:
        self.member_card.set_loading(False)
        self._basic_update_in_progress = False
        self.member_table.setEnabled(not self._loading and not self.member_card.is_editing() and not self._delete_in_progress)
        self.search_input.setEnabled(not self._loading and not self.member_card.is_editing())
        self.new_button.setEnabled(not self._loading and not self._delete_in_progress)
        show_error(self, message, title="Editar socio")
        self._update_action_buttons()

    @Slot(int)
    def _on_delete_started(self, member_id: int) -> None:  # noqa: ARG002
        self._delete_in_progress = True
        self.member_card.set_loading(True)
        self.member_table.setEnabled(False)
        self.search_input.setEnabled(False)
        self.new_button.setEnabled(False)
        self.renew_button.setEnabled(False)
        self.status_label.setText("Eliminando socio...")

    @Slot(int, str)
    def _on_delete_succeeded(self, member_id: int, message: str) -> None:
        logger.info("Member %s deleted", member_id)
        show_info(self, message or "Socio eliminado correctamente.", title="Eliminar socio")
        if self._current_member_id == member_id:
            self._current_member_id = None
            self.member_card.reset()
            self._hide_member_card()
        self.member_table.remove_member(member_id)
        self.controller.refresh_members()

    @Slot(int, str)
    def _on_delete_failed(self, member_id: int, message: str) -> None:  # noqa: ARG002
        show_error(self, message or "Hubo un error al eliminar al socio.", title="Eliminar socio")

    @Slot(int)
    def _on_delete_finished(self, member_id: int) -> None:  # noqa: ARG002
        self._delete_in_progress = False
        self.member_card.set_loading(False)
        controls_available = not self._loading and not self._basic_update_in_progress
        self.member_table.setEnabled(controls_available and not self.member_card.is_editing())
        self.search_input.setEnabled(controls_available and not self.member_card.is_editing())
        self.new_button.setEnabled(controls_available)
        self._update_action_buttons()
        if not self._loading:
            self._update_status_label(self._state)

    # ------------------------------------------------------------------
    # UI Callbacks
    # ------------------------------------------------------------------
    @Slot(str)
    def _on_search_text_changed(self, text: str) -> None:
        self.search_requested.emit(text)
        self._requested_search = text.strip() or None
        self._search_timer.start()

    @Slot()
    def _perform_search(self) -> None:
        # Cancelar búsqueda pendiente si existe (evitar procesar resultados obsoletos)
        if self._pending_search_operation is not None:
            logger.debug("Canceling pending search operation before new search")
            try:
                # Desconectar TODAS las señales de esta operación privada local
                # Es seguro usar disconnect() sin parámetros porque:
                # 1. La operación es privada (_pending_search_operation)
                # 2. Solo este componente conecta slots a estas señales
                # 3. Queremos cancelar TODOS los callbacks pendientes
                self._pending_search_operation.success.disconnect()
                self._pending_search_operation.error.disconnect()
            except Exception:
                pass  # Señales ya desconectadas o operación ya terminada
            self._pending_search_operation = None

        logger.debug("Performing search with criteria: %s", self._requested_search)
        self.controller.load_members(self._requested_search)

    @Slot(object)
    def _on_table_selection_changed(self, summary: Optional[MemberSummary]) -> None:
        if summary is None:
            self._current_member_id = None
            self.member_selected.emit(-1)
            self.member_card.reset()
            self._hide_member_card()
            self._update_action_buttons()
            return

        self._current_member_id = summary.member_id
        self._pending_delete_member_id = summary.member_id
        self.member_selected.emit(summary.member_id)

        self.member_card.set_state(MemberDetailState.from_summary(summary))
        self._show_member_card()
        self._update_action_buttons()

    @Slot(object)
    def _on_table_activated(self, summary: Optional[MemberSummary]) -> None:
        if summary is None:
            return
        logger.info("Member double-clicked: %s", summary.member_id)

    @Slot(int, object)
    def _on_basic_info_save_requested(self, member_id: int, payload: BasicInfoPayload) -> None:
        logger.info("Submitting basic info update for member_id=%s", member_id)
        self.controller.update_basic_info(member_id, payload)

    @Slot(int)
    def _on_delete_requested(self, member_id: int) -> None:
        dialog = AdminPasswordDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        admin_password = getattr(dialog, "password", "")
        if not admin_password:
            show_warning(self, "La contrasena de administrador es obligatoria.", title="Eliminar socio")
            return

        self._pending_delete_member_id = member_id
        self.controller.delete_member(member_id, admin_password)

    @Slot(bool)
    def _on_edit_mode_changed(self, editing: bool) -> None:
        logger.info("MembersTab edit mode changed: editing=%s member_id=%s", editing, self._current_member_id)
        if self._basic_update_in_progress:
            self.member_table.setEnabled(False)
            self.search_input.setEnabled(False)
            self.new_button.setEnabled(False)
            self.renew_button.setEnabled(False)
            return

        controls_available = not editing and not self._loading and not self._delete_in_progress
        self.member_table.setEnabled(controls_available)
        self.search_input.setEnabled(not editing and not self._loading)
        self.new_button.setEnabled(controls_available)
        if editing:
            self.renew_button.setEnabled(False)
        else:
            self._update_action_buttons()

    @Slot()
    def _on_renew_clicked(self) -> None:
        if self._loading or self._current_member_id is None:
            return

        summary = self.member_table.current_summary()
        if summary is None:
            return

        self.renew_members_requested.emit(summary.member_id)

        controller = RenewSubscriptionController(
            members_service=self.members_service,
            standing_bookings_service=self.standing_bookings_service,
            parent=self,
        )

        dialog = RenewSubscriptionDialog(
            controller=controller,
            member_id=summary.member_id,
            member_name=summary.full_name,
            member_data=summary.source,
            parent=self,
        )

        # Connect subscription_renewed signal to refresh UI
        dialog.subscription_renewed.connect(self._on_subscription_renewed)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            payload = getattr(dialog, "payload", None)
            if payload is not None:
                self.renewal_submitted.emit(payload)

    @Slot(int)
    def _on_reschedule_requested(self, member_id: int) -> None:
        if self._loading or member_id <= 0:
            return

        summary = self.member_table.current_summary()
        if summary is None or summary.member_id != member_id:
            summary = next((item for item in self._state.members if item.member_id == member_id), None)

        if summary is None:
            show_warning(self, "No se pudo cargar el socio seleccionado.", title="Cambiar clase")
            return

        detail = MemberDetailState.from_summary(summary)
        if detail.standing_booking is None:
            show_warning(self, "Este socio no tiene un horario fijo activo.", title="Cambiar clase")
            return

        dialog = RescheduleStandingBookingDialog(
            member_id=member_id,
            member_name=detail.full_name,
            standing_template_id=detail.standing_booking.template_id,
            membership_start=detail.membership.start_date,
            membership_end=detail.membership.end_date,
            membership_remaining_days=detail.membership.remaining_days,
            standing_bookings_service=self.standing_bookings_service,
            parent=self,
        )

        dialog.exec()

    @Slot(int, dict)
    def _on_subscription_renewed(self, member_id: int, result: dict) -> None:
        """Handle subscription renewal completion and refresh UI."""
        logger.info(f"Subscription renewed for member {member_id}, refreshing UI")

        # Refresh the member data in the controller
        # This will update both the table and the detail card
        self.controller.get_member_detail(member_id)

        # If we have a current search query, re-run the search to update the table
        # Otherwise, just reload all members
        if self._requested_search:
            logger.info(f"Re-running search with query: {self._requested_search}")
            QTimer.singleShot(100, self._perform_search)
        else:
            logger.info("Reloading all members")
            QTimer.singleShot(100, lambda: self.controller.load_members())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.member_card.is_editing():
            logger.info("MembersTab fallback ESC cancel triggered for member_id=%s", self._current_member_id)
            self.member_card.cancel_edit()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_status_label(self, state: MemberListState) -> None:
        visible_rows = len(state.members)
        total = state.total or visible_rows
        if visible_rows < total:
            self.status_label.setText(f"{visible_rows} de {total} socios")
        else:
            self.status_label.setText(f"{total} socios")

    def _update_action_buttons(self) -> None:
        has_selection = self._current_member_id is not None
        controls_locked = self._loading or self._delete_in_progress or self._basic_update_in_progress
        can_edit = has_selection and not controls_locked
        self.member_card.set_actions_enabled(can_edit, can_edit)
        self.renew_button.setEnabled(has_selection and not controls_locked and not self.member_card.is_editing())

    def _show_member_card(self) -> None:
        if self._card_visible:
            return

        self.side_card_container.setVisible(True)
        self.card_animation.stop()
        self.opacity_animation.stop()
        self.card_animation.setStartValue(self.side_card_container.maximumWidth())
        self.card_animation.setEndValue(self._card_width)
        self.opacity_animation.setStartValue(self.side_card_opacity.opacity())
        self.opacity_animation.setEndValue(1.0)
        self._card_animation_group.start()
        self._card_visible = True

    def _hide_member_card(self) -> None:
        if not self._card_visible:
            return

        self.card_animation.stop()
        self.opacity_animation.stop()
        self.card_animation.setStartValue(self.side_card_container.maximumWidth())
        self.card_animation.setEndValue(0)
        self.opacity_animation.setStartValue(self.side_card_opacity.opacity())
        self.opacity_animation.setEndValue(0.0)
        self._card_animation_group.start()
        QTimer.singleShot(280, lambda: self.side_card_container.setVisible(False))
        self._card_visible = False

    # ------------------------------------------------------------------
    # Click-away global para to close panel
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        # Sólo actuamos con panel visible
        if event.type() == QEvent.Type.MouseButtonPress and self._card_visible:
            # Nos interesan los eventos que ocurren dentro de este tab
            if isinstance(obj, QWidget) and self.isAncestorOf(obj):
                # Punto global del click (Qt6 -> QPointF, Qt5 -> QPoint)
                if hasattr(event, 'globalPosition'):
                    global_pt = event.globalPosition().toPoint()  # Llama al método y convierte a QPoint
                else:
                    global_pt = event.globalPos()  # Fallback para Qt5

                def global_rect(w: QWidget) -> QRect:
                    r = w.rect()
                    tl = w.mapToGlobal(r.topLeft())
                    br = w.mapToGlobal(r.bottomRight())
                    return QRect(tl, br)

                in_card = global_rect(self.side_card_frame).contains(global_pt)
                in_table = global_rect(self.member_table.viewport()).contains(global_pt)

                # Si estamos editando y el click cae fuera de la tarjeta,
                # cancelar edición de forma explícita para evitar estados bloqueados.
                if self.member_card.is_editing() and not in_card:
                    logger.info(
                        "Click-away detected while editing; cancelling edit for member_id=%s",
                        self._current_member_id,
                    )
                    self.member_card.cancel_edit()
                    return False

                # Clic fuera de la tabla y fuera del panel -> cerrar
                if not in_card and not in_table:
                    self.member_table.clearSelection()
                    self._hide_member_card()
                    return False  # dejamos que otros manejen el evento

        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Limpia el event filter al cerrar el widget."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)
