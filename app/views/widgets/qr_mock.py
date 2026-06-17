"""QR de *maqueta* (decorativo) para la pestaña de login por código.

Dibuja un código QR convincente con ``QPainter`` — tarjeta blanca, los 3
patrones localizadores y una rejilla de módulos **determinista** (no aleatoria
por render), con la marca FitPilot centrada (como Spotify centra su logo). NO es
un QR real escaneable: es solo visual mientras el flujo de device-authorization
queda diferido. Cuando exista el backend, ``LoginView.set_qr_pixmap`` reemplaza
este pixmap por uno real sin cambiar la UI.

Sin dependencias nuevas (no requiere el paquete ``qrcode``).
"""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor

from .brand_logo import logo_mark_pixmap

_MODULES = 25                 # rejilla NxN
_DARK = "#0E2A4A"             # navy oscuro (alto contraste, on-brand)
_SEED = 0xF17               # semilla fija -> patrón estable entre renders
_CENTER = 9                   # knockout central (módulos) para el logo


def _finder_corners() -> list[tuple[int, int]]:
    """Esquina superior-izquierda (fila, col) de cada patrón localizador 7x7."""
    return [(0, 0), (0, _MODULES - 7), (_MODULES - 7, 0)]


def render_qr_mock(size: int, dpr: float = 1.0) -> QPixmap:
    """Devuelve un QR decorativo de ``size`` px (lógicos), high-DPI aware."""
    dpr = max(1.0, float(dpr))
    pm = QPixmap(int(round(size * dpr)), int(round(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    s = float(size)
    dark = QColor(_DARK)
    white = QColor("#ffffff")

    # Tarjeta blanca de fondo
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(white)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.08, s * 0.08)

    pad = s * 0.10               # zona de silencio
    m = (s - 2 * pad) / _MODULES  # tamaño de módulo
    n = _MODULES

    # Celdas reservadas: localizadores + separador, y knockout central
    reserved = [[False] * n for _ in range(n)]
    for fr, fc in _finder_corners():
        for r in range(fr - 1, fr + 8):
            for c in range(fc - 1, fc + 8):
                if 0 <= r < n and 0 <= c < n:
                    reserved[r][c] = True
    c0 = (n - _CENTER) // 2
    for r in range(c0, c0 + _CENTER):
        for c in range(c0, c0 + _CENTER):
            reserved[r][c] = True

    def cell(r: int, c: int, inset: float = 0.0) -> QRectF:
        return QRectF(pad + c * m + inset, pad + r * m + inset, m - 2 * inset, m - 2 * inset)

    # Módulos pseudo-aleatorios DETERMINISTAS
    rnd = random.Random(_SEED)
    p.setBrush(dark)
    for r in range(n):
        for c in range(n):
            if reserved[r][c]:
                continue
            if rnd.random() < 0.48:
                p.drawRoundedRect(cell(r, c, inset=m * 0.08), m * 0.22, m * 0.22)

    # Patrones localizadores (7x7 con "ojo")
    for fr, fc in _finder_corners():
        p.setBrush(dark)
        p.drawRoundedRect(QRectF(pad + fc * m, pad + fr * m, 7 * m, 7 * m), m * 1.1, m * 1.1)
        p.setBrush(white)
        p.drawRoundedRect(QRectF(pad + (fc + 1) * m, pad + (fr + 1) * m, 5 * m, 5 * m), m * 0.8, m * 0.8)
        p.setBrush(dark)
        p.drawRoundedRect(QRectF(pad + (fc + 2) * m, pad + (fr + 2) * m, 3 * m, 3 * m), m * 0.5, m * 0.5)

    # Marca FitPilot centrada (sobre el knockout blanco)
    mark = logo_mark_pixmap(int(_CENTER * m * 0.74), dpr)
    if mark is not None:
        mw = mark.width() / dpr
        mh = mark.height() / dpr
        cx = pad + (c0 + _CENTER / 2) * m
        cy = pad + (c0 + _CENTER / 2) * m
        p.drawPixmap(int(cx - mw / 2), int(cy - mh / 2), mark)

    p.end()
    return pm
