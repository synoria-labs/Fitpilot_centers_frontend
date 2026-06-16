"""Barra lateral de navegación moderna (estilo Discord/Slack/Teams/WhatsApp-Desktop).

Reemplaza la navegación por pestañas. Reutiliza los tokens de diseño de la pantalla de Chat
(`app/views/tabs/whatsapp/theme.py`) e iconos Material Design (`mdi6`) vía QtAwesome — sin
dependencias nuevas. Pensada para escalar: soporta estado expandido/colapsado, tooltips, badges
de notificación y (modelo listo) submenús futuros.

Contrato con el resto de la app:
- `Sidebar.add_item(SidebarItem)` registra un ítem (conserva el concepto `tab_id`).
- `Sidebar.item_selected = Signal(str)` emite el `tab_id` al seleccionar.
- `set_active / set_enabled / set_badge / set_collapsed` permiten sincronizar desde el controller.
- El footer expone `user_label`, `session_label` (clicable) y `logout_button` para que
  `MainWindow` los pueble/conecte igual que hacía con el antiguo header.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QScrollArea, QToolButton,
    QPushButton,
)

from ..tabs.whatsapp import theme

EXPANDED_WIDTH = 240
COLLAPSED_WIDTH = 64
ICON_SIZE = 22
_DISABLED_ICON = "#4A555C"
_DISABLED_TEXT = "#5A656D"


@dataclass
class SidebarItem:
    """Modelo declarativo de un ítem de navegación (reemplaza las tuplas ``tab_configs``)."""

    tab_id: str                 # mismo concepto que hoy: "members", "whatsapp_chat", ...
    label: str
    icon: str                   # nombre qtawesome, p. ej. "mdi6.account-group"
    is_public: bool = True      # rol: False = solo admin
    section: str = "main"       # agrupación visual futura
    badge: int = 0              # contador (0 = oculto)
    children: list = field(default_factory=list)  # submenús futuros (vacío en MVP)


class ClickableLabel(QLabel):
    """QLabel que emite ``clicked`` al pulsar (para el indicador de sesión del footer)."""

    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SidebarItemWidget(QFrame):
    """Un botón de navegación: [icono][label][badge] con estados hover/activo/deshabilitado."""

    clicked = Signal(str)  # tab_id

    def __init__(self, item: SidebarItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab_id = item.tab_id
        self._icon_name = item.icon
        self._active = False
        self._collapsed = False

        self.setObjectName("sidebarItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("active", "false")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 9, 12, 9)
        lay.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        lay.addWidget(self.icon_label)

        self.text_label = QLabel(item.label)
        self.text_label.setObjectName("sidebarItemLabel")
        font = QFont()
        font.setPixelSize(14)
        self.text_label.setFont(font)
        lay.addWidget(self.text_label, 1)

        self.badge_label = QLabel()
        self.badge_label.setObjectName("sidebarBadge")
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.hide()
        lay.addWidget(self.badge_label)

        self.setToolTip(item.label)
        self._refresh_visual()
        if item.badge:
            self.set_badge(item.badge)

    # ------------------------------------------------------------------
    def _apply_icon(self, color: str) -> None:
        try:
            self.icon_label.setPixmap(
                qta.icon(self._icon_name, color=color).pixmap(QSize(ICON_SIZE, ICON_SIZE))
            )
        except Exception:  # noqa: BLE001 - icono inexistente => fallback discreto
            self.icon_label.setText("•")

    def _refresh_visual(self) -> None:
        if not self.isEnabled():
            icon_color, text_color = _DISABLED_ICON, _DISABLED_TEXT
        elif self._active:
            icon_color, text_color = theme.ACCENT, theme.TEXT_PRIMARY
        else:
            icon_color, text_color = theme.TEXT_SECONDARY, theme.TEXT_PRIMARY
        self._apply_icon(icon_color)
        self.text_label.setStyleSheet(f"color: {text_color}; background: transparent;")

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self._refresh_visual()
        self.style().unpolish(self)
        self.style().polish(self)

    def set_badge(self, count: int) -> None:
        if count and count > 0:
            self.badge_label.setText(str(count) if count < 100 else "99+")
            self.badge_label.setVisible(not self._collapsed)
        else:
            self.badge_label.hide()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.text_label.setVisible(not collapsed)
        if collapsed:
            self.badge_label.hide()
            self.layout().setContentsMargins(0, 9, 0, 9)
            self.layout().setAlignment(Qt.AlignmentFlag.AlignHCenter)
        else:
            self.layout().setContentsMargins(13, 9, 12, 9)
            self.layout().setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 (Qt override)
        super().setEnabled(enabled)
        self._refresh_visual()

    def mousePressEvent(self, event):  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit(self.tab_id)
        super().mousePressEvent(event)


class Sidebar(QFrame):
    """Contenedor de la barra lateral: branding + lista de ítems + footer de usuario."""

    item_selected = Signal(str)     # tab_id
    collapse_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._items: Dict[str, SidebarItemWidget] = {}
        self._collapsed = False
        self._active_tab_id: Optional[str] = None
        self.setFixedWidth(EXPANDED_WIDTH)
        self.setStyleSheet(_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Branding
        self.brand = QWidget()
        self.brand.setObjectName("sidebarBrand")
        bl = QHBoxLayout(self.brand)
        bl.setContentsMargins(16, 16, 12, 16)
        bl.setSpacing(10)
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(28, 28)
        try:
            self.brand_icon.setPixmap(
                qta.icon("mdi6.dumbbell", color=theme.ACCENT).pixmap(QSize(26, 26))
            )
        except Exception:  # noqa: BLE001
            self.brand_icon.setText("🏋")
        bl.addWidget(self.brand_icon)
        self.brand_text = QLabel("FitPilot")
        self.brand_text.setObjectName("sidebarBrandText")
        brand_font = QFont()
        brand_font.setPixelSize(18)
        brand_font.setWeight(QFont.Weight.Bold)
        self.brand_text.setFont(brand_font)
        bl.addWidget(self.brand_text, 1)
        root.addWidget(self.brand)

        # --- Ítems (scroll)
        self.items_container = QWidget()
        self.items_container.setObjectName("sidebarItems")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(8, 8, 8, 8)
        self.items_layout.setSpacing(4)
        self.items_layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.items_container)
        root.addWidget(scroll, 1)

        # --- Footer: usuario + sesión + logout + colapsar
        self.footer = QWidget()
        self.footer.setObjectName("sidebarFooter")
        fl = QVBoxLayout(self.footer)
        fl.setContentsMargins(12, 10, 12, 12)
        fl.setSpacing(6)

        self.user_label = QLabel("Usuario")
        self.user_label.setObjectName("sidebarUser")
        self.user_label.setWordWrap(True)
        fl.addWidget(self.user_label)

        self.session_label = ClickableLabel("")
        self.session_label.setObjectName("sidebarSession")
        self.session_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.session_label.setToolTip("Click para ver todas las sesiones activas")
        fl.addWidget(self.session_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.logout_button = QPushButton("Cerrar sesión")
        self.logout_button.setObjectName("sidebarLogout")
        self.logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        actions.addWidget(self.logout_button, 1)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("sidebarCollapse")
        self.collapse_button.setIconSize(QSize(18, 18))
        self.collapse_button.setToolTip("Colapsar / expandir")
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_collapse_icon()
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        actions.addWidget(self.collapse_button, 0)
        fl.addLayout(actions)
        root.addWidget(self.footer)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def add_item(self, item: SidebarItem) -> SidebarItemWidget:
        widget = SidebarItemWidget(item, self)
        widget.clicked.connect(self._on_item_clicked)
        self._items[item.tab_id] = widget
        # insertar antes del stretch final
        self.items_layout.insertWidget(self.items_layout.count() - 1, widget)
        return widget

    def set_active(self, tab_id: Optional[str]) -> None:
        """Marca el ítem activo sin emitir señal (para sincronizar desde el controller)."""
        self._active_tab_id = tab_id
        for tid, widget in self._items.items():
            widget.set_active(tid == tab_id)

    def active_tab_id(self) -> Optional[str]:
        return self._active_tab_id

    def set_enabled(self, tab_id: str, enabled: bool) -> None:
        widget = self._items.get(tab_id)
        if widget is not None:
            widget.setEnabled(enabled)

    def set_badge(self, tab_id: str, count: int) -> None:
        widget = self._items.get(tab_id)
        if widget is not None:
            widget.set_badge(count)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.brand_text.setVisible(not collapsed)
        self.user_label.setVisible(not collapsed)
        self.session_label.setVisible(not collapsed)
        self.logout_button.setVisible(not collapsed)
        for widget in self._items.values():
            widget.set_collapsed(collapsed)
        self._set_collapse_icon()

        start = self.width()
        end = COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH
        group = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(self, prop, self)
            anim.setDuration(180)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(anim)
        group.finished.connect(lambda: self.setFixedWidth(end))
        self._collapse_anim = group  # referencia fuerte
        group.start()
        self.collapse_toggled.emit(collapsed)

    # ------------------------------------------------------------------
    def _on_item_clicked(self, tab_id: str) -> None:
        self.set_active(tab_id)
        self.item_selected.emit(tab_id)

    def _set_collapse_icon(self) -> None:
        name = "mdi6.chevron-double-right" if self._collapsed else "mdi6.chevron-double-left"
        try:
            self.collapse_button.setIcon(qta.icon(name, color=theme.TEXT_SECONDARY))
        except Exception:  # noqa: BLE001
            self.collapse_button.setText(">" if self._collapsed else "<")


def _style() -> str:
    return f"""
#sidebar {{
    background-color: {theme.BG_APP};
    border-right: 1px solid {theme.DIVIDER};
}}
#sidebarBrand {{ background-color: {theme.BG_APP}; }}
#sidebarBrandText {{ color: {theme.TEXT_PRIMARY}; background: transparent; }}
#sidebarItems {{ background-color: {theme.BG_APP}; }}
#sidebarScroll {{ background: transparent; border: none; }}
#sidebarItem {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
}}
#sidebarItem:hover {{ background-color: {theme.ITEM_HOVER}; }}
#sidebarItem[active="true"] {{
    background-color: {theme.ITEM_SELECTED};
    border-left: 3px solid {theme.ACCENT};
}}
#sidebarBadge {{
    background-color: {theme.ACCENT};
    color: #0b141a;
    border-radius: 9px;
    min-width: 18px;
    min-height: 18px;
    padding: 0 5px;
    font-size: 10px;
    font-weight: bold;
}}
#sidebarFooter {{
    background-color: {theme.BG_PANEL};
    border-top: 1px solid {theme.DIVIDER};
}}
#sidebarUser {{
    color: {theme.TEXT_PRIMARY};
    background: transparent;
    font-size: 12px;
    font-weight: 600;
}}
#sidebarSession {{ color: {theme.TEXT_SECONDARY}; background: transparent; font-size: 11px; }}
#sidebarLogout {{
    background-color: transparent;
    color: #E57373;
    border: 1px solid {theme.DIVIDER};
    border-radius: 8px;
    padding: 6px 10px;
    font-weight: 600;
}}
#sidebarLogout:hover {{ background-color: rgba(229, 115, 115, 0.14); }}
#sidebarCollapse {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
}}
#sidebarCollapse:hover {{ background-color: {theme.ITEM_HOVER}; }}
"""
