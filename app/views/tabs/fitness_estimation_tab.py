"""Configuration tab for the campaign fitness estimates (kcal / kg of fat).

The number this screen controls goes out over WhatsApp to real members, so the screen is
built to be *checkable* rather than merely editable. Three blocks, in the order someone
debugging a wrong number would want them:

1. **Lo que el sistema ya sabe** — opening days and class duration, read-only, derived from
   ``class_templates``. Most of the calculation needs no configuration at all, and an
   operator who thinks the estimate is wrong should first see whether the weekly schedule is
   loaded.
2. **Intensidad por actividad** — the one input no query can derive. Blank means "inherited
   from the default for this activity", shown next to the value actually in force so an
   untouched catalog does not look unconfigured.
3. **Política de la estimación** — reference weight, horizon, fallbacks.

Underneath, a worked example: every intermediate value, because "36 sesiones x 525 kcal" is
checkable and "18,900" is an assertion.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...controllers.fitness_estimation_controller import FitnessEstimationController
from ...core import container, get_logger
from ...utils.dialog_helpers import show_error, show_info
from ..screen_style import screen_qss
from .whatsapp import theme

logger = get_logger(__name__)

_TITLE = "Estimaciones"

# ``class_templates.weekday`` stores 0=domingo, the same convention as Postgres' ``dow``
# and as ``attendance_profile_service._WEEKDAY_NAMES``.
_WEEKDAYS = ("domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado")


def _icon(name: str, primary: bool = False):
    return qta.icon(name, color="#ffffff" if primary else theme.palette_hex())


def _weekday_summary(weekdays: List[int]) -> str:
    if not weekdays:
        return "sin horario cargado"
    return ", ".join(_WEEKDAYS[d] for d in sorted(weekdays) if 0 <= d <= 6)


class FitnessEstimationTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        service = container.get("fitness_estimation_service")
        self.controller = FitnessEstimationController(service, self)
        self._class_types: List[Dict[str, Any]] = []
        # Guards the cell-changed handler while the table is being repopulated from a
        # server response, so a repaint does not fire a save for every row it writes.
        self._loading_table = False

        self._build_ui()
        self._connect_controller()
        self.controller.load_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setObjectName("fitnessEstimationTab")
        self.setStyleSheet(screen_qss("bot"))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("botHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 14, 12)
        header_layout.setSpacing(8)

        row = QHBoxLayout()
        title = QLabel(_TITLE)
        title.setObjectName("botTitle")
        row.addWidget(title)
        row.addStretch()

        self.refresh_btn = QPushButton("Actualizar")
        self.refresh_btn.setIcon(_icon("fa5s.sync"))
        self.refresh_btn.setIconSize(QSize(14, 14))
        self.refresh_btn.clicked.connect(self.controller.load_settings)
        row.addWidget(self.refresh_btn)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setObjectName("botPrimaryButton")
        self.save_btn.setIcon(_icon("fa5s.save", primary=True))
        self.save_btn.setIconSize(QSize(14, 14))
        self.save_btn.clicked.connect(self._save_config)
        row.addWidget(self.save_btn)
        header_layout.addLayout(row)

        hint = QLabel(
            "Controla el cálculo de «kcal no quemadas» y «kg de grasa» que usan las campañas "
            "de reactivación. Los días de clase y la duración se toman del horario semanal "
            "cargado en Clases: si abres fines de semana o cambias la duración, el cálculo se "
            "ajusta solo. Aquí sólo se configura lo que no se puede deducir."
        )
        hint.setObjectName("botHint")
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(16)

        content.addWidget(self._build_schedule_group())
        content.addWidget(self._build_intensity_group())
        content.addWidget(self._build_policy_group())
        content.addWidget(self._build_preview_group())
        content.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _build_schedule_group(self) -> QGroupBox:
        box = QGroupBox("Horario detectado (sólo lectura)")
        layout = QFormLayout(box)
        self.schedule_days_label = QLabel("—")
        self.schedule_days_label.setWordWrap(True)
        self.schedule_duration_label = QLabel("—")
        self.schedule_templates_label = QLabel("—")
        layout.addRow("Días con clase", self.schedule_days_label)
        layout.addRow("Duración promedio", self.schedule_duration_label)
        layout.addRow("Horarios activos", self.schedule_templates_label)

        note = QLabel(
            "Se deduce de las plantillas activas del horario semanal. Un socio nunca puede "
            "«perder» más clases por semana que los días que abre el gimnasio."
        )
        note.setObjectName("botHint")
        note.setWordWrap(True)
        layout.addRow(note)
        return box

    def _build_intensity_group(self) -> QGroupBox:
        box = QGroupBox("Intensidad por actividad (MET)")
        layout = QVBoxLayout(box)

        note = QLabel(
            "El MET es lo único que el sistema no puede deducir del horario. Deja la celda "
            "vacía para usar el valor por defecto de la actividad (spinning 8.5, yoga 3.0…). "
            "Referencia: Compendium of Physical Activities."
        )
        note.setObjectName("botHint")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.intensity_table = QTableWidget(0, 3)
        self.intensity_table.setHorizontalHeaderLabels(
            ["Actividad", "MET propio", "MET en uso"]
        )
        self.intensity_table.verticalHeader().setVisible(False)
        self.intensity_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        header = self.intensity_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.intensity_table.setMinimumHeight(160)
        self.intensity_table.cellChanged.connect(self._on_met_cell_changed)
        layout.addWidget(self.intensity_table)
        return box

    def _build_policy_group(self) -> QGroupBox:
        box = QGroupBox("Política de la estimación")
        layout = QFormLayout(box)

        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(30.0, 200.0)
        self.weight_spin.setDecimals(1)
        self.weight_spin.setSuffix(" kg")
        layout.addRow("Peso de referencia", self.weight_spin)

        self.horizon_spin = QSpinBox()
        self.horizon_spin.setRange(1, 260)
        self.horizon_spin.setSuffix(" semanas")
        self.horizon_spin.setToolTip(
            "Sólo acota el total de kcal. Déjalo por encima de la ausencia más larga de tu "
            "audiencia: si muerde, todos los socios más viejos reciben el mismo número y una "
            "ausencia de dos años deja de decir más que una de tres meses."
        )
        layout.addRow("Tope de la ventana (kcal)", self.horizon_spin)

        self.default_cadence_spin = QDoubleSpinBox()
        self.default_cadence_spin.setRange(0.5, 7.0)
        self.default_cadence_spin.setDecimals(1)
        self.default_cadence_spin.setSingleStep(0.5)
        self.default_cadence_spin.setSuffix(" clases/semana")
        layout.addRow("Ritmo supuesto sin historial", self.default_cadence_spin)

        self.min_bookings_spin = QSpinBox()
        self.min_bookings_spin.setRange(1, 100)
        self.min_bookings_spin.setSuffix(" reservas")
        layout.addRow("Mínimo para usar su historial", self.min_bookings_spin)

        self.lookback_spin = QSpinBox()
        self.lookback_spin.setRange(7, 1095)
        self.lookback_spin.setSuffix(" días")
        layout.addRow("Historial que se mira", self.lookback_spin)

        self.net_check = QCheckBox("Descontar el metabolismo basal")
        layout.addRow("Neto", self.net_check)

        self.default_met_spin = QDoubleSpinBox()
        self.default_met_spin.setRange(1.0, 25.0)
        self.default_met_spin.setDecimals(1)
        layout.addRow("MET por defecto", self.default_met_spin)

        self.default_duration_spin = QSpinBox()
        self.default_duration_spin.setRange(15, 240)
        self.default_duration_spin.setSuffix(" min")
        layout.addRow("Duración por defecto", self.default_duration_spin)

        self.default_open_days_spin = QSpinBox()
        self.default_open_days_spin.setRange(1, 7)
        self.default_open_days_spin.setSuffix(" días")
        layout.addRow("Días abiertos por defecto", self.default_open_days_spin)

        self.adaptation_check = QCheckBox("Considerar la adaptación metabólica")
        self.adaptation_check.setToolTip(
            "El cuerpo compensa: baja el apetito y el gasto no-ejercicio, y un cuerpo más "
            "pesado cuesta más de mantener. El peso tiende a un equilibrio en vez de "
            "acumularse sin límite."
        )
        self.adaptation_check.toggled.connect(self._on_adaptation_toggled)
        layout.addRow("Modelo de kg", self.adaptation_check)

        self.half_life_spin = QSpinBox()
        self.half_life_spin.setRange(30, 1825)
        self.half_life_spin.setSuffix(" días")
        layout.addRow("Vida media hasta el equilibrio", self.half_life_spin)

        self.kg_per_100_spin = QDoubleSpinBox()
        self.kg_per_100_spin.setRange(1.0, 10.0)
        self.kg_per_100_spin.setDecimals(2)
        self.kg_per_100_spin.setSingleStep(0.1)
        self.kg_per_100_spin.setSuffix(" kg por 100 kcal/día")
        layout.addRow("Peso de equilibrio", self.kg_per_100_spin)

        self.kcal_per_kg_spin = QSpinBox()
        self.kcal_per_kg_spin.setRange(5000, 12000)
        self.kcal_per_kg_spin.setSingleStep(100)
        self.kcal_per_kg_spin.setSuffix(" kcal/kg")
        layout.addRow("Equivalencia lineal a grasa", self.kcal_per_kg_spin)

        self.realization_spin = QDoubleSpinBox()
        self.realization_spin.setRange(0.1, 1.0)
        self.realization_spin.setDecimals(2)
        self.realization_spin.setSingleStep(0.05)
        layout.addRow("Factor de realización", self.realization_spin)

        note = QLabel(
            "«Neto» descuenta lo que el socio habría quemado en reposo de todos modos: la "
            "frase promete lo que dejó de quemar de más, no el gasto bruto.\n\n"
            "Las kcal y los kg no son la misma cifra dividida entre 7700. Las kcal sí se "
            "acumulan linealmente; los kg no, porque el cuerpo compensa (Hall et al., Lancet "
            "2011: 10 kcal/día ≈ 0.45 kg de cambio final, la mitad en ~1 año). Con la "
            "adaptación apagada se vuelve a la regla lineal de 1958, que sobreestima el "
            "cambio de peso a largo plazo alrededor del doble."
        )
        note.setObjectName("botHint")
        note.setWordWrap(True)
        layout.addRow(note)
        return box

    def _build_preview_group(self) -> QGroupBox:
        box = QGroupBox("Ejemplo con estos valores")
        layout = QVBoxLayout(box)
        self.preview_headline = QLabel("—")
        self.preview_headline.setWordWrap(True)
        self.preview_detail = QLabel("—")
        self.preview_detail.setObjectName("botHint")
        self.preview_detail.setWordWrap(True)
        layout.addWidget(self.preview_headline)
        layout.addWidget(self.preview_detail)
        return box

    # ------------------------------------------------------------ controller
    def _connect_controller(self) -> None:
        self.controller.settings_loaded.connect(self._apply_settings)
        self.controller.settings_saved.connect(self._on_saved)
        self.controller.error_occurred.connect(
            lambda msg: show_error(self, msg, title=_TITLE)
        )
        self.controller.loading_changed.connect(self._on_loading)

    def _on_loading(self, loading: bool) -> None:
        self.save_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)

    def _on_saved(self, settings: Optional[Dict[str, Any]]) -> None:
        self._apply_settings(settings)
        show_info(self, "Configuración guardada.", title=_TITLE)

    def _apply_settings(self, settings: Optional[Dict[str, Any]]) -> None:
        if not settings:
            return
        self._apply_config(settings.get("config") or {})
        self._apply_schedule(settings.get("schedule") or {})
        self._render_intensities(settings.get("class_types") or [])
        self._apply_preview(settings.get("preview"))

    def _apply_config(self, config: Dict[str, Any]) -> None:
        self.weight_spin.setValue(float(config.get("reference_weight_kg", 70)))
        self.horizon_spin.setValue(int(config.get("horizon_weeks", 12)))
        self.default_cadence_spin.setValue(float(config.get("default_sessions_per_week", 2.5)))
        self.min_bookings_spin.setValue(int(config.get("min_bookings_for_history", 4)))
        self.lookback_spin.setValue(int(config.get("cadence_lookback_days", 180)))
        self.net_check.setChecked(bool(config.get("net_of_resting", True)))
        self.default_met_spin.setValue(float(config.get("default_met", 6.0)))
        self.default_duration_spin.setValue(int(config.get("default_duration_min", 60)))
        self.default_open_days_spin.setValue(int(config.get("default_open_days_per_week", 5)))
        self.kcal_per_kg_spin.setValue(int(config.get("kcal_per_kg_fat", 7700)))
        self.adaptation_check.setChecked(bool(config.get("metabolic_adaptation", True)))
        self.half_life_spin.setValue(int(config.get("kg_half_life_days", 365)))
        self.kg_per_100_spin.setValue(float(config.get("kg_per_100_kcal_per_day", 4.5)))
        self.realization_spin.setValue(float(config.get("realization_factor", 1.0)))
        self._on_adaptation_toggled(self.adaptation_check.isChecked())

    def _apply_schedule(self, schedule: Dict[str, Any]) -> None:
        days = schedule.get("open_weekdays") or []
        per_week = int(schedule.get("open_days_per_week") or 0)
        self.schedule_days_label.setText(
            f"{per_week} por semana — {_weekday_summary(days)}"
        )
        duration = schedule.get("mean_duration_min")
        self.schedule_duration_label.setText(
            f"{int(duration)} min" if duration else "sin horario cargado"
        )
        self.schedule_templates_label.setText(str(schedule.get("active_templates") or 0))

    def _render_intensities(self, class_types: List[Dict[str, Any]]) -> None:
        self._class_types = list(class_types)
        self._loading_table = True
        try:
            self.intensity_table.setRowCount(len(self._class_types))
            for row, item in enumerate(self._class_types):
                name = QTableWidgetItem(item.get("name") or item.get("code") or "")
                name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.intensity_table.setItem(row, 0, name)

                met_value = item.get("met_value")
                own = QTableWidgetItem("" if met_value is None else f"{float(met_value):.1f}")
                own.setToolTip("Vacío = usa el valor por defecto de la actividad.")
                self.intensity_table.setItem(row, 1, own)

                effective = float(item.get("effective_met") or 0)
                suffix = " (por defecto)" if item.get("is_default") else ""
                in_use = QTableWidgetItem(f"{effective:.1f}{suffix}")
                in_use.setFlags(in_use.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.intensity_table.setItem(row, 2, in_use)
        finally:
            self._loading_table = False

    def _apply_preview(self, preview: Optional[Dict[str, Any]]) -> None:
        if not preview:
            self.preview_headline.setText("—")
            self.preview_detail.setText("")
            return
        self.preview_headline.setText(
            f"Un socio ausente {preview['days_inactive']} días recibiría: "
            f"{preview['kcal_text']} kcal ≈ {preview['kg_fat_text']} kg de grasa "
            f"({preview['window_label']})."
        )
        detail = (
            f"{preview['sessions_missed']:.0f} clases perdidas "
            f"({preview['sessions_per_week']:.1f}/semana × {preview['weeks_counted']:.0f} "
            f"semanas) × {preview['kcal_per_session']:.0f} kcal por clase "
            f"({preview['met']:.1f} MET, {preview['duration_min']} min)."
        )
        steady = preview.get("kg_steady_state") or 0
        if steady > 0:
            # Sin el techo, la cifra de kg se lee como si creciera para siempre.
            detail += (
                f"\nEquivale a {preview['kcal_per_day']:.0f} kcal/día que dejó de gastar; "
                f"aunque no vuelva nunca, el peso tiende a {steady:.1f} kg y no pasa de ahí."
            )
        if preview.get("horizon_reached"):
            detail += (
                "\n⚠ El tope de la ventana está mordiendo: todos los socios más antiguos que "
                "esto reciben el mismo número. Súbelo si quieres que siga diferenciando."
            )
        self.preview_detail.setText(detail)

    def _on_adaptation_toggled(self, enabled: bool) -> None:
        """Los dos modelos usan parámetros distintos; mostrar los dos habilitados sugiere que
        ambos cuentan, y sólo cuenta uno."""
        self.half_life_spin.setEnabled(enabled)
        self.kg_per_100_spin.setEnabled(enabled)
        self.kcal_per_kg_spin.setEnabled(not enabled)

    # ---------------------------------------------------------------- actions
    def _save_config(self) -> None:
        self.controller.save_config(
            {
                "reference_weight_kg": self.weight_spin.value(),
                "horizon_weeks": self.horizon_spin.value(),
                "default_sessions_per_week": self.default_cadence_spin.value(),
                "min_bookings_for_history": self.min_bookings_spin.value(),
                "cadence_lookback_days": self.lookback_spin.value(),
                "default_met": self.default_met_spin.value(),
                "default_duration_min": self.default_duration_spin.value(),
                "default_open_days_per_week": self.default_open_days_spin.value(),
                "net_of_resting": self.net_check.isChecked(),
                "kcal_per_kg_fat": self.kcal_per_kg_spin.value(),
                "metabolic_adaptation": self.adaptation_check.isChecked(),
                "kg_half_life_days": self.half_life_spin.value(),
                "kg_per_100_kcal_per_day": self.kg_per_100_spin.value(),
                "realization_factor": self.realization_spin.value(),
            }
        )

    def _on_met_cell_changed(self, row: int, column: int) -> None:
        if self._loading_table or column != 1:
            return
        if row >= len(self._class_types):
            return
        class_type_id = self._class_types[row].get("id")
        if class_type_id is None:
            return

        item = self.intensity_table.item(row, column)
        raw = (item.text() if item else "").strip().replace(",", ".")
        if not raw:
            # An empty cell is a real instruction: clear the override and go back to the
            # activity's default. That is why the column is nullable rather than backfilled.
            self.controller.set_class_type_met(int(class_type_id), None)
            return
        try:
            value = float(raw)
        except ValueError:
            show_error(self, f"«{raw}» no es un número válido de MET.", title=_TITLE)
            self._render_intensities(self._class_types)
            return
        self.controller.set_class_type_met(int(class_type_id), value)
