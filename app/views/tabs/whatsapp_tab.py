"""
Vista de la pestaña WhatsApp - Gestión de plantillas (Meta Cloud API).

Administra las plantillas almacenadas en ``app.whatsapp_templates`` con sincronización
bidireccional a Meta: crear/editar/eliminar llama a la Business Management API y refleja el
estado de aprobación. El editor es simplificado (cuerpo con placeholders {{1}}, {{2}}... +
valores de ejemplo + footer opcional); la app arma los ``components`` en el backend.
"""
import re
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QLineEdit, QGroupBox, QSplitter, QListWidget, QListWidgetItem, QComboBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ...core import container, get_logger
from ...controllers.whatsapp_controller import WhatsAppController
from ...utils.dialog_helpers import show_confirmation, show_error, show_info

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_CATEGORIES = ["UTILITY", "MARKETING", "AUTHENTICATION"]
_STATUS_COLORS = {
    "APPROVED": "#2ecc71",
    "PENDING": "#f39c12",
    "REJECTED": "#e74c3c",
}


def _parse_components(components: Optional[List[Any]]):
    """Extrae (body_text, body_examples, footer_text) de un array de components Meta."""
    body_text = ""
    body_examples: List[str] = []
    footer_text = ""
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        text = comp.get("text")
        if ctype == "BODY" and isinstance(text, str):
            body_text = text
            example = comp.get("example")
            if isinstance(example, dict):
                rows = example.get("body_text")
                if isinstance(rows, list) and rows and isinstance(rows[0], list):
                    body_examples = [str(v) for v in rows[0]]
        elif ctype == "FOOTER" and isinstance(text, str):
            footer_text = text
    return body_text, body_examples, footer_text


def _media_header_info(components: Optional[List[Any]]) -> tuple[Optional[str], str]:
    """Return (media_format, example_url) for IMAGE/VIDEO/DOCUMENT headers."""
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        media_format = str(comp.get("format") or "").upper()
        if ctype != "HEADER" or media_format not in {"IMAGE", "VIDEO", "DOCUMENT"}:
            continue
        example = comp.get("example")
        handles = example.get("header_handle") if isinstance(example, dict) else None
        if isinstance(handles, list) and handles:
            return media_format, str(handles[0] or "").strip()
        return media_format, ""
    return None, ""


class WhatsAppTab(QWidget):
    """Vista para gestión de plantillas de WhatsApp."""

    # Señales (compatibilidad / observabilidad externa)
    template_selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.current: Optional[Dict[str, Any]] = None  # plantilla seleccionada (None = nueva)
        self._templates: List[Dict[str, Any]] = []

        try:
            service = container.get("whatsapp_service")
        except Exception as exc:  # pragma: no cover - defensivo
            logger.error("No se pudo obtener whatsapp_service del contenedor: %s", exc)
            raise
        self.controller = WhatsAppController(service, self)

        self.setup_ui()
        self._connect_controller()
        self.controller.load_templates()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Gestión de Plantillas WhatsApp")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.sync_btn = QPushButton("🔄 Sincronizar")
        self.sync_btn.clicked.connect(self.on_sync)
        header_layout.addWidget(self.sync_btn)

        self.new_btn = QPushButton("+ Nueva Plantilla")
        self.new_btn.clicked.connect(self.on_new_template)
        header_layout.addWidget(self.new_btn)

        self.save_btn = QPushButton("💾 Guardar")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_template)
        header_layout.addWidget(self.save_btn)

        self.delete_btn = QPushButton("🗑️ Eliminar")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.on_delete_template)
        header_layout.addWidget(self.delete_btn)

        layout.addLayout(header_layout)

        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panel izquierdo - Lista
        left_panel = QGroupBox("Plantillas")
        left_layout = QVBoxLayout(left_panel)
        self.templates_list = QListWidget()
        self.templates_list.itemClicked.connect(self.on_template_selected)
        left_layout.addWidget(self.templates_list)
        splitter.addWidget(left_panel)

        # Panel derecho - Editor
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Información de plantilla
        info_group = QGroupBox("Información de Plantilla")
        info_layout = QVBoxLayout(info_group)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nombre:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: bienvenida_nuevo_socio")
        self.name_input.textChanged.connect(self.update_preview)
        name_layout.addWidget(self.name_input)
        info_layout.addLayout(name_layout)

        meta_layout = QHBoxLayout()
        meta_layout.addWidget(QLabel("Idioma:"))
        self.language_input = QLineEdit("es_MX")
        self.language_input.setMaximumWidth(100)
        meta_layout.addWidget(self.language_input)
        meta_layout.addWidget(QLabel("Categoría:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(_CATEGORIES)
        meta_layout.addWidget(self.category_combo)
        meta_layout.addWidget(QLabel("Estado:"))
        self.status_label = QLabel("No guardado")
        self.status_label.setStyleSheet("color: orange;")
        meta_layout.addWidget(self.status_label)
        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        right_layout.addWidget(info_group)

        # Contenido
        content_group = QGroupBox("Contenido de la Plantilla")
        content_layout = QVBoxLayout(content_group)

        vars_label = QLabel(
            "Usa marcadores posicionales: {{1}}, {{2}}, {{3}}... (deben coincidir con la "
            "plantilla aprobada en Meta)"
        )
        vars_label.setStyleSheet("color: #3498db; font-size: 11px;")
        vars_label.setWordWrap(True)
        content_layout.addWidget(vars_label)

        content_layout.addWidget(QLabel("Cuerpo (BODY):"))
        self.body_editor = QTextEdit()
        self.body_editor.setPlaceholderText(
            "Hola {{1}}! 👋\n\nBienvenido a FitPilot. Tu membresía {{2}} está activa.\n\n"
            "¡Nos vemos en el gym! 💪"
        )
        self.body_editor.textChanged.connect(self.update_preview)
        content_layout.addWidget(self.body_editor)

        examples_layout = QHBoxLayout()
        examples_layout.addWidget(QLabel("Valores de ejemplo:"))
        self.examples_input = QLineEdit()
        self.examples_input.setPlaceholderText("Para {{1}}, {{2}}... separados por |  →  Juan | Mensual Libre")
        self.examples_input.textChanged.connect(self.update_preview)
        examples_layout.addWidget(self.examples_input)
        content_layout.addLayout(examples_layout)

        footer_layout = QHBoxLayout()
        footer_layout.addWidget(QLabel("Footer (opcional):"))
        self.footer_input = QLineEdit()
        self.footer_input.setPlaceholderText("Ej: FitPilot")
        self.footer_input.textChanged.connect(self.update_preview)
        footer_layout.addWidget(self.footer_input)
        content_layout.addLayout(footer_layout)

        preview_label = QLabel("Vista Previa:")
        preview_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(preview_label)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(120)
        self.preview_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
        content_layout.addWidget(self.preview_text)

        right_layout.addWidget(content_group)

        # Enviar prueba
        test_group = QGroupBox("Enviar Prueba (envía la plantilla aprobada a un número)")
        test_layout = QVBoxLayout(test_group)
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("Teléfono:"))
        self.test_phone = QLineEdit()
        self.test_phone.setPlaceholderText("+52 XXX XXX XXXX")
        test_row.addWidget(self.test_phone)
        self.send_test_btn = QPushButton("📤 Enviar Prueba")
        self.send_test_btn.setEnabled(False)
        self.send_test_btn.clicked.connect(self.on_send_test)
        test_row.addWidget(self.send_test_btn)
        test_layout.addLayout(test_row)

        self.header_media_row = QWidget()
        header_media_layout = QHBoxLayout(self.header_media_row)
        header_media_layout.setContentsMargins(0, 0, 0, 0)
        self.header_media_label = QLabel("Media header:")
        self.header_media_input = QLineEdit()
        self.header_media_input.setPlaceholderText("URL pública de imagen/video/documento")
        header_media_layout.addWidget(self.header_media_label)
        header_media_layout.addWidget(self.header_media_input)
        self.header_media_row.setVisible(False)
        test_layout.addWidget(self.header_media_row)
        right_layout.addWidget(test_group)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter)

    def _connect_controller(self):
        self.controller.templates_loaded.connect(self._on_templates_loaded)
        self.controller.synced.connect(self._on_synced)
        self.controller.template_saved.connect(self._on_template_saved)
        self.controller.template_deleted.connect(self._on_template_deleted)
        self.controller.test_sent.connect(self._on_test_sent)
        self.controller.error_occurred.connect(self._on_error)
        self.controller.loading_changed.connect(self._on_loading_changed)

    # ------------------------------------------------------------------
    # Helpers de estado de plantilla
    # ------------------------------------------------------------------
    def _example_values(self) -> List[str]:
        raw = self.examples_input.text().strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("|")]

    def _set_status(self, status: Optional[str]):
        text = status or "No guardado"
        color = _STATUS_COLORS.get((status or "").upper(), "orange")
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def _set_identity_editable(self, editable: bool):
        """Nombre/idioma/categoría son inmutables en Meta tras crear."""
        self.name_input.setReadOnly(not editable)
        self.language_input.setReadOnly(not editable)
        self.category_combo.setEnabled(editable)

    def _populate_list(self, keep_id: Optional[int] = None):
        self.templates_list.clear()
        for tpl in self._templates:
            item = QListWidgetItem(tpl.get("template_name") or f"#{tpl.get('id')}")
            item.setData(Qt.ItemDataRole.UserRole, tpl.get("id"))
            status = (tpl.get("template_status") or "").upper()
            if status and status != "APPROVED":
                item.setText(f"{item.text()}  ({status})")
            self.templates_list.addItem(item)
            if keep_id is not None and tpl.get("id") == keep_id:
                self.templates_list.setCurrentItem(item)

    # ------------------------------------------------------------------
    # Acciones de usuario
    # ------------------------------------------------------------------
    def on_template_selected(self, item: QListWidgetItem):
        template_id = item.data(Qt.ItemDataRole.UserRole)
        tpl = next((t for t in self._templates if t.get("id") == template_id), None)
        if not tpl:
            return
        self.current = tpl
        body, examples, footer = _parse_components(tpl.get("components"))

        self.name_input.setText(tpl.get("template_name") or "")
        self.language_input.setText(tpl.get("template_language") or "")
        category = (tpl.get("category") or "").upper()
        if category in _CATEGORIES:
            self.category_combo.setCurrentText(category)
        self.body_editor.setPlainText(body)
        self.examples_input.setText(" | ".join(examples))
        self.footer_input.setText(footer)
        media_format, media_url = _media_header_info(tpl.get("components"))
        self.header_media_row.setVisible(bool(media_format))
        self.header_media_label.setText(f"{media_format or 'Media'} del header:")
        self.header_media_input.setText(media_url)
        self._set_status(tpl.get("template_status"))
        self._set_identity_editable(False)

        approved = (tpl.get("template_status") or "").upper() == "APPROVED"
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.send_test_btn.setEnabled(approved)
        self.update_preview()
        self.template_selected.emit(self.templates_list.currentRow())

    def on_new_template(self):
        self.current = None
        self.templates_list.clearSelection()
        self.name_input.clear()
        self.language_input.setText("es_MX")
        self.category_combo.setCurrentText("UTILITY")
        self.body_editor.clear()
        self.examples_input.clear()
        self.footer_input.clear()
        self.header_media_row.setVisible(False)
        self.header_media_input.clear()
        self.preview_text.clear()
        self._set_status("Nueva plantilla")
        self._set_identity_editable(True)
        self.name_input.setFocus()
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self.send_test_btn.setEnabled(False)

    def on_save_template(self):
        body = self.body_editor.toPlainText().strip()
        if not body:
            show_error(self, "El cuerpo de la plantilla es obligatorio.")
            return

        data = {
            "body_text": body,
            "body_examples": self._example_values(),
            "footer_text": self.footer_input.text().strip() or None,
        }

        if self.current is None:
            name = self.name_input.text().strip()
            if not name:
                show_error(self, "El nombre es obligatorio.")
                return
            data.update({
                "name": name,
                "language": self.language_input.text().strip() or "es_MX",
                "category": self.category_combo.currentText(),
            })
            self.controller.save_template(None, data)
        else:
            self.controller.save_template(self.current.get("id"), data)

    def on_delete_template(self):
        if not self.current:
            return
        name = self.current.get("template_name")
        if show_confirmation(
            self,
            f"¿Eliminar la plantilla '{name}' en Meta y localmente?",
            title="Confirmar Eliminación",
            ok_text="Sí",
            cancel_text="No",
        ):
            self.controller.delete_template(self.current.get("id"))

    def on_sync(self):
        self.controller.sync_templates()

    def on_send_test(self):
        if not self.current:
            show_error(self, "Selecciona una plantilla aprobada para enviar.")
            return
        phone = self.test_phone.text().strip()
        if not phone:
            show_error(self, "Ingresa un número de teléfono.")
            return
        header_media_url = None
        if self.header_media_row.isVisible():
            header_media_url = self.header_media_input.text().strip()
            if not header_media_url:
                show_error(self, "Esta plantilla requiere una URL de media para el header.")
                return
        self.controller.send_test(
            phone,
            self.current.get("id"),
            self._example_values(),
            header_media_url=header_media_url,
        )

    def update_preview(self):
        body = self.body_editor.toPlainText()
        values = self._example_values()

        def repl(match: "re.Match") -> str:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(values) and values[idx]:
                return values[idx]
            return match.group(0)

        preview = _PLACEHOLDER_RE.sub(repl, body)
        footer = self.footer_input.text().strip()
        if footer:
            preview = f"{preview}\n\n{footer}"
        self.preview_text.setPlainText(preview)

    # ------------------------------------------------------------------
    # Callbacks del controller
    # ------------------------------------------------------------------
    def _on_templates_loaded(self, templates: List[Dict[str, Any]]):
        self._templates = templates or []
        keep = self.current.get("id") if self.current else None
        self._populate_list(keep_id=keep)
        logger.info("Plantillas cargadas: %d", len(self._templates))

    def _on_synced(self, templates: List[Dict[str, Any]]):
        self._templates = templates or []
        self._populate_list()
        show_info(self, f"Sincronización completa: {len(self._templates)} plantillas.")

    def _on_template_saved(self, template: Optional[Dict[str, Any]], message: str):
        show_info(self, f"{message}. Meta revisará la plantilla (estado PENDING hasta aprobación).")
        self.current = template
        self.controller.load_templates()

    def _on_template_deleted(self, template_id: int):
        show_info(self, "Plantilla eliminada.")
        self.current = None
        self.on_new_template()
        self.controller.load_templates()

    def _on_test_sent(self, message: str):
        show_info(self, message)

    def _on_error(self, message: str):
        show_error(self, message)

    def _on_loading_changed(self, loading: bool):
        self.sync_btn.setEnabled(not loading)
        self.save_btn.setEnabled(not loading and (self.current is not None or self.name_input.text().strip() != ""))
