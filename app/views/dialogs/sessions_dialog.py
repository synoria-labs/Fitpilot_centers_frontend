"""
Diálogo para gestionar sesiones activas del usuario.
"""
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ...core.logging import get_logger
from ...core.di import container
from ...threads.authenticated_operations import AuthenticatedOperation, start_authenticated_operation
from ...utils.dialog_helpers import show_confirmation, show_info, show_warning
from ..table_widget_helpers import configure_table_widget

logger = get_logger(__name__)


class SessionsDialog(QDialog):
    """Diálogo para visualizar y gestionar sesiones activas."""

    sessions_loaded = Signal(list)
    session_revoked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions_service = container.get('sessions_service')
        self.sessions: List[Dict[str, Any]] = []
        self._load_op: Optional[AuthenticatedOperation] = None
        self._revoke_ops: Dict[str, AuthenticatedOperation] = {}
        self._setup_ui()
        self._load_sessions()

    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Sesiones Activas")
        self.setMinimumSize(800, 500)

        layout = QVBoxLayout(self)

        # Título
        title = QLabel("Administrar Sesiones Activas")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Descripción
        description = QLabel(
            "Estas son todas las sesiones activas de tu cuenta. "
            "Puedes revocar cualquier sesión sospechosa."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Tabla de sesiones
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels([
            "Dispositivo", "IP", "Última Actividad", "Creado", "Acciones"
        ])
        configure_table_widget(self.sessions_table)

        # Configurar tamaño de columnas
        header = self.sessions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Dispositivo
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # IP
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Última actividad
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Creado
        header.setSectionResizeMode(4, QHeaderView.Fixed)  # Acciones
        self.sessions_table.setColumnWidth(4, 100)

        layout.addWidget(self.sessions_table)

        # Botones inferiores
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_btn = QPushButton("Actualizar")
        refresh_btn.clicked.connect(self._load_sessions)
        button_layout.addWidget(refresh_btn)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Conectar señales
        self.sessions_loaded.connect(self._on_sessions_loaded)
        self.session_revoked.connect(self._on_session_revoked)

    def _load_sessions(self):
        """Carga las sesiones activas del usuario."""
        logger.info("Loading user sessions...")

        # Cancelar/limpiar operación previa
        if self._load_op:
            try:
                self._load_op.success.disconnect()
                self._load_op.error.disconnect()
            except Exception:
                pass
            self._load_op = None

        self._load_op = start_authenticated_operation(
            service=self.sessions_service,
            method_name="get_my_sessions",
            parent=self,
            on_success=self.sessions_loaded.emit,
            on_error=self._on_load_error,
        )

    def _on_sessions_loaded(self, sessions: List[Dict[str, Any]]):
        """Maneja las sesiones cargadas."""
        self.sessions = sessions
        self._populate_table()
        logger.info(f"Loaded {len(sessions)} sessions")

    def _on_load_error(self, error_msg: str):
        """Maneja errores al cargar sesiones."""
        logger.error(f"Failed to load sessions: {error_msg}")
        show_warning(
            self,
            f"No se pudieron cargar las sesiones: {error_msg}",
            title="Error"
        )

    def _populate_table(self):
        """Llena la tabla con los datos de sesiones."""
        self.sessions_table.setRowCount(len(self.sessions))

        for row, session in enumerate(self.sessions):
            # Columna 0: Dispositivo (con ícono)
            device_icon = self.sessions_service.get_device_icon(session["device_name"])
            device_text = f"{device_icon} {session['device_name']}"
            if session["is_current"]:
                device_text += " (Esta sesión)"

            device_item = QTableWidgetItem(device_text)
            if session["is_current"]:
                font = device_item.font()
                font.setBold(True)
                device_item.setFont(font)
            self.sessions_table.setItem(row, 0, device_item)

            # Columna 1: IP
            ip_item = QTableWidgetItem(session["ip_address"])
            self.sessions_table.setItem(row, 1, ip_item)

            # Columna 2: Última actividad
            last_active_str = self.sessions_service.format_last_active(session["last_active_at"])
            last_active_item = QTableWidgetItem(last_active_str)
            self.sessions_table.setItem(row, 2, last_active_item)

            # Columna 3: Creado
            created_str = session["created_at"].strftime("%d/%m/%Y %H:%M") if session["created_at"] else "N/A"
            created_item = QTableWidgetItem(created_str)
            self.sessions_table.setItem(row, 3, created_item)

            # Columna 4: Acciones (botón revocar)
            if not session["is_current"]:
                revoke_btn = QPushButton("Revocar")
                revoke_btn.setProperty("session_id", session["session_id"])
                revoke_btn.clicked.connect(lambda checked, sid=session["session_id"]: self._revoke_session(sid))
                self.sessions_table.setCellWidget(row, 4, revoke_btn)
            else:
                # No permitir revocar la sesión actual
                label = QLabel("Activa")
                label.setAlignment(Qt.AlignCenter)
                self.sessions_table.setCellWidget(row, 4, label)

    def _revoke_session(self, session_id: str):
        """Revoca una sesión específica."""
        # Confirmar acción
        if show_confirmation(
            self,
            "¿Estás seguro de que deseas revocar esta sesión?",
            title="Confirmar",
            ok_text="Sí",
            cancel_text="No",
        ):
            logger.info(f"Revoking session {session_id[:8]}...")

            op = start_authenticated_operation(
                service=self.sessions_service,
                method_name="revoke_session",
                parent=self,
                on_success=lambda success: self._on_revoke_result(session_id, success),
                on_error=lambda err: self._on_revoke_error(session_id, err),
                on_finished=lambda: self._revoke_ops.pop(session_id, None),
                session_id=session_id,
            )
            self._revoke_ops[session_id] = op

    def _on_revoke_result(self, session_id: str, success: bool):
        """Maneja el resultado de revocar una sesión."""
        if success:
            show_info(self, "Sesión revocada correctamente.", title="Éxito")
            self.session_revoked.emit(session_id)
            self._load_sessions()  # Recargar sesiones
        else:
            show_warning(self, "No se pudo revocar la sesión.", title="Error")

    def _on_revoke_error(self, session_id: str, error_msg: str):
        """Maneja errores al revocar una sesión."""
        logger.error(f"Failed to revoke session {session_id[:8]}: {error_msg}")
        show_warning(
            self,
            f"Error al revocar la sesión: {error_msg}",
            title="Error"
        )

    def _on_session_revoked(self, session_id: str):
        """Callback cuando una sesión es revocada."""
        logger.info(f"Session {session_id[:8]} has been revoked")
