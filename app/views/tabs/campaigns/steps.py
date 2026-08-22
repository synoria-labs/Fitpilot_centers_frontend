"""Los tres pasos del asistente de campañas: audiencia, mensaje y revisión.

La versión anterior ponía todo en un solo formulario con scroll: objetivo, predicados de
audiencia en crudo, mapeo de variables, programación, ocho botones de acción y las métricas,
todo visible a la vez. Separarlo en pasos no es decoración — cada paso responde una sola
pregunta (*a quién*, *qué les digo*, *cuándo lo mando*) y el usuario solo ve los controles
que importan en ese momento.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QSpinBox, QVBoxLayout, QWidget,
)

from ..whatsapp.template_preview_widget import TemplatePreviewWidget

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

_MEMBERSHIP_STATES = [
    ("expired", "Vencidos"),
    ("active", "Activos"),
    ("pending", "Pendientes"),
]

# weekday is stored 0=Sunday .. 6=Saturday (backend classModel.ClassTemplate).
_WEEKDAY_SHORT = ("Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb")

# How a member must relate to the selected classes to enter the audience.
_AFFINITY_MODES = [
    ("favorite", "es la clase que más reservan"),
    ("attended", "la han reservado alguna vez"),
]


def body_placeholder_count(components: Optional[List[Any]]) -> int:
    for component in components or []:
        if isinstance(component, dict) and str(component.get("type") or "").upper() == "BODY":
            indices = [int(m) for m in _PLACEHOLDER_RE.findall(str(component.get("text") or ""))]
            return max(indices) if indices else 0
    return 0


def _component_of(components: Optional[List[Any]], kind: str) -> Optional[dict]:
    for component in components or []:
        if isinstance(component, dict) and str(component.get("type") or "").upper() == kind:
            return component
    return None


def class_key(level: str, class_id: Any) -> str:
    """Payload for a class row.

    A plain string, not a tuple: Qt compares item data as QVariants and relying on tuple
    wrapping to round-trip is a subtlety this does not need.
    """
    return f"{level}:{class_id}"


def parse_class_key(value: Any):
    """('class_type' | 'class_template', id) from a row payload, or None."""
    if not value:
        return None
    level, _, raw_id = str(value).partition(":")
    if level not in ("class_type", "class_template") or not raw_id.isdigit():
        return None
    return level, int(raw_id)


def template_label(template: Dict[str, Any]) -> str:
    """'Spinning · Lun 07:00' — the class *with its schedule*, as staff think of it."""
    name = template.get("class_type_name") or template.get("name") or "Clase"
    weekday = template.get("weekday")
    day = _WEEKDAY_SHORT[int(weekday) % 7] if weekday is not None else ""
    raw_time = str(template.get("start_time_local") or "")
    clock = raw_time[:5] if len(raw_time) >= 5 else raw_time
    suffix = " ".join(part for part in (day, clock) if part)
    return f"{name} · {suffix}" if suffix else str(name)


class AudienceStep(QWidget):
    """Paso 1 — a quién le hablamos: objetivo, membresía y clases."""

    spec_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._class_types: List[Dict[str, Any]] = []
        self._class_templates: List[Dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        basics = QGroupBox("Objetivo y nombre")
        basics.setObjectName("campGroup")
        form = QFormLayout(basics)
        form.setContentsMargins(10, 10, 10, 10)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ej. Reactivación agosto")
        form.addRow("Nombre", self.name_edit)
        self.objective_combo = QComboBox()
        form.addRow("Objetivo", self.objective_combo)
        self.description_edit = QLineEdit()
        form.addRow("Descripción", self.description_edit)
        layout.addWidget(basics)

        layout.addWidget(self._build_membership_group())
        layout.addWidget(self._build_classes_group())

        self.preview_label = QLabel("—")
        self.preview_label.setWordWrap(True)
        self.preview_label.setObjectName("campHint")
        layout.addWidget(self.preview_label)
        layout.addStretch()

        for widget in (
            self.end_range_check,
            self.inactive_check,
            self.class_check,
        ):
            widget.toggled.connect(self.spec_changed.emit)
        for spin in (self.end_min_spin, self.end_max_spin, self.inactive_spin):
            spin.valueChanged.connect(self.spec_changed.emit)
        for check in self.state_checks.values():
            check.toggled.connect(self.spec_changed.emit)
        self.class_mode_combo.currentIndexChanged.connect(self.spec_changed.emit)
        self.class_list.itemChanged.connect(lambda _item: self.spec_changed.emit())
        self.plan_list.itemChanged.connect(lambda _item: self.spec_changed.emit())

    # ------------------------------------------------------------------ build
    def _build_membership_group(self) -> QGroupBox:
        group = QGroupBox("Membresía")
        group.setObjectName("campGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        states = QHBoxLayout()
        states.addWidget(QLabel("Estado:"))
        self.state_checks: Dict[str, QCheckBox] = {}
        for key, label in _MEMBERSHIP_STATES:
            check = QCheckBox(label)
            if key == "expired":
                check.setChecked(True)
            self.state_checks[key] = check
            states.addWidget(check)
        states.addStretch()
        layout.addLayout(states)

        # Phrased forwards ("hace N días") instead of the raw negative day offsets the API
        # uses: nobody thinks about their lapsed members as "-90 to -7".
        end_row = QHBoxLayout()
        self.end_range_check = QCheckBox("Vencieron entre hace")
        self.end_range_check.setChecked(True)
        self.end_min_spin = QSpinBox()
        self.end_min_spin.setRange(0, 3650)
        self.end_min_spin.setValue(90)
        self.end_max_spin = QSpinBox()
        self.end_max_spin.setRange(0, 3650)
        self.end_max_spin.setValue(7)
        end_row.addWidget(self.end_range_check)
        end_row.addWidget(self.end_min_spin)
        end_row.addWidget(QLabel("y hace"))
        end_row.addWidget(self.end_max_spin)
        end_row.addWidget(QLabel("días"))
        end_row.addStretch()
        layout.addLayout(end_row)

        inactive_row = QHBoxLayout()
        self.inactive_check = QCheckBox("Sin reservar desde hace")
        self.inactive_spin = QSpinBox()
        self.inactive_spin.setRange(1, 3650)
        self.inactive_spin.setValue(30)
        inactive_row.addWidget(self.inactive_check)
        inactive_row.addWidget(self.inactive_spin)
        inactive_row.addWidget(QLabel("días"))
        inactive_row.addStretch()
        layout.addLayout(inactive_row)

        layout.addWidget(QLabel("Planes (opcional):"))
        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(90)
        layout.addWidget(self.plan_list)
        return group

    def _build_classes_group(self) -> QGroupBox:
        group = QGroupBox("Clases")
        group.setObjectName("campGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        mode_row = QHBoxLayout()
        self.class_check = QCheckBox("Filtrar por clase, cuando")
        self.class_mode_combo = QComboBox()
        for key, label in _AFFINITY_MODES:
            self.class_mode_combo.addItem(label, key)
        mode_row.addWidget(self.class_check)
        mode_row.addWidget(self.class_mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.class_list = QListWidget()
        self.class_list.setMaximumHeight(150)
        layout.addWidget(self.class_list)

        hint = QLabel(
            "Marca una actividad completa (Spinning) o solo algunos horarios "
            "(Spinning · Lun 07:00)."
        )
        hint.setObjectName("campHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return group

    # ------------------------------------------------------------------ data in
    def set_objectives(self, objectives: List[Dict[str, Any]]) -> None:
        self.objective_combo.clear()
        for objective in objectives or []:
            self.objective_combo.addItem(
                objective.get("label", objective.get("key")), objective.get("key")
            )

    def set_plans(self, plans: List[Dict[str, Any]]) -> None:
        self.plan_list.blockSignals(True)
        self.plan_list.clear()
        for plan in plans or []:
            item = QListWidgetItem(plan.get("name") or f"Plan {plan.get('id')}")
            item.setData(Qt.ItemDataRole.UserRole, plan.get("id"))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.plan_list.addItem(item)
        self.plan_list.blockSignals(False)

    def set_classes(self, class_types, class_templates) -> None:
        """Activities first, then their scheduled slots grouped underneath."""
        self._class_types = list(class_types or [])
        self._class_templates = [t for t in (class_templates or []) if t.get("is_active")]
        self.class_list.blockSignals(True)
        self.class_list.clear()

        by_type: Dict[Any, List[Dict[str, Any]]] = {}
        for template in self._class_templates:
            by_type.setdefault(template.get("class_type_id"), []).append(template)

        for class_type in self._class_types:
            self._add_class_item(
                class_type.get("name") or "?",
                class_key("class_type", class_type.get("id")),
            )
            for template in sorted(
                by_type.get(class_type.get("id"), []),
                key=lambda t: (t.get("weekday") or 0, str(t.get("start_time_local") or "")),
            ):
                self._add_class_item(
                    "    " + template_label(template),
                    class_key("class_template", template.get("id")),
                )
        self.class_list.blockSignals(False)

    def _add_class_item(self, label: str, payload: str) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, payload)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.class_list.addItem(item)

    def set_preview_text(self, text: str) -> None:
        self.preview_label.setText(text)

    # ------------------------------------------------------------------ spec IO
    def _checked_payloads(self, widget: QListWidget) -> List[Any]:
        return [
            widget.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(widget.count())
            if widget.item(row).checkState() == Qt.CheckState.Checked
        ]

    def audience_spec(self) -> Dict[str, Any]:
        predicates: List[Dict[str, Any]] = []
        states = [key for key, check in self.state_checks.items() if check.isChecked()]
        if states:
            predicates.append({"type": "membership_status", "in": states})

        if self.end_range_check.isChecked():
            # The UI counts days *ago*; the API counts signed days from today.
            predicates.append(
                {
                    "type": "membership_end_at",
                    "op": "between",
                    "days_from_now": [-self.end_min_spin.value(), -self.end_max_spin.value()],
                }
            )

        plan_ids = [pid for pid in self._checked_payloads(self.plan_list) if pid is not None]
        if plan_ids:
            predicates.append({"type": "plan_id", "in": plan_ids})

        if self.inactive_check.isChecked():
            predicates.append(
                {
                    "type": "last_activity",
                    "op": "older_than_days",
                    "value": self.inactive_spin.value(),
                }
            )

        if self.class_check.isChecked():
            selected = [parse_class_key(v) for v in self._checked_payloads(self.class_list)]
            selected = [s for s in selected if s]
            # Templates are the more specific answer, so a mixed selection uses them; the
            # backend predicate takes one granularity at a time.
            templates = [cid for level, cid in selected if level == "class_template"]
            types = [cid for level, cid in selected if level == "class_type"]
            level, ids = ("class_template", templates) if templates else ("class_type", types)
            if ids:
                predicates.append(
                    {
                        "type": "class_affinity",
                        "level": level,
                        "mode": self.class_mode_combo.currentData() or "favorite",
                        "in": ids,
                    }
                )
        return {"base": "members", "predicates": predicates}

    def apply_audience_spec(self, spec: Dict[str, Any]) -> None:
        predicates = (spec or {}).get("predicates") or []
        states: set = set()
        self.end_range_check.setChecked(False)
        self.inactive_check.setChecked(False)
        self.class_check.setChecked(False)
        self._uncheck_all(self.plan_list)
        self._uncheck_all(self.class_list)

        for predicate in predicates:
            ptype = predicate.get("type")
            if ptype == "membership_status":
                states = set(predicate.get("in") or [])
            elif ptype == "membership_end_at" and predicate.get("days_from_now"):
                low, high = sorted(predicate["days_from_now"])
                self.end_range_check.setChecked(True)
                self.end_min_spin.setValue(abs(int(low)))
                self.end_max_spin.setValue(abs(int(high)))
            elif ptype == "plan_id" and predicate.get("in"):
                self._check_payloads(self.plan_list, set(predicate["in"]))
            elif ptype == "last_activity" and predicate.get("op") == "older_than_days":
                self.inactive_check.setChecked(True)
                self.inactive_spin.setValue(int(predicate.get("value", 30)))
            elif ptype == "class_affinity" and predicate.get("in"):
                level = predicate.get("level") or "class_type"
                self.class_check.setChecked(True)
                self._check_payloads(
                    self.class_list,
                    {class_key(level, cid) for cid in predicate["in"]},
                )
                mode_index = self.class_mode_combo.findData(predicate.get("mode") or "favorite")
                if mode_index >= 0:
                    self.class_mode_combo.setCurrentIndex(mode_index)

        for key, check in self.state_checks.items():
            check.setChecked(key in states)

    @staticmethod
    def _uncheck_all(widget: QListWidget) -> None:
        widget.blockSignals(True)
        for row in range(widget.count()):
            widget.item(row).setCheckState(Qt.CheckState.Unchecked)
        widget.blockSignals(False)

    @staticmethod
    def _check_payloads(widget: QListWidget, payloads: set) -> None:
        widget.blockSignals(True)
        for row in range(widget.count()):
            item = widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) in payloads:
                item.setCheckState(Qt.CheckState.Checked)
        widget.blockSignals(False)


class MessageStep(QWidget):
    """Paso 2 — qué les decimos: plantilla, variables y la burbuja real."""

    test_send_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._templates: List[Dict[str, Any]] = []
        self._variables: List[Dict[str, Any]] = []
        self._param_combos: List[QComboBox] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        group = QGroupBox("Mensaje")
        group.setObjectName("campGroup")
        form = QFormLayout(group)
        form.setContentsMargins(10, 10, 10, 10)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self._rebuild_mapping)
        form.addRow("Plantilla", self.template_combo)
        self.mapping_container = QWidget()
        self.mapping_layout = QFormLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow("Variables", self.mapping_container)
        left_layout.addWidget(group)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("campHint")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        left_layout.addWidget(self.warning_label)

        left_layout.addStretch()
        layout.addWidget(left, 1)

        preview_column = QWidget()
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_title = QLabel("Así lo verá el socio")
        preview_title.setObjectName("campPreviewRailTitle")
        preview_layout.addWidget(preview_title)
        self.preview = TemplatePreviewWidget()
        self.preview.setMinimumHeight(340)
        preview_layout.addWidget(self.preview, 1)
        preview_column.setMinimumWidth(300)
        preview_column.setMaximumWidth(380)
        layout.addWidget(preview_column)

    # ------------------------------------------------------------------ data in
    def set_variables(self, variables: List[Dict[str, Any]]) -> None:
        self._variables = list(variables or [])

    def set_templates(self, templates: List[Dict[str, Any]]) -> None:
        self._templates = list(templates or [])
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("— Selecciona —", None)
        for template in self._templates:
            self.template_combo.addItem(template.get("template_name", "?"), template.get("id"))
        self.template_combo.blockSignals(False)
        self._rebuild_mapping()

    def current_template(self) -> Optional[Dict[str, Any]]:
        template_id = self.template_combo.currentData()
        return next((t for t in self._templates if t.get("id") == template_id), None)

    def select_template(self, template_id: Optional[int], mapping: Optional[List[str]]) -> None:
        index = self.template_combo.findData(template_id)
        self.template_combo.blockSignals(True)
        self.template_combo.setCurrentIndex(index if index >= 0 else 0)
        self.template_combo.blockSignals(False)
        self._rebuild_mapping(saved_mapping=mapping or [])

    def param_mapping(self) -> List[str]:
        return [combo.currentData() for combo in self._param_combos]

    def template_id(self) -> Optional[int]:
        return self.template_combo.currentData()

    # ------------------------------------------------------------------ internals
    def _rebuild_mapping(self, *_args, saved_mapping: Optional[List[str]] = None) -> None:
        while self.mapping_layout.rowCount():
            self.mapping_layout.removeRow(0)
        self._param_combos = []

        template = self.current_template()
        count = body_placeholder_count(template.get("components")) if template else 0
        for index in range(count):
            combo = QComboBox()
            for variable in self._variables:
                combo.addItem(variable.get("label", variable.get("key")), variable.get("key"))
            if saved_mapping and index < len(saved_mapping):
                found = combo.findData(saved_mapping[index])
                if found >= 0:
                    combo.setCurrentIndex(found)
            combo.currentIndexChanged.connect(self.refresh_preview)
            self._param_combos.append(combo)
            self.mapping_layout.addRow(f"{{{{{index + 1}}}}}", combo)
        self.refresh_preview()

    def refresh_preview(self, *_args) -> None:
        """Render the template with sample values, exactly as the dry run would."""
        template = self.current_template()
        if not template:
            self.preview.set_preview(body="Selecciona una plantilla para ver el mensaje.")
            self.warning_label.setVisible(False)
            return

        samples = {v.get("key"): v.get("sample", "") for v in self._variables}
        components = template.get("components")
        body_component = _component_of(components, "BODY")
        body = str((body_component or {}).get("text") or "")
        for index, key in enumerate(self.param_mapping(), start=1):
            body = body.replace(f"{{{{{index}}}}}", samples.get(key, ""))

        footer = _component_of(components, "FOOTER")
        header = _component_of(components, "HEADER")
        buttons = _component_of(components, "BUTTONS")
        header_format = str((header or {}).get("format") or "").upper()

        self.preview.set_preview(
            body=body,
            footer=(footer or {}).get("text"),
            header_text=(header or {}).get("text") if header_format == "TEXT" else None,
            media_format=header_format if header_format in ("IMAGE", "VIDEO", "DOCUMENT") else None,
            buttons=(buttons or {}).get("buttons"),
        )
        self._warn_about_class_variables()

    def _warn_about_class_variables(self) -> None:
        """A class variable on an audience with no class affinity renders as nothing.

        Better to say so here than to let the operator discover blank gaps in the messages
        their members already received.
        """
        uses_class_var = any(
            (key or "").startswith("favorite_class") for key in self.param_mapping()
        )
        self.warning_label.setVisible(uses_class_var)
        if uses_class_var:
            self.warning_label.setText(
                "Esta plantilla usa datos de la clase del socio. Quien no tenga historial de "
                "reservas recibirá ese espacio en blanco — combínala con un filtro de clase."
            )


class ReviewStep(QWidget):
    """Paso 3 — cuándo se manda, y qué se va a mandar exactamente."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary_group = QGroupBox("Resumen")
        summary_group.setObjectName("campGroup")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        self.summary_label = QLabel("—")
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_group)

        schedule_group = QGroupBox("Cuándo enviar")
        schedule_group.setObjectName("campGroup")
        schedule_layout = QVBoxLayout(schedule_group)
        schedule_layout.setContentsMargins(10, 10, 10, 10)
        schedule_layout.setSpacing(8)
        self.send_now_radio = QRadioButton("Enviar ahora")
        self.send_now_radio.setChecked(True)
        self.schedule_radio = QRadioButton("Programar")
        group = QButtonGroup(self)
        group.addButton(self.send_now_radio)
        group.addButton(self.schedule_radio)
        schedule_layout.addWidget(self.send_now_radio)

        schedule_row = QHBoxLayout()
        schedule_row.addWidget(self.schedule_radio)
        self.schedule_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_dt.setCalendarPopup(True)
        schedule_row.addWidget(self.schedule_dt)
        schedule_row.addStretch()
        schedule_layout.addLayout(schedule_row)

        self.quiet_hours_label = QLabel("")
        self.quiet_hours_label.setObjectName("campHint")
        self.quiet_hours_label.setWordWrap(True)
        self.quiet_hours_label.setVisible(False)
        schedule_layout.addWidget(self.quiet_hours_label)
        layout.addWidget(schedule_group)
        layout.addStretch()

    def set_summary(self, lines: List[str]) -> None:
        self.summary_label.setText("\n".join(lines))

    def is_scheduled(self) -> bool:
        return self.schedule_radio.isChecked()

    def scheduled_at(self):
        return self.schedule_dt.dateTime().toPython().astimezone()

    def set_quiet_hours_warning(self, message: str) -> None:
        self.quiet_hours_label.setText(message)
        self.quiet_hours_label.setVisible(bool(message))
