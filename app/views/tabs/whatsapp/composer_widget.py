"""Message composer (text input + send button)."""
import qtawesome as qta
from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton

from . import theme

_STYLE = f"""
#composer {{ background-color: palette(window); }}
#composerInput {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid transparent;
    border-radius: 21px;
    padding: 0 16px;
    min-height: 42px;
    max-height: 42px;
    font-size: 13px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    placeholder-text-color: palette(placeholder-text);
}}
#composerInput:focus {{ border: 1px solid palette(highlight); }}
#composerInput::placeholder {{ color: palette(placeholder-text); }}
#composerIconButton {{
    background: transparent;
    color: palette(mid);
    border: none;
    border-radius: 18px;
    padding: 7px;
}}
#composerIconButton:hover {{ background-color: palette(alternate-base); }}
#composerSend {{
    background-color: {theme.ACCENT};
    border: none;
    border-radius: 20px;
    padding: 8px;
}}
#composerSend:hover {{ background-color: #06c191; }}
#composerSend:disabled {{
    background-color: palette(mid);
    color: palette(window);
}}
#composerInput:disabled {{
    background-color: palette(window);
    color: palette(mid);
    border: 1px solid palette(mid);
}}
"""


def _make_visual_button(icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("composerIconButton")
    button.setIcon(qta.icon(icon_name, color=theme.palette_hex(QPalette.ColorRole.Mid)))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(36, 36)
    button.setToolTip(tooltip)
    button.setEnabled(False)
    button.setAutoRaise(True)
    return button


class ComposerWidget(QWidget):
    send_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        self.setStyleSheet(_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        layout.addWidget(_make_visual_button("fa5s.plus", "Proximamente: adjuntar"))
        layout.addWidget(_make_visual_button("fa5s.smile", "Proximamente: emojis"))

        self.input = QLineEdit()
        self.input.setObjectName("composerInput")
        self.input.setPlaceholderText("Escribe un mensaje...")
        self.input.returnPressed.connect(self._emit)
        layout.addWidget(self.input, 1)

        layout.addWidget(_make_visual_button("fa5s.microphone", "Proximamente: audio"))

        self.send_button = QToolButton()
        self.send_button.setObjectName("composerSend")
        self.send_button.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        self.send_button.setIconSize(QSize(17, 17))
        self.send_button.setFixedSize(40, 40)
        self.send_button.setToolTip("Enviar")
        self.send_button.setCursor(self.send_button.cursor())
        self.send_button.clicked.connect(self._emit)
        layout.addWidget(self.send_button)

    def set_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def _emit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.send_requested.emit(text)
            self.input.clear()
