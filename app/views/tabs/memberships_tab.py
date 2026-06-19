"""
Vista de la pestaña de Membresías - CRUD del catálogo de planes.

Soporta dos enfoques de plan:
- Horario fijo (paquete con slot semanal recurrente)
- Acceso libre (por tiempo, sin horario ni límite)
- Créditos prepagados (pago por sesión: N clases/créditos con vigencia)

Solo los usuarios con la capacidad ``manage_membership_plans`` (admin por
defecto) pueden crear/editar/eliminar; el resto ve la lista en modo lectura.
"""
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QDialog,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QTextEdit, QCheckBox, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...models.base import MembershipPlan
from ...utils.dialog_helpers import show_confirmation, show_error, show_info
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)

MANAGE_CAPABILITY = "manage_membership_plans"

# (display label, code) pairs reused by the dialog.
PLAN_TYPE_CHOICES = [
    ("Horario fijo", "fixed_schedule"),
    ("Acceso libre", "flexible"),
    ("Créditos prepagados", "credit_pack"),
]
DURATION_UNIT_CHOICES = [
    ("días", "day"),
    ("semanas", "week"),
    ("meses", "month"),
]


class MembershipsTab(QWidget):
    """Vista para gestión del catálogo de planes/membresías."""

    def __init__(self):
        super().__init__()

        try:
            memberships_service = container.get("memberships_service")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve memberships_service: %s", exc)
            raise

        # Capability gating (admin por defecto).
        self._can_manage = self._resolve_can_manage()

        from ...controllers.memberships_controller import MembershipsController
        self.controller = MembershipsController(memberships_service, self)

        self._plans: List[MembershipPlan] = []

        self.setup_ui()
        self._connect_controller()
        self.controller.load_plans()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _resolve_can_manage(self) -> bool:
        try:
            auth_service = container.get("auth_service")
            return bool(auth_service.has_capability(MANAGE_CAPABILITY))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not resolve capability, defaulting to read-only: %s", exc)
            return False

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Catálogo de Membresías")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.new_btn = QPushButton("+ Nueva Membresía")
        self.new_btn.setObjectName("primaryButton")
        self.new_btn.clicked.connect(self.on_new_clicked)
        header_layout.addWidget(self.new_btn)

        self.edit_btn = QPushButton("Editar")
        self.edit_btn.setObjectName("actionButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.on_edit_clicked)
        header_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Eliminar")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        header_layout.addWidget(self.delete_btn)

        self.reactivate_btn = QPushButton("Reactivar")
        self.reactivate_btn.setObjectName("actionButton")
        self.reactivate_btn.setEnabled(False)
        self.reactivate_btn.clicked.connect(self.on_reactivate_clicked)
        header_layout.addWidget(self.reactivate_btn)

        layout.addLayout(header_layout)

        if not self._can_manage:
            hint = QLabel("Solo lectura: no tienes permiso para gestionar planes.")
            hint.setObjectName("hintLabel")
            layout.addWidget(hint)
            self.new_btn.setEnabled(False)

        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nombre", "Tipo", "Precio", "Vigencia",
            "Créditos/Clases", "Activo", "Descripción",
        ])
        configure_table_widget(self.table)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        if self._can_manage:
            self.table.cellDoubleClicked.connect(lambda *_: self.on_edit_clicked())
        layout.addWidget(self.table)

        # Resumen
        summary_layout = QHBoxLayout()
        self.summary_label = QLabel("0 membresías registradas")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()
        layout.addLayout(summary_layout)

    def _connect_controller(self):
        self.controller.plans_loaded.connect(self._on_plans_loaded)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.mutation_succeeded.connect(self._on_mutation_succeeded)
        self.controller.mutation_failed.connect(self._on_error)

    # ------------------------------------------------------------------
    # Controller callbacks
    # ------------------------------------------------------------------
    def _on_plans_loaded(self, plans: List[MembershipPlan]):
        self._plans = list(plans)
        self.table.setRowCount(len(self._plans))

        for row, plan in enumerate(self._plans):
            credits = str(plan.class_limit) if plan.class_limit else "—"
            self._set_cell(row, 0, str(plan.id))
            self._set_cell(row, 1, plan.name)
            self._set_cell(row, 2, plan.type_display())
            self._set_cell(row, 3, plan.price_display())
            self._set_cell(row, 4, plan.duration_display())
            self._set_cell(row, 5, credits)
            self._set_cell(row, 6, "Sí" if plan.is_active else "No")
            self._set_cell(row, 7, plan.description or "")

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.on_selection_changed()
        self._update_summary()

    def _on_mutation_succeeded(self, message: str):
        show_info(self, message or "Operación exitosa", title="Membresías")

    def _on_error(self, message: str):
        show_error(self, message or "Ocurrió un error.", title="Membresías")

    def _set_cell(self, row: int, col: int, text: str):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Selection / actions
    # ------------------------------------------------------------------
    def _selected_plan(self) -> Optional[MembershipPlan]:
        row = self.table.currentRow()
        if 0 <= row < len(self._plans):
            return self._plans[row]
        return None

    def on_selection_changed(self):
        plan = self._selected_plan()
        has_selection = plan is not None and self._can_manage
        self.edit_btn.setEnabled(has_selection)
        # Eliminar solo para planes activos; Reactivar solo para inactivos.
        self.delete_btn.setEnabled(has_selection and bool(plan and plan.is_active))
        self.reactivate_btn.setEnabled(has_selection and bool(plan and not plan.is_active))

    def on_new_clicked(self):
        if not self._can_manage:
            return
        dialog = PlanDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.create_plan(dialog.get_data())

    def on_edit_clicked(self):
        if not self._can_manage:
            return
        plan = self._selected_plan()
        if not plan:
            return
        dialog = PlanDialog(self, plan=plan)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.update_plan(plan.id, dialog.get_data())

    def on_delete_clicked(self):
        if not self._can_manage:
            return
        plan = self._selected_plan()
        if not plan:
            return
        if show_confirmation(
            self,
            f"¿Desactivar la membresía '{plan.name}'? Dejará de venderse pero se "
            f"conservará el historial. Podrás reactivarla luego.",
            title="Desactivar membresía",
            ok_text="Desactivar",
            cancel_text="Cancelar",
        ):
            self.controller.deactivate_plan(plan.id)

    def on_reactivate_clicked(self):
        if not self._can_manage:
            return
        plan = self._selected_plan()
        if not plan:
            return
        self.controller.activate_plan(plan.id)

    def _update_summary(self):
        active = sum(1 for p in self._plans if p.is_active)
        total = len(self._plans)
        self.summary_label.setText(f"{total} membresías ({active} activas)")


class PlanDialog(QDialog):
    """Diálogo para crear/editar un plan de membresía."""

    def __init__(self, parent=None, plan: Optional[MembershipPlan] = None):
        super().__init__(parent)
        self.plan = plan
        self.setup_ui()
        if plan:
            self.load_plan(plan)
        self._on_type_changed()

    def setup_ui(self):
        self.setWindowTitle("Editar Membresía" if self.plan else "Nueva Membresía")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._form = form

        # Tipo de plan
        self.type_input = QComboBox()
        for label, code in PLAN_TYPE_CHOICES:
            self.type_input.addItem(label, code)
        self.type_input.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Tipo de plan:", self.type_input)

        # Nombre
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: Paquete 10 clases")
        form.addRow("Nombre:", self.name_input)

        # Precio
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 999999)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("$ ")
        self.price_input.setSuffix(" MXN")
        form.addRow("Precio:", self.price_input)

        # Vigencia (valor + unidad)
        duration_row = QHBoxLayout()
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 999)
        self.duration_input.setValue(30)
        duration_row.addWidget(self.duration_input)
        self.duration_unit = QComboBox()
        for label, code in DURATION_UNIT_CHOICES:
            self.duration_unit.addItem(label, code)
        duration_row.addWidget(self.duration_unit)
        duration_widget = QWidget()
        duration_widget.setLayout(duration_row)
        form.addRow("Vigencia:", duration_widget)

        # Créditos / nº de clases (class_limit)
        self.class_limit_input = QSpinBox()
        self.class_limit_input.setRange(0, 9999)
        self.class_limit_input.setSpecialValueText("Sin límite")  # 0 -> sin límite
        form.addRow("Créditos / Clases:", self.class_limit_input)

        # Avanzado: límites de sesiones
        self.max_day_input = QSpinBox()
        self.max_day_input.setRange(0, 99)
        self.max_day_input.setSpecialValueText("Sin límite")
        form.addRow("Máx. sesiones/día:", self.max_day_input)

        self.max_week_input = QSpinBox()
        self.max_week_input.setRange(0, 99)
        self.max_week_input.setSpecialValueText("Sin límite")
        form.addRow("Máx. sesiones/semana:", self.max_week_input)

        # Activo (solo en edición)
        self.active_input = QCheckBox("Plan activo (visible y a la venta)")
        self.active_input.setChecked(True)
        if self.plan:
            form.addRow("Estado:", self.active_input)

        # Descripción
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        self.description_input.setPlaceholderText("Descripción opcional...")
        form.addRow("Descripción:", self.description_input)

        # Nota contextual por tipo
        self.type_note = QLabel("")
        self.type_note.setWordWrap(True)
        self.type_note.setObjectName("hintLabel")
        form.addRow("", self.type_note)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_row_visible(self, field_widget: QWidget, visible: bool):
        field_widget.setVisible(visible)
        label = self._form.labelForField(field_widget)
        if label is not None:
            label.setVisible(visible)

    def _on_type_changed(self, *_):
        plan_type = self.type_input.currentData()
        # class_limit applies to credit packs (required) and fixed schedule (optional);
        # hidden for flexible (open access).
        self._set_row_visible(self.class_limit_input, plan_type in ("credit_pack", "fixed_schedule"))

        notes = {
            "fixed_schedule": "Horario fijo: el socio elige un horario semanal recurrente al inscribirse. "
                              "Créditos/Clases es opcional (0 = sin límite).",
            "flexible": "Acceso libre: vigencia por tiempo, sin horario fijo ni límite de clases.",
            "credit_pack": "Créditos prepagados (pago por sesión): el socio compra N clases/créditos "
                           "y consume uno por reserva, dentro de la vigencia.",
        }
        self.type_note.setText(notes.get(plan_type, ""))

    def load_plan(self, plan: MembershipPlan):
        idx = self.type_input.findData(plan.plan_type)
        if idx >= 0:
            self.type_input.setCurrentIndex(idx)
        self.name_input.setText(plan.name or "")
        self.price_input.setValue(float(plan.price or 0))
        self.duration_input.setValue(int(plan.duration_value or 1))
        unit_idx = self.duration_unit.findData(plan.duration_unit)
        if unit_idx >= 0:
            self.duration_unit.setCurrentIndex(unit_idx)
        self.class_limit_input.setValue(int(plan.class_limit or 0))
        self.max_day_input.setValue(int(plan.max_sessions_per_day or 0))
        self.max_week_input.setValue(int(plan.max_sessions_per_week or 0))
        self.active_input.setChecked(bool(plan.is_active))
        self.description_input.setPlainText(plan.description or "")

    def _on_accept(self):
        plan_type = self.type_input.currentData()
        if not self.name_input.text().strip():
            show_error(self, "El nombre es obligatorio.", title="Datos incompletos")
            return
        if plan_type == "credit_pack" and self.class_limit_input.value() <= 0:
            show_error(
                self,
                "Para un paquete de créditos prepagados debes indicar el número de créditos/clases (> 0).",
                title="Datos incompletos",
            )
            return
        self.accept()

    def get_data(self) -> dict:
        plan_type = self.type_input.currentData()
        class_limit_val = self.class_limit_input.value()
        # 0 means "sin límite" -> None. For flexible plans there is never a limit.
        class_limit = None
        if plan_type in ("credit_pack", "fixed_schedule") and class_limit_val > 0:
            class_limit = class_limit_val

        return {
            "plan_type": plan_type,
            "name": self.name_input.text().strip(),
            "price": self.price_input.value(),
            "duration_value": self.duration_input.value(),
            "duration_unit": self.duration_unit.currentData(),
            "class_limit": class_limit,
            "max_sessions_per_day": self.max_day_input.value() or None,
            "max_sessions_per_week": self.max_week_input.value() or None,
            "is_active": self.active_input.isChecked(),
            "description": self.description_input.toPlainText().strip() or None,
        }
