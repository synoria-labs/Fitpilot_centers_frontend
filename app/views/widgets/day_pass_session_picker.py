"""Select an actual class, never a recurring template, for a single-class pass."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QLabel, QDateEdit

from ...services.classes_service import ClassesService
from ...threads.authenticated_operations import start_authenticated_operation

STUDIO_ZONE = ZoneInfo("America/Mexico_City")


def is_day_pass(plan):
    return bool(plan and plan.duration_unit == "day" and plan.duration_value == 1)


class DayPassSessionPicker(QWidget):
    def __init__(self, client, date_edit=None, parent=None):
        super().__init__(parent)
        self._service = ClassesService(client)
        self._request = 0
        self._operations = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.date_edit = date_edit or QDateEdit()
        if date_edit is None:
            self.date_edit.setCalendarPopup(True)
            self.date_edit.setDate(QDate.currentDate())
            self.date_edit.setMinimumDate(QDate.currentDate())
            layout.addWidget(self.date_edit)
        self.combo = QComboBox()
        self.hint = QLabel("El pase vence al terminar la clase seleccionada.")
        self.hint.setWordWrap(True)
        layout.addWidget(QLabel("Clase para el pase diario"))
        layout.addWidget(self.combo)
        layout.addWidget(self.hint)
        self.date_edit.dateChanged.connect(self.reload)

    def reload(self, *_):
        if not self.isEnabled():
            return
        self._request += 1
        request = self._request
        selected = self.date_edit.date().toPython()
        start = datetime.combine(selected, time.min, tzinfo=STUDIO_ZONE)
        self.combo.clear()
        self.combo.addItem("Cargando clases…", None)
        self.combo.setEnabled(False)

        def loaded(rows):
            if request != self._request:
                return
            self.combo.clear()
            self.combo.addItem("Selecciona una clase", None)
            for row in rows or []:
                stamp = datetime.fromisoformat(row["startAt"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(row["endAt"].replace("Z", "+00:00"))
                if stamp <= datetime.now(timezone.utc) or stamp.astimezone(STUDIO_ZONE).date() != selected or row.get("availableSpots", 0) <= 0:
                    continue
                self.combo.addItem(
                    f"{row.get('name') or 'Clase'} · {stamp.astimezone(STUDIO_ZONE):%d/%m/%Y %H:%M}"
                    f"–{end.astimezone(STUDIO_ZONE):%H:%M} · {row.get('venueName') or ''}", row,
                )
            self.combo.setEnabled(self.combo.count() > 1)
            self.hint.setText("El pase vence al terminar la clase seleccionada." if self.combo.count() > 1 else "No hay clases con cupo para esa fecha.")

        def failed(_error):
            if request == self._request:
                self.combo.clear()
                self.combo.setEnabled(False)
                self.hint.setText("No se pudieron cargar las clases. Cambia la fecha para reintentar.")

        operation = start_authenticated_operation(
            self._service, "get_available_sessions", parent=self,
            on_success=loaded, on_error=failed,
            start_date=max(start, datetime.now(timezone.utc)), end_date=start + timedelta(days=1),
        )
        self._operations.append(operation)

    def session_id(self):
        row = self.combo.currentData()
        if not row:
            return None
        stamp = datetime.fromisoformat(row["startAt"].replace("Z", "+00:00"))
        if stamp <= datetime.now(timezone.utc) or stamp.astimezone(STUDIO_ZONE).date() != self.date_edit.date().toPython():
            return None
        return int(row["id"])
