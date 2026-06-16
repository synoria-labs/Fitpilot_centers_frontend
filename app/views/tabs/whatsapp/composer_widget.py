"""Message composer (text input + attach button + emoji picker + send button)."""
import qtawesome as qta
from PySide6.QtCore import Signal, QSize, QPoint, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLineEdit, QToolButton, QWidget

from . import theme
from .attachment_preview_dialog import AttachmentPreviewDialog, FILE_DIALOG_FILTER
from .emoji_picker import EmojiPicker

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
    color: {theme.TEXT_PRIMARY};
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
    attachment_requested = Signal(str, str)  # (file_path, caption)
    bot_toggle_requested = Signal(bool)  # robot button: enable/disable the bot for this conversation

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        # A plain QWidget only paints its stylesheet background-color when
        # WA_StyledBackground is set; without this the bar wouldn't take the
        # palette(window) color (same as the chat area).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self._emoji_picker = None  # lazily created, reused across openings

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        self.attach_button = QToolButton()
        self.attach_button.setObjectName("composerIconButton")
        self.attach_button.setIcon(qta.icon("fa5s.plus", color=theme.TEXT_PRIMARY))
        self.attach_button.setIconSize(QSize(18, 18))
        self.attach_button.setFixedSize(36, 36)
        self.attach_button.setToolTip("Adjuntar archivo")
        self.attach_button.setAutoRaise(True)
        self.attach_button.clicked.connect(self._on_attach_clicked)
        layout.addWidget(self.attach_button)

        self.emoji_button = QToolButton()
        self.emoji_button.setObjectName("composerIconButton")
        self.emoji_button.setIcon(qta.icon("fa5s.smile", color=theme.TEXT_PRIMARY))
        self.emoji_button.setIconSize(QSize(18, 18))
        self.emoji_button.setFixedSize(36, 36)
        self.emoji_button.setToolTip("Emojis")
        self.emoji_button.setAutoRaise(True)
        self.emoji_button.clicked.connect(self._open_emoji_picker)
        layout.addWidget(self.emoji_button)

        # Robot toggle: enable/disable the WhatsApp bot for the open conversation.
        self.bot_button = QToolButton()
        self.bot_button.setObjectName("composerIconButton")
        self.bot_button.setCheckable(True)
        self.bot_button.setChecked(True)
        self.bot_button.setIconSize(QSize(18, 18))
        self.bot_button.setFixedSize(36, 36)
        self.bot_button.setAutoRaise(True)
        self.bot_button.toggled.connect(self._on_bot_toggled)
        self._update_bot_button(True)
        layout.addWidget(self.bot_button)

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
        self.attach_button.setEnabled(enabled)
        self.emoji_button.setEnabled(enabled)
        self.bot_button.setEnabled(enabled)

    def set_sending(self, sending: bool) -> None:
        """Lock the composer while an attachment is being uploaded."""
        self.set_enabled(not sending)
        self.input.setPlaceholderText(
            "Enviando archivo..." if sending else "Escribe un mensaje..."
        )

    def set_bot_enabled(self, enabled: bool) -> None:
        """Reflect a conversation's bot state on the toggle WITHOUT emitting a change."""
        self.bot_button.blockSignals(True)
        self.bot_button.setChecked(bool(enabled))
        self.bot_button.blockSignals(False)
        self._update_bot_button(bool(enabled))

    def _on_bot_toggled(self, checked: bool) -> None:
        self._update_bot_button(checked)
        self.bot_toggle_requested.emit(checked)

    def _update_bot_button(self, enabled: bool) -> None:
        icon = "mdi6.robot" if enabled else "mdi6.robot-off"
        color = theme.ACCENT if enabled else theme.palette_hex(QPalette.ColorRole.Mid)
        self.bot_button.setIcon(qta.icon(icon, color=color))
        self.bot_button.setToolTip(
            "Bot activado — clic para desactivar"
            if enabled
            else "Bot desactivado — clic para activar"
        )

    def _emit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.send_requested.emit(text)
            self.input.clear()

    def _on_attach_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Adjuntar archivo", "", FILE_DIALOG_FILTER
        )
        if not file_path:
            return
        dialog = AttachmentPreviewDialog(file_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.attachment_requested.emit(dialog.file_path, dialog.caption)

    def _open_emoji_picker(self) -> None:
        if self._emoji_picker is None:
            self._emoji_picker = EmojiPicker(self)
            self._emoji_picker.emoji_selected.connect(self._insert_emoji)
        picker = self._emoji_picker
        # Position the popup just above the emoji button, left-aligned with it.
        anchor = self.emoji_button.mapToGlobal(QPoint(0, 0))
        x = anchor.x()
        y = anchor.y() - picker.height() - 6
        picker.move(x, max(0, y))
        picker.show()

    def _insert_emoji(self, emoji: str) -> None:
        # Insert at the cursor (replacing any selection); keep the picker open.
        self.input.insert(emoji)
