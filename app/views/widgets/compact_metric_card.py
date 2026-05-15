"""Compact, theme-aware metric card.

Used by the Finanzas (PaymentsMetricsPanel) and Dashboard tabs to render
single-value KPIs with a colored left accent stripe and an optional trend
line. Backgrounds and secondary text use ``palette(...)`` so the card matches
whichever Qt theme (light/dark) is active.

Layout:
    ▎ 💵  Ingresos
    ▎ $4,400.00
    ▎ ↑ +12.3%
"""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# Hard-coded medium gray for secondary text. ``palette(mid)`` is intended for
# separators and reads as nearly invisible on most dark themes.
SECONDARY_TEXT = "#a0a8b0"

# Trend deltas use these accent colors regardless of card accent.
TREND_UP_COLOR = "#2ecc71"
TREND_DOWN_COLOR = "#e74c3c"
TREND_FLAT_COLOR = SECONDARY_TEXT


_CARD_QSS_TEMPLATE = """
QFrame#compactMetricCard {{
    background-color: palette(alternate-base);
    border: 1px solid palette(mid);
    border-left: 3px solid {accent};
    border-radius: 5px;
}}
"""


def trend_text(curr: float | int | None, prev: float | int | None) -> Tuple[str, str]:
    """Compute trend label + color for two comparable numbers.

    Returns ``("", SECONDARY_TEXT)`` when prev is None or 0 (no meaningful base
    to compute a percent against). Otherwise returns ``("↑ +X.X%", green)``,
    ``("↓ -X.X%", red)``, or ``("→ 0.0%", gray)``.
    """
    if prev is None or curr is None:
        return "", TREND_FLAT_COLOR
    try:
        prev_f = float(prev)
        curr_f = float(curr)
    except (TypeError, ValueError):
        return "", TREND_FLAT_COLOR
    if prev_f == 0:
        if curr_f == 0:
            return "→ 0.0%", TREND_FLAT_COLOR
        # Going from 0 to something is a real change but the percent is
        # mathematically undefined; surface the absolute delta instead.
        return f"↑ +{curr_f:,.0f}", TREND_UP_COLOR
    delta = (curr_f - prev_f) / prev_f * 100
    if delta > 0:
        return f"↑ +{delta:.1f}%", TREND_UP_COLOR
    if delta < 0:
        return f"↓ {delta:.1f}%", TREND_DOWN_COLOR
    return "→ 0.0%", TREND_FLAT_COLOR


class CompactMetricCard(QFrame):
    """Compact, theme-aware metric card."""

    def __init__(
        self,
        title: str,
        icon: str,
        accent: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("compactMetricCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._accent = accent
        self._title_text = title
        self._icon_text = icon
        self._build()
        self._apply_accent()

    # ----------------------------------------------------------------- ui

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(1)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.setContentsMargins(0, 0, 0, 0)
        self._icon = QLabel(self._icon_text)
        header.addWidget(self._icon)
        self._title = QLabel(self._title_text)
        header.addWidget(self._title)
        header.addStretch()
        outer.addLayout(header)

        self._value = QLabel("0")
        outer.addWidget(self._value)

        self._trend = QLabel("")
        self._trend.setVisible(False)
        outer.addWidget(self._trend)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(78)

    def _apply_accent(self) -> None:
        self.setStyleSheet(_CARD_QSS_TEMPLATE.format(accent=self._accent))
        self._icon.setStyleSheet(
            f"font-size: 14px; color: {self._accent}; background: transparent; border: none;"
        )
        self._title.setStyleSheet(
            f"font-size: 11px; color: {SECONDARY_TEXT}; background: transparent; "
            f"border: none; font-weight: 500;"
        )
        self._value.setStyleSheet(
            f"font-size: 19px; font-weight: bold; color: {self._accent}; "
            f"background: transparent; border: none;"
        )
        # Trend stylesheet is overwritten on each set_value() to encode color.

    # ----------------------------------------------------------------- public

    def configure(self, *, icon: str, title: str) -> None:
        """Override icon and title after construction."""
        self._icon_text = icon
        self._title_text = title
        self._icon.setText(icon)
        self._title.setText(title)

    def set_value(
        self,
        value: str,
        trend: Optional[str] = None,
        trend_color: str = SECONDARY_TEXT,
    ) -> None:
        """Set the main value and optional trend line.

        ``trend`` is freeform text (e.g. "Top: cash" or "↑ +12.3%"); when
        ``trend_color`` is provided it's applied so callers can use the
        ``trend_text(...)`` helper to get a coordinated label/color pair.
        """
        self._value.setText(value)
        if trend:
            self._trend.setText(trend)
            self._trend.setStyleSheet(
                f"font-size: 10px; color: {trend_color}; "
                f"background: transparent; border: none;"
            )
            self._trend.setVisible(True)
        else:
            self._trend.setVisible(False)

    def set_trend_delta(
        self, current: float | int | None, previous: float | int | None
    ) -> None:
        """Convenience: compute trend text from current/previous and apply it."""
        label, color = trend_text(current, previous)
        if label:
            self._trend.setText(label)
            self._trend.setStyleSheet(
                f"font-size: 10px; color: {color}; "
                f"background: transparent; border: none;"
            )
            self._trend.setVisible(True)
        else:
            self._trend.setVisible(False)

    def set_accent(self, accent: str) -> None:
        if accent == self._accent:
            return
        self._accent = accent
        self._apply_accent()

    @property
    def accent(self) -> str:
        return self._accent
