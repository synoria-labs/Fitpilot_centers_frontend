"""
ClassesTab - Vista rediseñada de clases con vista semanal por tipo de clase
"""
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List
from collections import defaultdict
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
)

from ...core import container, get_logger
from ...threads.authenticated_operations import AuthenticatedOperation, start_authenticated_operation
from ...utils.datetime_helpers import parse_iso_datetime
from ...models.base import ClassTemplate
from ..widgets.week_selector import WeekSelector
from ..widgets.class_type_filter import ClassTypeFilter
from ..widgets.weekly_class_grid import WeeklyClassGrid


logger = get_logger(__name__)


@dataclass
class ScheduleGroup:
    key: str
    name: str
    start_time_local: str
    template_ids: List[int] = field(default_factory=list)


class ClassesTab(QWidget):
    """
    Vista para gestión de clases con visualización semanal.

    Features:
    - Vista semanal (7 días)
    - Filtro por tipo de clase
    - Selector de horario cuando hay múltiples sesiones
    - Grid dinámico con íconos según tipo de clase
    """

    def __init__(self) -> None:
        super().__init__()

        logger.info("ClassesTab initializing...")

        # Get services from container
        try:
            self._classes_service = container.get("classes_service")
            self._standing_bookings_service = container.get("standing_bookings_service")
            logger.info(f"Services loaded: classes={self._classes_service is not None}, standing_bookings={self._standing_bookings_service is not None}")
        except Exception as e:
            self._classes_service = None
            self._standing_bookings_service = None
            logger.error(f"Services not available in container: {e}")

        # State
        self._current_week_start: Optional[date] = None
        self._current_week_end: Optional[date] = None
        self._current_class_type_id: Optional[int] = None
        self._current_class_type_code: str = 'spinning'
        self._loading = False
        self._current_op: Optional[AuthenticatedOperation] = None
        self._class_types_op: Optional[AuthenticatedOperation] = None  # Keep ref to prevent GC
        self._templates_op: Optional[AuthenticatedOperation] = None  # Keep ref to prevent GC

        # Session data organized by day
        self._sessions_by_day: Dict[date, List[Dict]] = defaultdict(list)
        # Selected session for each day (when multiple exist)
        self._selected_sessions: Dict[date, Dict] = {}
        self._selected_day: Optional[date] = None
        self._templates: List[ClassTemplate] = []
        self._schedule_groups: List[ScheduleGroup] = []
        self._current_schedule: Optional[ScheduleGroup] = None

        # Build UI
        self._build_ui()
        logger.info("ClassesTab UI built")

        # Load initial data
        logger.info("ClassesTab calling _load_class_types()...")
        self._load_class_types()
        logger.info("ClassesTab initialization complete")

    def _build_ui(self) -> None:
        """Build the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top controls row
        controls_layout = QHBoxLayout()

        # Week selector
        self.week_selector = WeekSelector()
        self.week_selector.week_changed.connect(self._on_week_changed)
        controls_layout.addWidget(self.week_selector)

        controls_layout.addStretch()

        # Class type filter
        self.class_type_filter = ClassTypeFilter()
        self.class_type_filter.class_type_changed.connect(self._on_class_type_changed)
        controls_layout.addWidget(self.class_type_filter)

        # Fixed schedule filter
        self.template_filter = self._build_template_filter()
        controls_layout.addWidget(self.template_filter)

        layout.addLayout(controls_layout)

        # Weekly grid
        self.weekly_grid = WeeklyClassGrid()
        self.weekly_grid.day_selected.connect(self._on_day_selected)
        layout.addWidget(self.weekly_grid, 1)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _build_template_filter(self) -> QWidget:
        """Build fixed schedule selector widget."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        label = QLabel("Horario:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(240)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        layout.addWidget(self.template_combo)

        layout.addStretch()
        return widget

    def _load_class_types(self):
        """Load available class types from the backend"""
        logger.info("_load_class_types called")

        if not self._standing_bookings_service:
            logger.error("StandingBookingsService not available")
            self.status_label.setText("Error: Servicio no disponible")
            return

        logger.info("Creating AuthenticatedOperation for get_class_types")

        # Create async operation and store reference to prevent garbage collection
        self._class_types_op = start_authenticated_operation(
            service=self._standing_bookings_service,
            method_name="get_class_types",
            parent=self,
            on_success=self._on_class_types_loaded,
            on_error=self._on_class_types_error,
        )
        logger.info("AuthenticatedOperation execution started")

    def _load_class_templates(self) -> None:
        """Load available class templates for fixed schedules."""
        logger.info("_load_class_templates called")

        if not self._standing_bookings_service:
            logger.error("StandingBookingsService not available for templates")
            return

        self._templates_op = start_authenticated_operation(
            service=self._standing_bookings_service,
            method_name="get_class_templates",
            parent=self,
            on_success=self._on_class_templates_loaded,
            on_error=self._on_class_templates_error,
        )

    @Slot(object)
    def _on_class_types_loaded(self, class_types: List):
        """Handle successful class types loading"""
        logger.info(f"_on_class_types_loaded called with data type: {type(class_types)}")
        logger.info(f"Loaded {len(class_types) if isinstance(class_types, list) else 'N/A'} class types")

        # Convert ClassType objects to dictionaries
        class_types_dicts = []
        for ct in class_types:
            # Check if it's an object with attributes or already a dict
            if hasattr(ct, 'id'):
                class_types_dicts.append({
                    'id': ct.id,
                    'code': ct.code,
                    'name': ct.name,
                    'description': getattr(ct, 'description', None)
                })
            else:
                # Already a dict
                class_types_dicts.append(ct)

        logger.info(f"Converted class types: {class_types_dicts}")

        # Populate filter
        logger.info("Populating class type filter...")
        self.class_type_filter.populate_class_types(class_types_dicts, default_code='spinning')
        logger.info("Class type filter populated")

        # Get initial selection
        logger.info("Getting selected class type...")
        selected = self.class_type_filter.get_selected_class_type()
        logger.info(f"Selected class type: {selected}")

        if selected:
            self._current_class_type_id = selected['id']
            self._current_class_type_code = selected['code']
            logger.info(f"Class type set: ID={self._current_class_type_id}, Code={self._current_class_type_code}")

            # Load initial week
            week_start, week_end = self.week_selector.get_current_week()
            self._current_week_start = week_start
            self._current_week_end = week_end
            logger.info(f"Week range: {week_start} to {week_end}")
            self._load_class_templates()
        else:
            logger.warning("No class type selected!")

    @Slot(str)
    def _on_class_types_error(self, error: str):
        """Handle class types loading error"""
        logger.error(f"Error loading class types: {error}")
        self.status_label.setText(f"Error cargando tipos de clase: {error}")

    @Slot(date, date)
    def _on_week_changed(self, start_date: date, end_date: date):
        """Handle week selection change"""
        logger.info(f"Week changed: {start_date} to {end_date}")
        self._current_week_start = start_date
        self._current_week_end = end_date
        self._load_week_sessions()

    @Slot(int, str, str)
    def _on_class_type_changed(self, class_type_id: int, code: str, name: str):
        """Handle class type selection change"""
        logger.info(f"Class type changed: {name} (id={class_type_id}, code={code})")
        self._current_class_type_id = class_type_id
        self._current_class_type_code = code
        self._refresh_template_filter()
        if self._current_schedule is not None:
            self._load_week_sessions()

    @Slot(object)
    def _on_class_templates_loaded(self, templates: List[ClassTemplate]) -> None:
        """Handle class template load for fixed schedule selection."""
        if not templates:
            self._templates = []
            self._refresh_template_filter()
            return

        self._templates = [t for t in templates if getattr(t, "is_active", True)]
        self._refresh_template_filter()
        if self._current_schedule is not None:
            self._load_week_sessions()

    @Slot(str)
    def _on_class_templates_error(self, error: str) -> None:
        logger.error(f"Error loading class templates: {error}")

    @Slot(int)
    def _on_template_changed(self, index: int) -> None:
        """Handle fixed schedule selection change."""
        data = self.template_combo.itemData(index)
        if isinstance(data, ScheduleGroup):
            self._current_schedule = data
            self._load_week_sessions()
        else:
            self._current_schedule = None
            self.status_label.setText("Selecciona un horario")
            self.weekly_grid.show_error("Selecciona un horario")

    def _refresh_template_filter(self) -> None:
        """Refresh fixed schedule list based on current class type."""
        selected_key = self._current_schedule.key if self._current_schedule else None
        self.template_combo.blockSignals(True)
        self.template_combo.clear()

        filtered = self._templates
        if self._current_class_type_id:
            filtered = [t for t in self._templates if t.class_type_id == self._current_class_type_id]

        self._schedule_groups = self._build_schedule_groups(filtered)

        if not self._schedule_groups:
            self._current_schedule = None
            self.template_combo.setEnabled(False)
            self.template_combo.blockSignals(False)
            return

        selected_index = 0
        for group in self._schedule_groups:
            label = self._format_schedule_label(group)
            self.template_combo.addItem(label, group)
            if selected_key is not None and group.key == selected_key:
                selected_index = self.template_combo.count() - 1

        self.template_combo.setCurrentIndex(selected_index)
        data = self.template_combo.currentData()
        self._current_schedule = data if isinstance(data, ScheduleGroup) else None
        self.template_combo.setEnabled(True)
        self.template_combo.blockSignals(False)

    def _format_schedule_label(self, group: ScheduleGroup) -> str:
        """Return combo label for a schedule group (name + start time)."""
        if group.start_time_local:
            return f"{group.name} - {group.start_time_local}"
        return group.name

    def _build_schedule_groups(self, templates: List[ClassTemplate]) -> List[ScheduleGroup]:
        """Group templates by name and start time to cover Monday-Sunday schedules."""
        groups: Dict[str, ScheduleGroup] = {}
        for template in templates:
            name = (template.name or template.class_type_name or "Clase").strip()
            start_time = str(template.start_time_local or "").strip()
            venue_id = getattr(template, "venue_id", None)
            key = f"{name}|{start_time}|{venue_id}"
            group = groups.get(key)
            if group is None:
                group = ScheduleGroup(key=key, name=name, start_time_local=start_time)
                groups[key] = group
            if template.id not in group.template_ids:
                group.template_ids.append(int(template.id))

        result = list(groups.values())
        result.sort(key=lambda g: (g.start_time_local, g.name, g.key))
        return result

    @Slot(object)
    def _on_day_selected(self, day_date: date):
        """Handle day selection from the weekly grid."""
        if not day_date:
            return
        self._selected_day = day_date
        self.weekly_grid.set_selected_date(day_date)

    def _load_week_sessions(self):
        """Load sessions for the current week and class type"""
        logger.info(f"_load_week_sessions called - start={self._current_week_start}, end={self._current_week_end}, class_type_id={self._current_class_type_id}")

        if not self._classes_service:
            logger.error("ClassesService not available")
            self.status_label.setText("Error: Servicio no disponible")
            return

        if self._loading:
            logger.debug("Already loading, skipping duplicate request")
            return

        if not self._current_week_start or not self._current_week_end or not self._current_class_type_id:
            logger.warning(f"Week or class type not set yet - start={self._current_week_start}, end={self._current_week_end}, type_id={self._current_class_type_id}")
            return

        if self._current_schedule is None:
            logger.warning("Schedule not selected yet")
            self.status_label.setText("Selecciona un horario")
            self.weekly_grid.show_error("Selecciona un horario")
            return

        logger.info("Starting to load week sessions...")
        self._loading = True
        self.status_label.setText("Cargando sesiones...")
        self.weekly_grid.show_loading()
        logger.info("Loading state set, grid showing loading")

        # Create async operation
        logger.info("Creating AuthenticatedOperation for get_week_sessions_with_seats")
        self._current_op = start_authenticated_operation(
            service=self._classes_service,
            method_name="get_week_sessions_with_seats",
            parent=self,
            on_success=self._on_sessions_loaded,
            on_error=self._on_sessions_error,
            on_finished=lambda: setattr(self, '_loading', False),
            start_date=self._current_week_start,
            end_date=self._current_week_end,
            class_type_id=self._current_class_type_id,
            venue_id=None  # TODO: Add venue filter if needed
        )

        logger.info("Executing sessions operation...")
        logger.info("Sessions operation started")

    @Slot(object)
    def _on_sessions_loaded(self, sessions: List[Dict]):
        """Handle successful sessions loading"""
        logger.info(f"_on_sessions_loaded called with data type: {type(sessions)}")
        logger.info(f"Loaded {len(sessions) if isinstance(sessions, list) else 'N/A'} sessions")
        if sessions and len(sessions) > 0:
            logger.info(f"First session sample: {sessions[0]}")

        # Group sessions by date
        logger.info("Grouping sessions by date...")
        self._sessions_by_day = defaultdict(list)
        self._selected_sessions = {}

        template_ids = set(self._current_schedule.template_ids) if self._current_schedule else set()
        for session in sessions:
            template_id_raw = session.get('templateId') or session.get('template_id')
            template_id = int(template_id_raw) if template_id_raw is not None else None
            if template_ids and template_id not in template_ids:
                continue

            # Parse start_at to get the date
            start_at_raw = session.get('startAt')
            start_at = parse_iso_datetime(start_at_raw) if isinstance(start_at_raw, str) else start_at_raw
            if isinstance(start_at, datetime):
                session_date = start_at.date()
            else:
                logger.warning(f"Unknown startAt format: {start_at_raw}")
                continue

            # Convert to expected format
            end_at_raw = session.get('endAt')
            end_at = parse_iso_datetime(end_at_raw) if isinstance(end_at_raw, str) else end_at_raw
            session_data = {
                'id': session.get('id'),
                'name': session.get('name'),
                'start_at': start_at,
                'end_at': end_at,
                'capacity': session.get('capacity'),
                'seats': session.get('seats', []),
                'instructor_name': session.get('instructorName'),
                'template_id': template_id
            }

            self._sessions_by_day[session_date].append(session_data)

        # For each day, select the first session by default
        for day_date, day_sessions in self._sessions_by_day.items():
            if day_sessions:
                # Sort by start time
                day_sessions.sort(key=lambda s: s['start_at'])
                self._selected_sessions[day_date] = day_sessions[0]

        # Choose a default selected day (today if in range, otherwise first day with sessions)
        if self._current_week_start:
            week_dates = [self._current_week_start + timedelta(days=i) for i in range(7)]
            today = date.today()
            if today in week_dates:
                self._selected_day = today
            else:
                self._selected_day = None

        if not self._selected_day:
            for day_date in sorted(self._sessions_by_day.keys()):
                if self._sessions_by_day[day_date]:
                    self._selected_day = day_date
                    break

        self.weekly_grid.set_selected_date(self._selected_day)

        # Refresh the grid
        self._refresh_grid()

        filtered_total = sum(len(day_sessions) for day_sessions in self._sessions_by_day.values())
        self.status_label.setText(f"Cargadas {filtered_total} sesiones")

    @Slot(str)
    def _on_sessions_error(self, error: str):
        """Handle sessions loading error"""
        logger.error(f"Error loading sessions: {error}")
        self.status_label.setText(f"Error: {error}")
        self.weekly_grid.show_error(f"Error: {error}")

    def _refresh_grid(self):
        """Refresh the weekly grid with selected sessions"""
        if not self._current_week_start:
            return

        # Prepare data for grid: map each date to its selected session
        grid_data = {}
        for i in range(7):
            day_date = self._current_week_start + timedelta(days=i)
            if day_date in self._selected_sessions:
                grid_data[day_date] = self._selected_sessions[day_date]

        # Update grid
        self.weekly_grid.populate_grid(
            week_start=self._current_week_start,
            sessions_by_day=grid_data,
            class_type_code=self._current_class_type_code
        )


# For testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    window = ClassesTab()
    window.setWindowTitle("ClassesTab Test")
    window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())
