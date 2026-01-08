"""Member detail card widget for the members tab."""

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal, QRegularExpression
from ....core.config import Config
from PySide6.QtGui import QAction, QIcon, QRegularExpressionValidator, QPainter, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....viewmodels.members_state import BasicInfoPayload, MemberDetailState
from .avatar_widget import AvatarWidget
from ....utils.dialog_helpers import show_warning


class MemberDetailCard(QWidget):
    """Displays member details and handles inline editing."""

    save_requested = Signal(int, object)  # member_id, BasicInfoPayload
    delete_requested = Signal(int)
    edit_mode_changed = Signal(bool)
    avatar_upload_requested = Signal(int, str)  # member_id, file_path
    avatar_delete_requested = Signal(int)  # member_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_state = MemberDetailState()
        self._editing = False
        self._loading = False

        self._build_ui()
        self._update_actions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_state(self, state: MemberDetailState) -> None:
        """Update the card with the provided member state."""
        self._current_state = state
        if not state.member_id:
            self._editing = False
        self._populate_from_state()
        self._update_actions()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        if loading and self._editing:
            self._editing = False
            self._populate_from_state()
        self._update_actions()

    def set_actions_enabled(self, can_edit: bool, can_delete: bool) -> None:
        if self._loading:
            can_edit = False
            can_delete = False
        self.edit_action.setEnabled(can_edit)
        self.edit_button.setEnabled(can_edit)
        self.delete_action.setEnabled(can_delete)
        self.delete_button.setEnabled(can_delete)

    def reset(self) -> None:
        """Clear content and exit edit mode."""
        self._current_state = MemberDetailState()
        self._editing = False
        self._populate_from_state()
        self._update_actions()

    def is_editing(self) -> bool:
        return self._editing

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with avatar and title
        header_container = QWidget()
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

        self.membership_end_label = QLabel("Vencimiento de membresía")
        self.membership_end_label.setStyleSheet(label_style)
        layout.addWidget(self.membership_end_label)

        self.membership_end_value = QLabel("-")
        self.membership_end_value.setStyleSheet(value_style)
        layout.addWidget(self.membership_end_value)

        self.remaining_days_label = QLabel("Días restantes")
        self.remaining_days_label.setStyleSheet(label_style)
        layout.addWidget(self.remaining_days_label)

        self.remaining_days_value = QLabel("-")
        self.remaining_days_value.setStyleSheet(value_style)
        layout.addWidget(self.remaining_days_value)

        buttons_container = QWidget(self)
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch()

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self._cancel_edit)
        buttons_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton("Guardar")
        self.save_button.clicked.connect(self._on_save_clicked)
        self.save_button.setEnabled(False)
        buttons_layout.addWidget(self.save_button)

        buttons_container.setVisible(False)
        self.buttons_container = buttons_container
        layout.addWidget(buttons_container)
        layout.addStretch()

    def _build_icon_button(self, action: QAction) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("memberCardIconButton")
        button.setDefaultAction(action)
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(action.toolTip())
        button.setStyleSheet(
            "QToolButton#memberCardIconButton {"
            " border: none; padding: 4px; border-radius: 6px;"
            " background-color: rgba(0, 0, 0, 0.18); color: #ffffff; }"
            "QToolButton#memberCardIconButton:hover, QToolButton#memberCardIconButton:focus {"
            " background-color: palette(highlight); color: palette(base); }"
            "QToolButton#memberCardIconButton:disabled {"
            " background-color: rgba(0, 0, 0, 0.08); color: rgba(255, 255, 255, 0.6); }"
        )
        return button

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _toggle_edit_mode(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        self._editing = not self._editing
        self._update_edit_widgets()
        self.edit_mode_changed.emit(self._editing)

    def _request_delete(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
        self.delete_requested.emit(self._current_state.member_id)

    def _cancel_edit(self) -> None:
        self._editing = False
        self._populate_from_state()
        self._update_edit_widgets()
        self.edit_mode_changed.emit(False)

    def _on_save_clicked(self) -> None:
        if self._loading or not self._current_state.member_id:
            return
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
        self.name_value.setText(data.full_name or "-")
        self.email_value.setText(data.email or "-")
        self.phone_value.setText(data.phone_number or "-")
        self.plan_value.setText(data.membership.plan_name)

        # Backend now calculates the real status
        self.status_value.setText(data.membership.status)

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

        if data.membership.end_date:
            formatted_date = self._format_date(data.membership.end_date)
            self.membership_end_value.setText(formatted_date)
        else:
            self.membership_end_value.setText("-")

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
            self._validate_inputs()
        else:
            self.save_button.setEnabled(False)
            self._clear_invalid_state()

    def _update_actions(self) -> None:
        has_member = bool(self._current_state.member_id)
        can_edit = has_member and not self._loading
        can_delete = has_member and not self._loading

        self.set_actions_enabled(can_edit, can_delete)
        self.cancel_button.setEnabled(self._editing and not self._loading)
        if self._editing:
            self._validate_inputs()
        else:
            self.save_button.setEnabled(False)

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
            return QIcon(str(icon_path))
        return QIcon()

    def _on_avatar_changed(self, file_path: str) -> None:
        """Handle avatar change event."""
        if self._current_state.member_id and file_path:
            self.avatar_upload_requested.emit(self._current_state.member_id, file_path)

    def _on_avatar_removed(self) -> None:
        """Handle avatar removal event."""
        if self._current_state.member_id:
            self.avatar_delete_requested.emit(self._current_state.member_id)


