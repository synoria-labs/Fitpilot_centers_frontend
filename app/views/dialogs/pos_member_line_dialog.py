"""Dialog to add a membership line (alta or renovación) to a POS sale.

Reuses the membership-plan catalog and the standard amount input. Member search
happens in the POS tab; this dialog receives the chosen member for renewals.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QLineEdit, QVBoxLayout,
)

from ...utils.qt_helpers import configure_amount_input, get_combo_selected_data, populate_combo_safely


class PosMembershipLineDialog(QDialog):
    def __init__(
        self,
        mode: str,                         # 'new' | 'renewal'
        plans: List[Any],
        member: Optional[Dict[str, Any]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self._plans = plans or []
        self._member = member or {}
        self.setWindowTitle("Alta de membresía" if mode == "new" else "Renovación de membresía")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        if mode == "renewal":
            name = self._member.get("full_name") or self._member.get("fullName") or "Socio"
            form.addRow("Socio:", QLabel(str(name)))
        else:
            self.name_input = QLineEdit()
            self.name_input.setPlaceholderText("Nombre completo")
            self.email_input = QLineEdit()
            self.email_input.setPlaceholderText("Opcional")
            self.phone_input = QLineEdit()
            self.phone_input.setPlaceholderText("WhatsApp (opcional)")
            form.addRow("Nombre:", self.name_input)
            form.addRow("Email:", self.email_input)
            form.addRow("Teléfono:", self.phone_input)

        self.plan_combo = QComboBox()
        populate_combo_safely(
            self.plan_combo, self._plans, lambda p: f"{p.name} (${p.price:,.2f})", lambda p: p
        )
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        form.addRow("Plan:", self.plan_combo)

        self.amount_input = QDoubleSpinBox()
        configure_amount_input(self.amount_input, 1_000_000)
        self.amount_input.setPrefix("$ ")
        form.addRow("Monto:", self.amount_input)

        layout.addLayout(form)

        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #e67e22;")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Agregar")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_plan_changed()

    def _selected_plan(self):
        return get_combo_selected_data(self.plan_combo)

    def _on_plan_changed(self) -> None:
        plan = self._selected_plan()
        if plan is not None:
            self.amount_input.setValue(float(plan.price or 0))
        # Alta of a fixed-schedule plan needs a class slot -> guide the user.
        needs_slot = bool(plan and getattr(plan, "fixed_time_slot", False) and self.mode == "new")
        self.warning_label.setVisible(needs_slot)
        if needs_slot:
            self.warning_label.setText(
                "Este plan tiene horario fijo. Para el alta con clase/asiento usa la pestaña "
                "Socios. Aquí solo puedes vender planes flexibles o de créditos."
            )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not needs_slot)

    def _on_accept(self) -> None:
        if self._selected_plan() is None:
            self.warning_label.setText("Selecciona un plan.")
            self.warning_label.setVisible(True)
            return
        if self.mode == "new" and not self.name_input.text().strip():
            self.warning_label.setText("Ingresa el nombre del socio.")
            self.warning_label.setVisible(True)
            return
        self.accept()

    def get_line(self) -> Dict[str, Any]:
        plan = self._selected_plan()
        amount = float(self.amount_input.value())
        line: Dict[str, Any] = {
            "plan_id": plan.id,
            "unit_price": amount,
        }
        if self.mode == "new":
            line["line_type"] = "membership_new"
            line["full_name"] = self.name_input.text().strip()
            line["email"] = self.email_input.text().strip() or None
            line["phone_number"] = self.phone_input.text().strip() or None
            line["description"] = f"Alta: {plan.name}"
        else:
            line["line_type"] = "membership_renewal"
            line["member_id"] = int(self._member.get("id"))
            line["description"] = f"Renovación: {plan.name}"
        return line
