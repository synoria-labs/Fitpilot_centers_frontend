"""Efecto neon (halo) en hover/focus para los inputs de texto, a nivel de app.

Qt QSS no soporta ``box-shadow``, por lo que el glow real se consigue con un
``QGraphicsDropShadowEffect`` (offset 0 -> halo simetrico) que se aplica y se
quita mediante un ``eventFilter`` instalado una sola vez en la ``QApplication``.
Asi cubre todos los inputs actuales y futuros sin tocar cada call site.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QAbstractSpinBox,
    QComboBox,
)

from .tabs.whatsapp import theme

_INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
# Inputs borderless dentro de una "pill" -> el glow se aplica a la pill, no al input
# (glowear un input transparente brillaria el texto, no la barra). Ver ComposerWidget.
_SKIP_OBJECT_NAMES = {"composerInput"}

# Glow sutil, parecido al input del chat: blur corto y halo semi-transparente.
_BLUR_RADIUS = 12
_GLOW_ALPHA = 190


def make_neon_glow(widget) -> QGraphicsDropShadowEffect:
    """Crea el efecto de halo neon (mismas constantes que el glow global)."""
    glow = QGraphicsDropShadowEffect(widget)
    glow.setOffset(0, 0)
    glow.setBlurRadius(_BLUR_RADIUS)
    color = QColor(theme.ACCENT)
    color.setAlpha(_GLOW_ALPHA)
    glow.setColor(color)
    return glow


def _ancestor_has_effect(widget) -> bool:
    """True si algun ancestro ya tiene un QGraphicsEffect."""
    parent = widget.parentWidget()
    while parent is not None:
        if parent.graphicsEffect() is not None:
            return True
        parent = parent.parentWidget()
    return False


def set_neon_glow(widget, on: bool) -> None:
    """Activa/desactiva el halo neon en cualquier widget (input o contenedor)."""
    effect = widget.graphicsEffect()
    if on:
        if isinstance(effect, QGraphicsDropShadowEffect):
            return
        # Qt no soporta QGraphicsEffect anidados: si un ancestro ya tiene un effect
        # (p.ej. la opacidad del side card de Socios/Suscripciones, o el fade de
        # pagina), montar un glow encima corrompe el pintado -> "QPainter: Painter
        # not active" / "paint device painted by one painter at a time". Se omite.
        if _ancestor_has_effect(widget):
            return
        widget.setGraphicsEffect(make_neon_glow(widget))
    elif isinstance(effect, QGraphicsDropShadowEffect):
        widget.setGraphicsEffect(None)


class NeonInputGlow(QObject):
    """Aplica un halo neon azul a los inputs de texto en hover/focus, app-wide."""

    def _is_target(self, widget) -> bool:
        if not isinstance(widget, _INPUT_TYPES) or not widget.isEnabled():
            return False
        if widget.objectName() in _SKIP_OBJECT_NAMES:
            return False
        if isinstance(widget.parent(), QComboBox):  # QLineEdit interno de un combo
            return False
        return True

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        event_type = event.type()
        if event_type in (QEvent.Type.Enter, QEvent.Type.FocusIn):
            if self._is_target(obj):
                set_neon_glow(obj, True)
        elif event_type == QEvent.Type.Leave:
            if self._is_target(obj):
                set_neon_glow(obj, obj.hasFocus())  # mantener si sigue enfocado
        elif event_type == QEvent.Type.FocusOut:
            if self._is_target(obj):
                set_neon_glow(obj, obj.underMouse())  # mantener si el mouse sigue encima
        return False


def install_neon_input_glow(app) -> NeonInputGlow:
    """Instala el filtro de glow en la QApplication y devuelve la instancia.

    El llamador debe conservar la referencia para que el GC no la elimine.
    """
    glow_filter = NeonInputGlow(app)
    app.installEventFilter(glow_filter)
    return glow_filter
