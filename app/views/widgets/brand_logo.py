"""Helpers to load the FitPilot brand logo as a crisp ``QPixmap``.

The SVG (``FitPilot-Logo.svg``) cannot be used here because ``PySide6.QtSvg``
fails to load its DLL in this environment, so we rasterise PNGs instead. Loading
is high-DPI aware: pass the display's ``devicePixelRatio`` so the pixmap renders
sharply on scaled screens.

- ``logo_pixmap``      → the full logo (graphic mark + "FitPilot" wordmark).
- ``logo_mark_pixmap`` → only the graphic mark (wings + P), pre-cropped into
  ``fitpilot-mark.png`` so it sits beside a separate "FitPilot" text label.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor

# frontend/app/views/widgets/brand_logo.py -> parents[2] == frontend/app
_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_LOGO_PNG = _ASSETS_DIR / "fitpilot-logo.png"
_MARK_PNG = _ASSETS_DIR / "fitpilot-mark.png"
# Same mark with the navy wings re-tinted to a mid blue, so it reads on dark
# surfaces (the navy is nearly invisible there). Used on dark themes.
_MARK_LIGHT_PNG = _ASSETS_DIR / "fitpilot-mark-light.png"


def _load_scaled(path: Path, height: int, device_pixel_ratio: float) -> Optional[QPixmap]:
    if not path.exists():
        return None
    source = QPixmap(str(path))
    if source.isNull():
        return None
    dpr = max(1.0, float(device_pixel_ratio))
    target_h = max(1, int(round(height * dpr)))
    scaled = source.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(dpr)
    return scaled


def logo_pixmap(height: int, device_pixel_ratio: float = 1.0) -> Optional[QPixmap]:
    """Return the full brand logo scaled to ``height`` logical pixels (keeps aspect).

    Returns ``None`` if the asset is missing so callers can fall back to text.
    """
    return _load_scaled(_LOGO_PNG, height, device_pixel_ratio)


def logo_mark_pixmap(height: int, device_pixel_ratio: float = 1.0) -> Optional[QPixmap]:
    """Return only the graphic mark (wings + P), scaled to ``height``.

    Falls back to the full logo if the cropped mark asset is missing, and to
    ``None`` if neither exists.
    """
    return _load_scaled(_MARK_PNG, height, device_pixel_ratio) or _load_scaled(
        _LOGO_PNG, height, device_pixel_ratio
    )


def logo_mark_pixmap_for_dark(height: int, device_pixel_ratio: float = 1.0) -> Optional[QPixmap]:
    """Mark variant whose navy wings are lightened so it reads on dark surfaces.

    Falls back to the standard (navy) mark if the lightened asset is missing.
    """
    return _load_scaled(_MARK_LIGHT_PNG, height, device_pixel_ratio) or logo_mark_pixmap(
        height, device_pixel_ratio
    )


def logo_mark_pixmap_tinted(
    height: int, color: str, device_pixel_ratio: float = 1.0
) -> Optional[QPixmap]:
    """Monochrome mark: the graphic mark filled with a single ``color``.

    Useful for a one-tone (e.g. accent-colored) brand icon. Returns ``None`` if
    the mark asset is missing.
    """
    src = _MARK_PNG if _MARK_PNG.exists() else _LOGO_PNG
    source = QPixmap(str(src))
    if source.isNull():
        return None
    dpr = max(1.0, float(device_pixel_ratio))
    target_h = max(1, int(round(height * dpr)))
    base = source.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(base.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(base.rect(), QColor(color))
    painter.end()
    result.setDevicePixelRatio(dpr)
    return result
