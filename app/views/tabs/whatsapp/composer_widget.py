"""Message composer (text input + send button)."""
import qtawesome as qta
from PySide6.QtCore import Signal, QSize
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton

from . import theme

_STYLE = f"""
#composer {{ background-color: {theme.BG_PANEL}; }}
#composerInput {{
    background-color: {theme.INPUT_BG};
    color: {theme.TEXT_PRIMARY};
    border: none;
    border-radius: 21px;
    padding: 10px 16px;
    font-size: 13px;
}}
#composerInput::placeholder {{ color: {theme.TEXT_SECONDARY}; }}
#composerIconButton {{
    background: transparent;
    color: {theme.TEXT_SECONDARY};
    border: none;
    border-radius: 18px;
    padding: 7px;
}}
#composerIconButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
#composerSend {{
    background-color: {theme.ACCENT};
    border: none;
    border-radius: 20px;
    padding: 8px;
}}
#composerSend:hover {{ background-color: #06c191; }}
#composerSend:disabled {{ background-color: #3b4a52; color: #8696A0; }}
#composerInput:disabled {{ color: #6b7a83; }}
"""


def _make_visual_button(icon_name: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("composerIconButton")
    button.setIcon(qta.icon(icon_name, color=theme.TEXT_SECONDARY))
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
