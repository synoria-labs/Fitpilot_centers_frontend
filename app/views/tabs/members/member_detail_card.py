"""Member detail card widget for the members tab."""

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal, QRegularExpression, QEvent
from ....core.config import Config
from ....core.logging import get_logger
from PySide6.QtGui import (
    QAction,
    QIcon,
    QRegularExpressionValidator,
    QPainter,
    QColor,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....viewmodels.members_state import BasicInfoPayload, MemberDetailState
from .avatar_widget import AvatarWidget
from ....utils.dialog_helpers import show_warning

logger = get_logger(__name__)


class MemberDetailCard(QWidget):
    """Displays member details and handles inline editing."""

    save_requested = Signal(int, object)  # member_id, BasicInfoPayload
    delete_requested = Signal(int)
    edit_mode_changed = Signal(bool)
    reschedule_requested = Signal(int)
    avatar_upload_requested = Signal(int, str)  # member_id, file_path
    avatar_delete_requested = Signal(int)  # member_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_state = MemberDetailState()
        self._editing = False
        self._loading = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._build_ui()
        self._setup_shortcuts()
        self._update_actions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_state(self, state: MemberDetailState) -> None:
        """Update the card with the provided member state."""
        was_editing = self._editing
        self._current_state = state
        if not state.member_id:
            self._editing = False
        self._populate_from_state()
        self._update_actions()
        if was_editing and not self._editing:
            logger.info("Member edit mode forced off by state reset")
            self.edit_mode_changed.emit(False)

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        was_editing = self._editing
        if loading and self._editing:
            self._editing = False
            self._populate_from_state()
        self._update_actions()
        if was_editing and not self._editing:
            logger.info("Member edit mode forced off due to loading transition")
            self.edit_mode_changed.emit(False)

    def set_actions_enabled(self, can_edit: bool, can_delete: bool) -> None:
        if self._loading:
            can_edit = False
            can_delete = False
        # Defensive: keep actions visible even if disabled to avoid "missing buttons" perception.
        self.edit_action.setVisible(True)
        self.delete_action.setVisible(True)
        self.edit_button.setVisible(True)
        self.delete_button.setVisible(True)
        self.edit_action.setEnabled(can_edit)
        self.edit_button.setEnabled(can_edit)
        self.delete_action.setEnabled(can_delete)
        self.delete_button.setEnabled(can_delete)

    def reset(self) -> None:
        """Clear content and exit edit mode."""
        was_editing = self._editing
        self._current_state = MemberDetailState()
        self._editing = False
        self._populate_from_state()
        self._update_actions()
        if was_editing:
            logger.info("Member edit mode forced off by card reset")
            self.edit_mode_changed.emit(False)

    def is_editing(self) -> bool:
        return self._editing

    def cancel_edit(self) -> None:
        """Public API to cancel inline editing from parent widgets."""
        if not self._editing:
            return
        self._cancel_edit()

    def save_if_valid(self) -> None:
        """Public API to trigger save action only when payload is valid."""
        if self._loading or not self._editing:
            return
        self._validate_inputs()
        if self.save_button.isEnabled():
            self._on_save_clicked()
        else:
            logger.info(
                "Save shortcut ignored due to invalid payload for member_id=%s",
                self._current_state.member_id,
            )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget(self.scroll_area)
        scroll_content.setMinimumWidth(0)
        scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header with avatar and title
        header_container = QWidget()
        header_container.setMinimumWidth(0)
        header_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        # Top row with title and action buttons
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.title_label = QLabel("Perfil del socio")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.edit_action = QAction(self)
        self.edit_action.setIcon(self._load_icon("edit-pencil.svg"))
        self.edit_action.setToolTip("Editar datos basicos")
        self.edit_action.triggered.connect(self._toggle_edit_mode)

        self.delete_action = QAction(self)
        self.delete_action.setIcon(self._load_icon("trash.svg"))
        self.delete_action.setToolTip("Eliminar socio")
        self.delete_action.triggered.connect(self._request_delete)

        self.edit_button = self._build_icon_button(self.edit_action)
        self.delete_button = self._build_icon_button(self.delete_action)

        title_row.addWidget(self.edit_button)
        title_row.addWidget(self.delete_button)
        header_layout.addLayout(title_row)

        # Avatar and name row
        avatar_row = QHBoxLayout()
        avatar_row.setContentsMargins(0, 0, 0, 0)
        avatar_row.setSpacing(12)

        # Avatar widget
        self.avatar_widget = AvatarWidget(size=80, editable=True, parent=self)
        self.avatar_widget.image_changed.connect(self._on_avatar_changed)
        self.avatar_widget.image_removed.connect(self._on_avatar_removed)
        avatar_row.addWidget(self.avatar_widget)
        avatar_row.addStretch()

        header_layout.addLayout(avatar_row)
        layout.addWidget(header_container)

        label_style = "font-size: 12px; color: #555555;"
        value_style = "font-size: 14px; font-weight: 500;"
        line_edit_style = (
            "QLineEdit {"
            " padding: 6px;"
            " border: 1px solid palette(mid);"
            " border-radius: 6px;"
            "}"
            "QLineEdit:focus { border-color: palette(highlight); }"
            "QLineEdit[invalid=\"true\"] { border-color: #d32f2f; }"
        )

        self.name_label = QLabel("Nombre completo")
        self.name_label.setStyleSheet(label_style)
        layout.addWidget(self.name_label)

        self.name_value = QLabel("-")
        self.name_value.setStyleSheet(value_style)
        self.name_value.setWordWrap(True)
        self.name_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.name_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.name_value.setMinimumWidth(0)
        layout.addWidget(self.name_value)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nombre completo")
        self.name_input.setStyleSheet(line_edit_style)
        self.name_input.setVisible(False)
        self.name_input.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.name_input)

        self.email_label = QLabel("Email")
        self.email_label.setStyleSheet(label_style)
        layout.addWidget(self.email_label)

        self.email_value = QLabel("-")
        self.email_value.setStyleSheet(value_style)
        self.email_value.setWordWrap(True)
        self.email_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.email_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.email_value.setMinimumWidth(0)
        layout.addWidget(self.email_value)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        self.email_input.setStyleSheet(line_edit_style)
        self.email_input.setVisible(False)
        self.email_input.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.email_input)

        self.phone_label = QLabel("Telefono")
        self.phone_label.setStyleSheet(label_style)
        layout.addWidget(self.phone_label)

        self.phone_value = QLabel("-")
        self.phone_value.setStyleSheet(value_style)
        layout.addWidget(self.phone_value)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Telefono (8-15 digitos)")
        self.phone_input.setStyleSheet(line_edit_style)
        self.phone_input.setVisible(False)
        self.phone_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^\+?\d{0,15}$"), self.phone_input)
        )
        self.phone_input.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.phone_input)

        self.plan_label = QLabel("Plan activo")
        self.plan_label.setStyleSheet(label_style)
        layout.addWidget(self.plan_label)

        self.plan_value = QLabel("-")
        self.plan_value.setStyleSheet(value_style)
        layout.addWidget(self.plan_value)

        self.status_label = QLabel("Estado")
        self.status_label.setStyleSheet(label_style)
        layout.addWidget(self.status_label)

        self.status_value = QLabel("-")
        self.status_value.setStyleSheet(value_style)
        layout.addWidget(self.status_value)

        self.schedule_label = QLabel("Horario fijo")
        self.schedule_label.setStyleSheet(label_style)
        layout.addWidget(self.schedule_label)

        self.schedule_value = QLabel("-")
        self.schedule_value.setStyleSheet(value_style)
        self.schedule_value.setWordWrap(True)
        self.schedule_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.schedule_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.schedule_value.setMinimumWidth(0)
        layout.addWidget(self.schedule_value)

        self.center_label = QLabel("Centro de entrenamiento")
        self.center_label.setStyleSheet(label_style)
        layout.addWidget(self.center_label)

        self.center_value = QLabel("-")
        self.center_value.setStyleSheet(value_style)
        self.center_value.setWordWrap(True)
        self.center_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.center_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.center_value.setMinimumWidth(0)
        layout.addWidget(self.center_value)

        self.change_schedule_button = QPushButton("Cambiar clase")
        self.change_schedule_button.setObjectName("actionButton")
        self.change_schedule_button.clicked.connect(self._on_reschedule_clicked)
        self.change_schedule_button.setEnabled(False)
        self.change_schedule_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.change_schedule_button)

        # Separator
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: palette(mid);")
        layout.addWidget(separator)

        # Dates section
        dates_label = QLabel("Fechas de Membresía")
        dates_label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        layout.addWidget(dates_label)

        self.member_since_label = QLabel("Miembro desde")
        self.member_since_label.setStyleSheet(label_style)
        layout.addWidget(self.member_since_label)

        self.member_since_value = QLabel("-")
        self.member_since_value.setStyleSheet(value_style)
        layout.addWidget(self.member_since_value)

        self.membership_start_label = QLabel("Inicio de membresía actual")
        self.membership_start_label.setStyleSheet(label_style)
        layout.addWidget(self.membership_start_label)

        self.membership_start_value = QLabel("-")
        self.membership_start_value.setStyleSheet(value_style)
        layout.addWidget(self.membership_start_value)

        self.remaining_days_label = QLabel("Días restantes")
        self.remaining_days_label.setStyleSheet(label_style)
        layout.addWidget(self.remaining_days_label)

        self.remaining_days_value = QLabel("-")
        self.remaining_days_value.setStyleSheet(value_style)
        layout.addWidget(self.remaining_days_value)

        self.scroll_area.setWidget(scroll_content)
        self.scroll_area.viewport().installEventFilter(self)
        root_layout.addWidget(self.scroll_area, 1)

        buttons_container = QWidget(self)
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch()

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("actionButton")
        self.cancel_button.clicked.connect(self._cancel_edit)
        buttons_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._on_save_clicked)
        self.save_button.setEnabled(False)
        buttons_layout.addWidget(self.save_button)

        buttons_container.setVisible(False)
        self.buttons_container = buttons_container
        root_layout.addWidget(buttons_container, 0)

    def _build_icon_button(self, action: QAction) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("memberCardIconButton")
        button.setDefaultAction(action)
        button.setFixedSize(30, 30)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        icon_size = QSize(16, 16)
        button.setIconSize(icon_size)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(False)
        tooltip = action.toolTip() or self._action_label(action)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        action.setText("")
        button.setStyleSheet(
            "QToolButton#memberCardIconButton {"
            " border: 1px solid rgba(120, 150, 190, 217); padding: 4px; border-radius: 6px;"
            " background-color: rgba(35, 50, 70, 242); color: #ffffff; }"
            "QToolButton#memberCardIconButton:hover, QToolButton#memberCardIconButton:focus {"
            " background-color: rgba(65, 100, 140, 242); color: #ffffff; }"
            "QToolButton#memberCardIconButton:disabled {"
            " border: 1px solid rgba(90, 90, 90, 217);"
            " background-color: rgba(50, 50, 50, 217); color: rgba(230, 230, 230, 217); }"
        )
        return button

    def _action_label(self, action: QAction) -> str:
        tooltip = (action.toolTip() or "").lower()
        if "editar" in tooltip:
            return "Editar"
        if "eliminar" in tooltip:
            return "Eliminar"
        return "Accion"

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _toggle_edit_mode(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        self._editing = not self._editing
        logger.info(
            "Member edit mode changed: editing=%s member_id=%s",
            self._editing,
            self._current_state.member_id,
        )
        self._update_edit_widgets()
        self.edit_mode_changed.emit(self._editing)

    def _request_delete(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        self.delete_requested.emit(self._current_state.member_id)

    def _cancel_edit(self) -> None:
        logger.info("Member edit cancelled for member_id=%s", self._current_state.member_id)
        self._editing = False
        self._populate_from_state()
        self._update_edit_widgets()
        self.edit_mode_changed.emit(False)

    def _on_save_clicked(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        logger.info("Member save requested for member_id=%s", self._current_state.member_id)
        payload = self._collect_payload()
        if not payload.is_valid():
            show_warning(self, "Completa los datos requeridos antes de guardar.", title="Editar socio")
            return
        self.save_requested.emit(self._current_state.member_id, payload)

    def _validate_inputs(self) -> None:
        if not self._editing:
            return

        name_text = self.name_input.text().strip()
        email_text = self.email_input.text().strip()
        phone_text = self.phone_input.text().strip()

        email_valid = bool(email_text) and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_text))
        phone_valid = bool(phone_text) and bool(re.fullmatch(r"\+?\d{8,15}", phone_text))
        name_valid = bool(name_text)

        self._set_invalid_state(self.name_input, not name_valid)
        self._set_invalid_state(self.email_input, not email_valid)
        self._set_invalid_state(self.phone_input, not phone_valid)

        enable = all((name_valid, email_valid, phone_valid)) and not self._loading
        self.save_button.setEnabled(enable)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _collect_payload(self) -> BasicInfoPayload:
        return BasicInfoPayload(
            name=self.name_input.text().strip(),
            email=self.email_input.text().strip(),
            phone=self.phone_input.text().strip(),
        )

    def _populate_from_state(self) -> None:
        data = self._current_state
        name_text = data.full_name or "-"
        email_text = data.email or "-"
        phone_text = data.phone_number or "-"
        plan_text = data.membership.plan_name or "-"
        status_text = data.membership.status or "-"

        self.name_value.setText(name_text)
        self.name_value.setToolTip(name_text)
        self.email_value.setText(email_text)
        self.email_value.setToolTip(email_text)
        self.phone_value.setText(phone_text)
        self.plan_value.setText(plan_text)

        # Backend now calculates the real status
        self.status_value.setText(status_text)

        if data.standing_booking:
            schedule_text = self._format_schedule_label(data.standing_booking)
            center_text = getattr(data.standing_booking, "venue_name", None) or "-"
        else:
            schedule_text = "-"
            center_text = "-"

        self.schedule_value.setText(schedule_text)
        self.schedule_value.setToolTip(schedule_text)
        self.center_value.setText(center_text)
        self.center_value.setToolTip(center_text)

        # Update avatar
        self.avatar_widget.set_initials(data.full_name)
        if data.profile_picture_url:
            # Convert relative URL to full URL if needed
            if data.profile_picture_url.startswith('/'):
                full_url = f"{Config.API_BASE_URL}{data.profile_picture_url}"
                self.avatar_widget.set_image_from_url(full_url)
            else:
                self.avatar_widget.set_image_from_url(data.profile_picture_url)
        else:
            self.avatar_widget.clear_image()

        # Format and display dates
        if data.registration_date:
            formatted_date = self._format_date(data.registration_date)
            self.member_since_value.setText(formatted_date)
        else:
            self.member_since_value.setText("-")

        if data.membership.start_date:
            formatted_date = self._format_date(data.membership.start_date)
            self.membership_start_value.setText(formatted_date)
        else:
            self.membership_start_value.setText("-")

        # Display remaining days with color indicator - backend calculates this now
        if data.membership.remaining_days is not None:
            days = data.membership.remaining_days

            # Handle negative days (expired memberships)
            if days < 0:
                days_text = f"{abs(days)} {'día' if abs(days) == 1 else 'días'} (vencida)"
                color = "#d32f2f"  # Red for expired
            else:
                days_text = f"{days} {'día' if days == 1 else 'días'}"

                # Color based on days remaining
                if days <= 3:
                    color = "#d32f2f"  # Red for urgent
                elif days <= 7:
                    color = "#f57c00"  # Orange for warning
                else:
                    color = "#388e3c"  # Green for OK

            self.remaining_days_value.setText(f"⏱️ {days_text}")
            self.remaining_days_value.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {color};"
            )
        else:
            self.remaining_days_value.setText("-")
            self.remaining_days_value.setStyleSheet("font-size: 14px; font-weight: 500;")

        self.name_input.setText(data.full_name if data.full_name != "-" else "")
        self.email_input.setText(data.email if data.email != "-" else "")
        self.phone_input.setText(data.phone_number if data.phone_number != "-" else "")

        self._update_edit_widgets()

    def _format_date(self, date) -> str:
        """Format date in Spanish format."""
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        return f"{date.day} de {months.get(date.month, '')} de {date.year}"

    def _format_schedule_label(self, booking) -> str:
        name_label = (
            getattr(booking, "template_name", None)
            or getattr(booking, "class_type_name", None)
            or ""
        )
        label = str(name_label).strip()
        return label or "-"

    def _weekday_name(self, weekday: Optional[int]) -> str:
        if weekday is None:
            return ""
        mapping = {
            0: "Domingo",
            1: "Lunes",
            2: "Martes",
            3: "Miercoles",
            4: "Jueves",
            5: "Viernes",
            6: "Sabado",
            7: "Domingo",
        }
        return mapping.get(int(weekday), "")

    def _update_edit_widgets(self) -> None:
        is_editing = self._editing and bool(self._current_state.member_id)

        self.name_value.setVisible(not is_editing)
        self.email_value.setVisible(not is_editing)
        self.phone_value.setVisible(not is_editing)

        self.name_input.setVisible(is_editing)
        self.email_input.setVisible(is_editing)
        self.phone_input.setVisible(is_editing)
        self.buttons_container.setVisible(is_editing)

        if is_editing:
            self.name_input.setFocus()
            self.scroll_area.ensureWidgetVisible(self.name_input)
            self._validate_inputs()
        else:
            self.save_button.setEnabled(False)
            self._clear_invalid_state()

    def _setup_shortcuts(self) -> None:
        self._cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._cancel_shortcut.activated.connect(self._on_cancel_shortcut)

        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._save_shortcut.activated.connect(self._on_save_shortcut)

    def resizeEvent(self, event) -> None:
        """Keep scroll content width in sync with viewport to avoid horizontal clipping."""
        super().resizeEvent(event)
        self._sync_scroll_content_width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_scroll_content_width()

    def eventFilter(self, obj, event):
        if obj is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_scroll_content_width()
        return super().eventFilter(obj, event)

    def _sync_scroll_content_width(self) -> None:
        widget = self.scroll_area.widget()
        if widget is None:
            return
        viewport_width = self.scroll_area.viewport().width()
        if viewport_width > 0:
            widget.setFixedWidth(viewport_width)

    def _on_cancel_shortcut(self) -> None:
        if self._editing and not self._loading:
            logger.info("ESC shortcut triggered member edit cancel for member_id=%s", self._current_state.member_id)
            self.cancel_edit()

    def _on_save_shortcut(self) -> None:
        if self._editing and not self._loading:
            logger.info("Ctrl+S shortcut triggered member save for member_id=%s", self._current_state.member_id)
            self.save_if_valid()

    def _update_actions(self) -> None:
        has_member = bool(self._current_state.member_id)
        can_edit = has_member and not self._loading
        can_delete = has_member and not self._loading

        self.set_actions_enabled(can_edit, can_delete)
        self.cancel_button.setEnabled(self._editing and not self._loading)
        has_schedule = self._current_state.standing_booking is not None
        membership_status = (self._current_state.membership.status or "").lower()
        can_reschedule = (
            has_schedule
            and membership_status == "active"
            and not self._editing
            and not self._loading
        )
        self.change_schedule_button.setEnabled(can_reschedule)
        if self._editing:
            self._validate_inputs()
        else:
            self.save_button.setEnabled(False)

    def _on_reschedule_clicked(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        self.reschedule_requested.emit(self._current_state.member_id)

    def _set_invalid_state(self, widget: QLineEdit, invalid: bool) -> None:
        widget.setProperty("invalid", "true" if invalid else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _clear_invalid_state(self) -> None:
        for editor in (self.name_input, self.email_input, self.phone_input):
            self._set_invalid_state(editor, False)

    def _load_icon(self, icon_name: str) -> QIcon:
        icon_path = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_name
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            if self._icon_is_renderable(icon, QSize(16, 16)):
                return icon

        style = self.style()
        if style is not None:
            fallback_names = []
            if "trash" in icon_name:
                fallback_names = ["SP_TrashIcon", "SP_DialogDiscardButton"]
            if "edit" in icon_name or "pencil" in icon_name:
                # No hay icono "pencil" estandar; usar fallback legible.
                fallback_names = [
                    "SP_FileDialogDetailedView",
                    "SP_FileDialogContentsView",
                    "SP_DialogApplyButton",
                ]

            for pixmap_name in fallback_names:
                pixmap = getattr(QStyle.StandardPixmap, pixmap_name, None)
                if pixmap is not None:
                    icon = style.standardIcon(pixmap)
                    if self._icon_is_renderable(icon, QSize(16, 16)):
                        return icon

        return QIcon()

    def _icon_is_renderable(self, icon: QIcon, size: QSize) -> bool:
        if icon.isNull():
            return False
        pixmap = icon.pixmap(size)
        if pixmap.isNull():
            return False
        image = pixmap.toImage()
        if image.isNull():
            return False
        if not image.hasAlphaChannel():
            return True
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 0:
                    return True
        return False

    def _on_avatar_changed(self, file_path: str) -> None:
        """Handle avatar change event."""
        if self._current_state.member_id and file_path:
            self.avatar_upload_requested.emit(self._current_state.member_id, file_path)

    def _on_avatar_removed(self) -> None:
        """Handle avatar removal event."""
        if self._current_state.member_id:
            self.avatar_delete_requested.emit(self._current_state.member_id)


