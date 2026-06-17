"""Subscriptions tab view."""

import time
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QLabel,
    QHeaderView, QSizePolicy, QComboBox,
    QFrame, QGraphicsOpacityEffect, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer, QEasingCurve, QParallelAnimationGroup, QPropertyAnimation
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen, QBrush, QIcon, QPalette
from ...core import container

from ...core import get_logger

from ...threads.authenticated_operations import start_authenticated_operation
from ...utils.dialog_helpers import show_error, show_info
from ..dialogs.new_subscription_dialog import NewSubscriptionDialog
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)

def _status_color(estado: str) -> QColor:
    """Determina el color basado en el estado."""
    estado_clean = (estado or '').strip().lower()

    if 'activo' in estado_clean or 'active' in estado_clean:
        return QColor(76, 175, 80)  # Verde
    elif 'vencido' in estado_clean or 'expired' in estado_clean:
        return QColor(244, 67, 54)  # Rojo
    elif 'vence pronto' in estado_clean or 'pendiente' in estado_clean or 'pending' in estado_clean:
        return QColor(255, 193, 7)  # Amarillo
    elif 'cancelado' in estado_clean or 'canceled' in estado_clean:
        return QColor(158, 158, 158)  # Gris
    else:
        return QColor(158, 158, 158)  # Gris


def create_status_icon(estado: str, size: int = 14) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = _status_color(estado)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.darker(130), 1))
    diameter = size - 2
    painter.drawEllipse(1, 1, diameter, diameter)
    painter.end()

    return QIcon(pixmap)


class SubscriptionsTab(QWidget):
    """Widget used to list and search membership subscriptions."""

    search_requested = Signal(str)
    subscription_selected = Signal(int)
    new_subscription_requested = Signal()
    renew_subscription_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        logger.info("Initializing SubscriptionsTab")

        try:
            self.subscriptions_service = container.get('subscriptions_service')
            self.members_service = container.get('members_service')
            self.standing_bookings_service = container.get('standing_bookings_service')
            logger.info("Services obtained from container")
        except Exception as e:
            logger.error(f"Failed to get services: {e}")
            raise

        self.current_subscriptions: List[Any] = []  # List of MembershipSubscription objects
        self.total_subscriptions: int = 0
        self.loading: bool = False
        self.page_size: int = 100
        self.current_search: Optional[str] = None
        self.current_status_filter: Optional[str] = None
        self.requested_search: Optional[str] = None
        self.requested_status_filter: Optional[str] = None

        # Contact card state
        self._card_width = 320
        self._card_animation_duration = 280
        self._card_visible = False
        self._current_card_animation: Optional[QParallelAnimationGroup] = None
        self._active_card_subscription: Optional[Any] = None
        self._edit_mode = False
        self._card_edit_snapshot: Optional[Dict[str, str]] = None
        self._card_save_in_progress = False
        self._card_save_started_at: Optional[float] = None
        self._card_save_context: Optional[Dict[str, Any]] = None
        self._card_save_operation: Optional[Any] = None

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.perform_search)

        logger.info("Setting up UI")
        self.setup_ui()

        # Install event filter to handle clicks outside the card
        self.installEventFilter(self)
        self.table.installEventFilter(self)
        self.side_card_container.installEventFilter(self)

        logger.info("Loading initial subscriptions")
        self.load_subscriptions()

        # Install event filter to handle clicks outside the card
        self.installEventFilter(self)

    def setup_ui(self) -> None:
        """Builds the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        toolbar_layout = QHBoxLayout()

        search_label = QLabel("Buscar:")
        toolbar_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nombre, telefono o email...")
        self.search_input.textChanged.connect(self.on_search)
        toolbar_layout.addWidget(self.search_input)

        # Status filter
        status_label = QLabel("Estado:")
        toolbar_layout.addWidget(status_label)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["Todos", "Activo", "Vencido", "Cancelado", "Pendiente"])
        self.status_filter.currentTextChanged.connect(self.on_status_filter_changed)
        toolbar_layout.addWidget(self.status_filter)

        toolbar_layout.addStretch()

        self.new_button = QPushButton("+ Nueva Suscripción")
        self.new_button.setObjectName("primaryButton")
        self.new_button.clicked.connect(self.on_new_subscription_clicked)
        toolbar_layout.addWidget(self.new_button)

        self.renew_button = QPushButton("Renovar Suscripción")
        self.renew_button.setObjectName("actionButton")
        self.renew_button.clicked.connect(self.on_renew_clicked)
        self.renew_button.setEnabled(False)
        toolbar_layout.addWidget(self.renew_button)

        layout.addLayout(toolbar_layout)

        # Content area with table and side card
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Nombre", "Teléfono", "Email", "Plan", "Estado", "Vencimiento"
        ])

        # Configuración de comportamiento
        configure_table_widget(self.table)
        self.table.setSortingEnabled(True)

        # Configuración de headers
        self.table.horizontalHeader().setStretchLastSection(False)

        # Configurar anchos específicos por columna
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Nombre - se expande
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Telefono - fijo
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Email - fijo
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Plan - fijo
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Estado - fijo
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Vencimiento - fijo

        # Establecer anchos específicos
        self.table.setColumnWidth(1, 120)  # Telefono
        self.table.setColumnWidth(2, 200)  # Email
        self.table.setColumnWidth(3, 150)  # Plan
        self.table.setColumnWidth(4, 120)  # Estado
        self.table.setColumnWidth(5, 120)  # Vencimiento

        # Configuración de scroll
        # Política de tamaño para la tabla
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Configurar señales
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellDoubleClicked.connect(self.on_double_click)

        # Asegurar que la tabla esté interactiva
        self.table.setEnabled(True)
        content_layout.addWidget(self.table, 1)

        # Side card container setup
        self.side_card_container = QWidget()
        self.side_card_container.setObjectName("subscriptionCardContainer")
        self.side_card_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.side_card_container.setMinimumWidth(0)
        self.side_card_container.setMaximumWidth(0)

        side_card_layout = QVBoxLayout(self.side_card_container)
        side_card_layout.setContentsMargins(0, 0, 0, 0)
        side_card_layout.setSpacing(0)

        self.side_card_frame = QFrame()
        self.side_card_frame.setObjectName("subscriptionCardFrame")
        self.side_card_frame.setFrameShape(QFrame.Shape.StyledPanel)

        # Use system colors instead of hardcoded values
        palette = QApplication.palette()
        background_color = palette.color(QPalette.ColorRole.Base).name()
        border_color = palette.color(QPalette.ColorRole.Mid).name()

        self.side_card_frame.setStyleSheet(f"#subscriptionCardFrame {{background-color: {background_color}; border: 1px solid {border_color}; border-radius: 8px;}}")
        self.side_card_frame.setFixedWidth(self._card_width)

        side_card_layout.addWidget(self.side_card_frame)

        card_layout = QVBoxLayout(self.side_card_frame)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        self.card_title_label = QLabel("Información de la suscripción")
        self.card_title_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        header_layout.addWidget(self.card_title_label)
        header_layout.addStretch()

        self.card_close_button = QPushButton("Cerrar")
        self.card_close_button.setFlat(True)
        self.card_close_button.clicked.connect(self._hide_subscription_contact_card)
        header_layout.addWidget(self.card_close_button)

        card_layout.addLayout(header_layout)

        self.card_name_input = QLineEdit()
        self.card_name_input.setPlaceholderText("Nombre completo")
        self.card_name_input.setReadOnly(True)
        card_layout.addWidget(self.card_name_input)

        self.card_phone_input = QLineEdit()
        self.card_phone_input.setPlaceholderText("Teléfono")
        self.card_phone_input.setReadOnly(True)
        card_layout.addWidget(self.card_phone_input)

        self.card_email_input = QLineEdit()
        self.card_email_input.setPlaceholderText("Email")
        self.card_email_input.setReadOnly(True)
        card_layout.addWidget(self.card_email_input)

        self.card_plan_label = QLabel("Plan: Sin plan")
        self.card_plan_label.setStyleSheet("color: #555555;")
        card_layout.addWidget(self.card_plan_label)

        self.card_status_label = QLabel("Estado: Sin datos")
        self.card_status_label.setStyleSheet("color: #555555;")
        card_layout.addWidget(self.card_status_label)

        self.card_dates_label = QLabel("Período: Sin datos")
        self.card_dates_label.setStyleSheet("color: #555555;")
        card_layout.addWidget(self.card_dates_label)

        card_layout.addStretch()

        self.card_edit_button = QPushButton("Editar contacto")
        self.card_edit_button.clicked.connect(self._toggle_edit_mode)
        self.card_edit_button.setEnabled(False)
        card_layout.addWidget(self.card_edit_button)

        self.card_save_button = QPushButton("Guardar cambios")
        self.card_save_button.clicked.connect(self._save_subscription_edits)
        self.card_save_button.setEnabled(False)
        self.card_save_button.setVisible(False)
        card_layout.addWidget(self.card_save_button)

        self.card_cancel_button = QPushButton("Cancelar")
        self.card_cancel_button.clicked.connect(self._cancel_edit_mode)
        self.card_cancel_button.setEnabled(False)
        self.card_cancel_button.setVisible(False)
        card_layout.addWidget(self.card_cancel_button)

        self.side_card_opacity_effect = QGraphicsOpacityEffect(self.side_card_frame)
        self.side_card_frame.setGraphicsEffect(self.side_card_opacity_effect)
        self.side_card_opacity_effect.setOpacity(0.0)

        self.side_card_container.setVisible(False)
        content_layout.addWidget(self.side_card_container)

        layout.addLayout(content_layout, 1)

        status_layout = QHBoxLayout()
        self.status_label = QLabel("0 suscripciones")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        layout.addLayout(status_layout)

    def load_subscriptions(self, search: Optional[str] = None, status: Optional[str] = None) -> None:
        """Requests the subscriptions list from the backend."""
        logger.info(f"load_subscriptions called with search: {search}, status: {status}")

        if self.loading:
            logger.info("Already loading, queueing search request")
            self.requested_search = search
            self.requested_status_filter = status
            return

        self.requested_search = search
        self.requested_status_filter = status
        self._set_loading(True)

        self.status_label.setText("Cargando suscripciones...")

        logger.info("Creating DataLoader worker for subscriptions")

        # Convert status display to API format
        api_status = None
        if status and status != "Todos":
            status_map = {
                "Activo": "active",
                "Vencido": "expired",
                "Cancelado": "canceled",
                "Pendiente": "pending"
            }
            api_status = status_map.get(status)

        # Use AuthenticatedOperation to maintain authentication context
        def _on_operation_complete():
            self._set_loading(False)

        operation = start_authenticated_operation(
            service=self.subscriptions_service,
            method_name='get_subscriptions',
            parent=self,
            on_success=self.on_subscriptions_loaded,
            on_error=self.on_subscriptions_error,
            on_finished=_on_operation_complete,
            limit=self.page_size,
            offset=0,
            search=search,
            status=api_status,
        )

        logger.info("Executing authenticated operation for subscriptions")

    def on_subscriptions_loaded(self, data: Optional[List[Any]]) -> None:
        """Handles successful data retrieval."""
        logger.info(f"on_subscriptions_loaded called with data type: {type(data)}")

        self.current_subscriptions = data or []
        self.total_subscriptions = len(self.current_subscriptions)
        self.current_search = self.requested_search
        self.current_status_filter = self.requested_status_filter

        logger.info(f"Subscriptions data loaded: {len(self.current_subscriptions)} records, total: {self.total_subscriptions}")

        self.populate_table()

        logger.info("populate_table completed")

        # Asegurar que se actualice el estado de carga
        self._set_loading(False)

    def on_subscriptions_error(self, error: str) -> None:
        """Handles data loading errors."""
        logger.error("Error loading subscriptions: %s", error)
        self.status_label.setText("Error al cargar suscripciones")

    def populate_table(self) -> None:
        """Fills the table with the current subscriptions list."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.current_subscriptions))
        if not self.current_subscriptions:
            self.table.setSortingEnabled(True)
            self.update_status()
            return

        for row, subscription in enumerate(self.current_subscriptions):
            subscription_id = subscription.id if hasattr(subscription, 'id') else ''

            # Get person data
            if hasattr(subscription, 'person') and subscription.person:
                nombre = subscription.person.full_name or 'Sin nombre'
                telefono = subscription.person.phone_number or 'N/A'
                email = subscription.person.email or 'N/A'
            else:
                nombre = 'Sin nombre'
                telefono = 'N/A'
                email = 'N/A'

            # Get plan data
            if hasattr(subscription, 'plan') and subscription.plan:
                plan_name = subscription.plan.name or 'Sin plan'
            else:
                plan_name = 'Sin plan'

            # Get status
            estado = subscription.status or 'Sin datos'
            estado_display = subscription.status_display() if hasattr(subscription, 'status_display') else estado

            # Get expiry info
            vencimiento = ''
            if hasattr(subscription, 'end_at') and subscription.end_at:
                vencimiento = subscription.end_at.strftime("%d/%m/%Y") if subscription.end_at else ''

            values = [nombre, telefono, email, plan_name, estado_display, vencimiento]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, subscription_id)
                    item.setData(Qt.ItemDataRole.UserRole + 2, subscription)

                if col == 4:  # Estado column
                    item.setData(Qt.ItemDataRole.UserRole + 1, estado)
                    icon = create_status_icon(estado)
                    item.setIcon(icon)
                    item.setText(estado_display)

                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.update_status()

    def on_search(self, text: str) -> None:
        """Schedules a remote search with debounce."""
        self.search_requested.emit(text)
        clean = text.strip() or None
        self.requested_search = clean
        self.search_timer.start()

    def on_status_filter_changed(self, status: str) -> None:
        """Handles status filter changes."""
        self.requested_status_filter = status if status != "Todos" else None
        self.search_timer.start()

    def perform_search(self) -> None:
        """Executes the pending search request."""
        self.load_subscriptions(self.requested_search, self.requested_status_filter)

    def _subscription_id_from_row(self, row: int) -> Optional[int]:
        """Returns the subscription id stored in the first column of a row."""
        if row < 0:
            return None

        item = self.table.item(row, 0)
        if item is None:
            return None

        data = item.data(Qt.ItemDataRole.UserRole)
        if data in (None, ''):
            return None

        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def _subscription_from_row(self, row: int) -> Optional[Any]:
        """Returns the subscription object stored in the first column of a row."""
        if row < 0:
            return None

        item = self.table.item(row, 0)
        if item is None:
            return None

        subscription = item.data(Qt.ItemDataRole.UserRole + 2)
        return subscription

    def on_selection_changed(self) -> None:
        """Updates selection dependent actions."""
        selected = len(self.table.selectedItems()) > 0
        self.renew_button.setEnabled(selected)

        if selected:
            row = self.table.currentRow()
            subscription_id = self._subscription_id_from_row(row)

            if subscription_id is not None:
                self.subscription_selected.emit(subscription_id)
            else:
                logger.debug("Selected row without valid subscription id")

    def on_double_click(self, row: int, col: int) -> None:
        """Handles double click on a row."""
        subscription = self._subscription_from_row(row)
        subscription_id = self._subscription_id_from_row(row)

        if subscription is None:
            logger.debug("Invalid subscription data on double click")
            self._hide_subscription_contact_card()
            return

        if subscription_id is not None:
            logger.info("Double click on subscription %s", subscription_id)
        else:
            logger.info("Double click on subscription without id")

        self._show_subscription_contact_card(subscription)

    def on_renew_clicked(self) -> None:
        """Emits renew signal for the selected subscription."""
        subscription_id = self._subscription_id_from_row(self.table.currentRow())
        if subscription_id is None:
            logger.debug("Invalid subscription id on renew request")
            return

        self.renew_subscription_requested.emit(subscription_id)

    def on_new_subscription_clicked(self) -> None:
        """Opens the new subscription dialog."""
        try:
            dialog = NewSubscriptionDialog(self.members_service, self.standing_bookings_service, self)
            if dialog.exec() == NewSubscriptionDialog.DialogCode.Accepted:
                # Refresh the table after successful enrollment
                self.refresh_data()
                logger.info("New subscription created, refreshing data")
        except Exception as e:
            logger.error(f"Error opening new subscription dialog: {e}")

    def update_status(self) -> None:
        """Refreshes the status bar label."""
        visible_rows = self.table.rowCount()
        total = self.total_subscriptions or visible_rows

        if visible_rows < total:
            self.status_label.setText(f"{visible_rows} de {total} suscripciones")
        else:
            self.status_label.setText(f"{total} suscripciones")

    def add_subscription(self, subscription_data: Dict[str, Any]) -> None:
        """Adds a new subscription to the current table."""
        self.current_subscriptions.append(subscription_data)
        self.total_subscriptions += 1
        self.populate_table()

    def refresh_data(self) -> None:
        """Triggers a manual refresh from external callers."""
        self.load_subscriptions(self.current_search, self.current_status_filter)

    def _set_loading(self, is_loading: bool) -> None:
        """Updates loading flag and handles queued searches."""
        self.loading = is_loading

        # Solo deshabilitar los botones, no la tabla
        self.new_button.setDisabled(is_loading)

        if is_loading:
            self.renew_button.setDisabled(True)
            self.status_label.setText("Cargando suscripciones...")
        else:
            self.on_selection_changed()
            # Asegurar que la tabla esté habilitada
            self.table.setEnabled(True)
            self.update_status()

        # Manejar búsquedas pendientes después de verificar que no estamos cargando
        if not is_loading and (self.requested_search != self.current_search or
                               self.requested_status_filter != self.current_status_filter):
            # Usar un QTimer para evitar recursión inmediata
            QTimer.singleShot(100, lambda: self.load_subscriptions(self.requested_search, self.requested_status_filter))

    def _capture_card_snapshot(self) -> Dict[str, str]:
        """Captures card editable fields so failed saves can be reverted."""
        return {
            "name": self.card_name_input.text().strip(),
            "phone": self.card_phone_input.text().strip(),
            "email": self.card_email_input.text().strip(),
        }

    def _restore_card_snapshot(self) -> None:
        """Restores card fields from the latest snapshot."""
        if not self._card_edit_snapshot:
            return
        self.card_name_input.setText(self._card_edit_snapshot.get("name", ""))
        self.card_phone_input.setText(self._card_edit_snapshot.get("phone", ""))
        self.card_email_input.setText(self._card_edit_snapshot.get("email", ""))

    def _set_card_saving_state(self, saving: bool) -> None:
        """Toggles only contact-card edit controls while a save is in progress."""
        self._card_save_in_progress = saving
        self._card_save_started_at = time.perf_counter() if saving else None

        self.card_name_input.setEnabled(not saving)
        self.card_phone_input.setEnabled(not saving)
        self.card_email_input.setEnabled(not saving)
        self.card_close_button.setEnabled(not saving)
        self.card_edit_button.setEnabled(
            (self._active_card_subscription is not None) and (not saving) and (not self._edit_mode)
        )
        self.card_cancel_button.setEnabled(self._edit_mode and (not saving))
        self.card_save_button.setEnabled(self._edit_mode and (not saving))
        self.card_save_button.setText("Guardando..." if saving else "Guardar cambios")

    def _member_id_from_subscription(self, subscription: Any) -> Optional[int]:
        """Resolve member id from subscription.person.id with safe fallbacks."""
        person = getattr(subscription, "person", None)
        candidates = [
            getattr(person, "id", None),
            getattr(subscription, "person_id", None),
            getattr(subscription, "personId", None),
        ]
        for candidate in candidates:
            if candidate in (None, ""):
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    def _subscription_id_from_subscription(self, subscription: Any) -> Optional[int]:
        value = getattr(subscription, "id", None)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _apply_subscription_contact(self, subscription: Any, result_payload: Dict[str, Any], fallback_payload: Dict[str, str]) -> None:
        """Apply backend-confirmed contact data to local subscription object."""
        if not hasattr(subscription, "person") or subscription.person is None:
            return

        member = result_payload.get("member")
        person = subscription.person
        if member is not None:
            if hasattr(person, "full_name"):
                person.full_name = getattr(member, "full_name", None) or fallback_payload.get("name", "")
            if hasattr(person, "phone_number"):
                person.phone_number = getattr(member, "phone_number", None) or fallback_payload.get("phone", "")
            if hasattr(person, "email"):
                person.email = getattr(member, "email", None) or fallback_payload.get("email", "")
            return

        if hasattr(person, "full_name"):
            person.full_name = fallback_payload.get("name", "")
        if hasattr(person, "phone_number"):
            person.phone_number = fallback_payload.get("phone", "")
        if hasattr(person, "email"):
            person.email = fallback_payload.get("email", "")

    def _update_subscription_row_contact(self, subscription: Any) -> None:
        """Updates only the selected subscription row contact cells (no full repaints)."""
        subscription_id = self._subscription_id_from_subscription(subscription)
        if subscription_id is None:
            return

        person = getattr(subscription, "person", None)
        name = getattr(person, "full_name", None) or "Sin nombre"
        phone = getattr(person, "phone_number", None) or "N/A"
        email = getattr(person, "email", None) or "N/A"

        for row in range(self.table.rowCount()):
            if self._subscription_id_from_row(row) != subscription_id:
                continue
            name_item = self.table.item(row, 0)
            phone_item = self.table.item(row, 1)
            email_item = self.table.item(row, 2)
            if name_item:
                name_item.setText(str(name))
            if phone_item:
                phone_item.setText(str(phone))
            if email_item:
                email_item.setText(str(email))
            break

    def _build_member_save_error_message(self, result: Any) -> str:
        if isinstance(result, dict):
            message = str(result.get("message") or "").strip()
            cause = str(result.get("error_cause") or "").strip()
            if message:
                return message
            if cause:
                return f"No se guardaron los cambios. Causa: {cause}."
        return "No se guardaron los cambios. Causa: Error al actualizar socio."

    def _on_save_subscription_edits_success(self, result: Any) -> None:
        """Handles update_member completion with explicit success semantics."""
        started_at = self._card_save_started_at
        self._set_card_saving_state(False)
        context = self._card_save_context or {}
        subscription = context.get("subscription")
        member_id = context.get("member_id")
        subscription_id = context.get("subscription_id")
        payload = context.get("payload") or {}
        duration_ms = ((time.perf_counter() - started_at) * 1000) if started_at else 0.0

        success = False
        if isinstance(result, dict) and isinstance(result.get("success"), bool):
            success = bool(result.get("success"))

        if not success or subscription is None:
            message = self._build_member_save_error_message(result)
            error_code = ""
            if isinstance(result, dict):
                error_code = str(result.get("error_code") or "").strip().upper()
            logger.warning(
                "subscription_contact_save member_id=%s subscription_id=%s success=%s error_code=%s duration_ms=%.2f",
                member_id,
                subscription_id,
                False,
                error_code or "UPDATE_FAILED",
                duration_ms,
            )
            self._restore_card_snapshot()
            show_error(self, message, title="Editar socio")
            return

        self._apply_subscription_contact(subscription, result, payload)
        self._update_subscription_row_contact(subscription)
        self._card_edit_snapshot = self._capture_card_snapshot()
        logger.info(
            "subscription_contact_save member_id=%s subscription_id=%s success=%s duration_ms=%.2f",
            member_id,
            subscription_id,
            True,
            duration_ms,
        )
        self._cancel_edit_mode()
        success_message = str(result.get("message") or "").strip() if isinstance(result, dict) else ""
        if success_message:
            show_info(self, success_message, title="Editar socio")

    def _on_save_subscription_edits_error(self, error: str) -> None:
        started_at = self._card_save_started_at
        self._set_card_saving_state(False)
        context = self._card_save_context or {}
        member_id = context.get("member_id")
        subscription_id = context.get("subscription_id")
        duration_ms = ((time.perf_counter() - started_at) * 1000) if started_at else 0.0
        logger.error(
            "subscription_contact_save member_id=%s subscription_id=%s success=%s error_code=%s duration_ms=%.2f error=%s",
            member_id,
            subscription_id,
            False,
            "NETWORK_ERROR",
            duration_ms,
            error,
        )
        self._restore_card_snapshot()
        show_error(
            self,
            "No se guardaron los cambios. Causa: Error de comunicacion con el servidor.",
            detailed_text=error or "",
            title="Editar socio",
        )

    def _on_save_subscription_edits_finished(self) -> None:
        if self._card_save_in_progress:
            self._set_card_saving_state(False)
        self._card_save_operation = None
        self._card_save_context = None

    def _show_subscription_contact_card(self, subscription: Any) -> None:
        """Populates and reveals the side contact card for the selected subscription."""
        self._active_card_subscription = subscription


        # Get person data
        if hasattr(subscription, 'person') and subscription.person:
            nombre = subscription.person.full_name or 'Sin nombre'
            telefono = subscription.person.phone_number or 'N/A'
            email = subscription.person.email or 'N/A'
        else:
            nombre = 'Sin nombre'
            telefono = 'N/A'
            email = 'N/A'

        # Set person fields
        self.card_name_input.setText(nombre)
        self.card_phone_input.setText(telefono)
        self.card_email_input.setText(email)

        # Update title
        subscription_id = subscription.id if hasattr(subscription, 'id') else None
        if subscription_id:
            self.card_title_label.setText(f"Suscripción #{subscription_id}")
        else:
            self.card_title_label.setText("Información de la suscripción")

        # Get plan data
        if hasattr(subscription, 'plan') and subscription.plan:
            plan_name = subscription.plan.name or 'Sin plan'
            self.card_plan_label.setText(f"Plan: {plan_name}")
        else:
            self.card_plan_label.setText("Plan: Sin plan")

        # Get status
        estado = subscription.status or 'Sin datos'
        estado_display = subscription.status_display() if hasattr(subscription, 'status_display') else estado
        self.card_status_label.setText(f"Estado: {estado_display}")

        # Get dates
        if hasattr(subscription, 'start_at') and hasattr(subscription, 'end_at'):
            start_date = subscription.start_at.strftime("%d/%m/%Y") if subscription.start_at else 'N/A'
            end_date = subscription.end_at.strftime("%d/%m/%Y") if subscription.end_at else 'N/A'
            self.card_dates_label.setText(f"Período: {start_date} - {end_date}")
        else:
            self.card_dates_label.setText("Período: Sin datos")

        self._set_card_saving_state(self._card_save_in_progress)

        if not self._card_visible:
            self._animate_subscription_card(True)
        else:
            self.side_card_container.setVisible(True)
            self.side_card_container.setMinimumWidth(self._card_width)
            self.side_card_container.setMaximumWidth(self._card_width)
            self.side_card_opacity_effect.setOpacity(1.0)

    def _hide_subscription_contact_card(self) -> None:
        """Hides the side contact card with animation."""
        if self._card_save_in_progress:
            logger.debug("Hide requested while contact save is in progress")
            return

        if not self._card_visible and self.side_card_container.maximumWidth() == 0:
            self._active_card_subscription = None
            self.card_edit_button.setEnabled(False)
            self._reset_card_fields()
            self.side_card_container.setMinimumWidth(0)
            self.side_card_container.setVisible(False)
            return

        self._active_card_subscription = None
        self.card_edit_button.setEnabled(False)
        self._reset_card_fields()
        self.side_card_container.setMinimumWidth(0)
        self._animate_subscription_card(False)

    def _reset_card_fields(self) -> None:
        """Resets all card fields to default values."""
        self.card_name_input.clear()
        self.card_phone_input.clear()
        self.card_email_input.clear()
        self.card_plan_label.setText("Plan: Sin plan")
        self.card_status_label.setText("Estado: Sin datos")
        self.card_dates_label.setText("Período: Sin datos")
        self.card_title_label.setText("Información de la suscripción")

        self._card_edit_snapshot = None

        # Reset edit mode
        if self._edit_mode:
            self._cancel_edit_mode()

    def _animate_subscription_card(self, show: bool) -> None:
        """Animates the side contact card into or out of view."""
        if self._current_card_animation is not None:
            self._current_card_animation.stop()
            self._current_card_animation.deleteLater()
            self._current_card_animation = None

        target_width = self._card_width if show else 0
        start_width = self.side_card_container.maximumWidth()

        if show and not self.side_card_container.isVisible():
            self.side_card_container.setVisible(True)
            if start_width <= 0:
                start_width = 0
                self.side_card_container.setMinimumWidth(0)
                self.side_card_container.setMaximumWidth(0)

        if not show and not self._card_visible and start_width <= 0:
            self.side_card_container.setMinimumWidth(0)
            self.side_card_container.setVisible(False)
            self.side_card_opacity_effect.setOpacity(0.0)
            return

        slide_max = QPropertyAnimation(self.side_card_container, b"maximumWidth", self)
        slide_max.setDuration(self._card_animation_duration)
        slide_max.setStartValue(start_width)
        slide_max.setEndValue(target_width)
        slide_max.setEasingCurve(QEasingCurve.Type.InOutCubic)

        slide_min = QPropertyAnimation(self.side_card_container, b"minimumWidth", self)
        slide_min.setDuration(self._card_animation_duration)
        slide_min.setStartValue(start_width)
        slide_min.setEndValue(target_width)
        slide_min.setEasingCurve(QEasingCurve.Type.InOutCubic)

        opacity_start = self.side_card_opacity_effect.opacity()
        if show and start_width <= 0:
            opacity_start = 0.0
            self.side_card_opacity_effect.setOpacity(0.0)

        opacity = QPropertyAnimation(self.side_card_opacity_effect, b"opacity", self)
        opacity.setDuration(self._card_animation_duration)
        opacity.setStartValue(opacity_start)
        opacity.setEndValue(1.0 if show else 0.0)
        opacity.setEasingCurve(QEasingCurve.Type.InOutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(slide_max)
        group.addAnimation(slide_min)
        group.addAnimation(opacity)

        def finalize():
            if show:
                self.side_card_container.setMinimumWidth(self._card_width)
                self.side_card_container.setMaximumWidth(self._card_width)
                self.side_card_opacity_effect.setOpacity(1.0)
                self.side_card_container.setVisible(True)
                self._card_visible = True
            else:
                self.side_card_container.setMinimumWidth(0)
                self.side_card_container.setMaximumWidth(0)
                self.side_card_opacity_effect.setOpacity(0.0)
                self.side_card_container.setVisible(False)
                self._card_visible = False
            self._current_card_animation = None
            group.deleteLater()

        group.finished.connect(finalize)
        self._current_card_animation = group
        group.start()

    def _toggle_edit_mode(self) -> None:
        """Toggles between view and edit mode for contact fields."""
        if self._card_save_in_progress:
            logger.debug("Edit toggle ignored while contact save is in progress")
            return

        if not self._edit_mode:
            self._edit_mode = True
            self._card_edit_snapshot = self._capture_card_snapshot()
            self.card_name_input.setReadOnly(False)
            self.card_phone_input.setReadOnly(False)
            self.card_email_input.setReadOnly(False)

            self.card_edit_button.setVisible(False)
            self.card_save_button.setVisible(True)
            self.card_cancel_button.setVisible(True)
            self._set_card_saving_state(False)
            return

        self._cancel_edit_mode()

    def _cancel_edit_mode(self) -> None:
        """Cancels edit mode and reverts to view mode."""
        if self._card_save_in_progress:
            logger.debug("Cancel edit ignored while contact save is in progress")
            return

        if self._edit_mode:
            self._edit_mode = False
            self.card_name_input.setReadOnly(True)
            self.card_phone_input.setReadOnly(True)
            self.card_email_input.setReadOnly(True)

            self.card_edit_button.setVisible(True)
            self.card_save_button.setVisible(False)
            self.card_cancel_button.setVisible(False)
            self._set_card_saving_state(False)

            if self._active_card_subscription:
                self._show_subscription_contact_card(self._active_card_subscription)
            self._card_edit_snapshot = None

    def _save_subscription_edits(self) -> None:
        """Persist contact edits through backend and avoid optimistic false positives."""
        if self._card_save_in_progress:
            logger.debug("Save ignored because another contact save is already running")
            return

        subscription = self._active_card_subscription
        if subscription is None:
            logger.debug("Save requested without an active subscription")
            return

        if not hasattr(subscription, 'person') or subscription.person is None:
            logger.debug("Save requested but subscription has no person data")
            show_error(self, "No se guardaron los cambios. Causa: Socio no encontrado.", title="Editar socio")
            return

        member_id = self._member_id_from_subscription(subscription)
        subscription_id = self._subscription_id_from_subscription(subscription)
        if member_id is None:
            logger.warning(
                "Contact save requested without valid member id for subscription_id=%s",
                subscription_id,
            )
            show_error(self, "No se guardaron los cambios. Causa: Socio no encontrado.", title="Editar socio")
            return

        nombre = self.card_name_input.text().strip()
        telefono = self.card_phone_input.text().strip()
        email = self.card_email_input.text().strip()

        person = subscription.person
        current_name = (getattr(person, "full_name", None) or "").strip()
        current_phone = (getattr(person, "phone_number", None) or "").strip()
        current_email = (getattr(person, "email", None) or "").strip()

        payload = {
            "name": nombre,
            "phone": telefono,
            "email": email,
        }
        changed_fields = [
            field
            for field, values in {
                "name": (nombre, current_name),
                "phone": (telefono, current_phone),
                "email": (email, current_email),
            }.items()
            if values[0] != values[1]
        ]

        if not changed_fields:
            logger.info(
                "subscription_contact_save skipped member_id=%s subscription_id=%s reason=no_changes",
                member_id,
                subscription_id,
            )
            self._cancel_edit_mode()
            return

        if not self._card_edit_snapshot:
            self._card_edit_snapshot = {
                "name": current_name,
                "phone": current_phone,
                "email": current_email,
            }

        self._card_save_context = {
            "member_id": member_id,
            "subscription_id": subscription_id,
            "subscription": subscription,
            "payload": payload,
        }

        logger.info(
            "subscription_contact_save requested member_id=%s subscription_id=%s changed_fields=%s",
            member_id,
            subscription_id,
            changed_fields,
        )
        if not callable(getattr(self.members_service, "update_member", None)):
            self._card_save_context = None
            show_error(self, "No se guardaron los cambios. Causa: Servicio no disponible.", title="Editar socio")
            return

        self._set_card_saving_state(True)
        try:
            self._card_save_operation = start_authenticated_operation(
                service=self.members_service,
                method_name="update_member",
                parent=self,
                on_success=self._on_save_subscription_edits_success,
                on_error=self._on_save_subscription_edits_error,
                on_finished=self._on_save_subscription_edits_finished,
                member_id=member_id,
                payload=payload,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_card_saving_state(False)
            self._card_save_context = None
            logger.error(
                "subscription_contact_save member_id=%s subscription_id=%s success=%s error_code=%s error=%s",
                member_id,
                subscription_id,
                False,
                "UPDATE_FAILED",
                exc,
            )
            self._restore_card_snapshot()
            show_error(self, "No se guardaron los cambios. Causa: Error al actualizar socio.", title="Editar socio")

    
