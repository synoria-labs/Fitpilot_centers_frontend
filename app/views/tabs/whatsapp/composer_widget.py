"""Message composer (text input + attach button + voice recorder + send button)."""
import qtawesome as qta
from PySide6.QtCore import Signal, QSize, QPoint, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from . import theme
from .attachment_preview_dialog import AttachmentPreviewDialog, FILE_DIALOG_FILTER
from .emoji_picker import EmojiPicker
from .voice_note_recorder import VoiceNoteRecorder
from .voice_waveform_widget import VoiceWaveformWidget

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
#recordingBar {{
    background-color: palette(base);
    border: 1px solid palette(highlight);
    border-radius: 21px;
    min-height: 42px;
    max-height: 42px;
}}
QLabel#recordingDot {{
    background-color: #ff5c5c;
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
}}
QLabel#recordingTime {{
    color: {theme.TEXT_PRIMARY};
    background: transparent;
    font-size: 13px;
    min-width: 38px;
}}
#composerPauseButton {{
    background: transparent;
    border: none;
    border-radius: 18px;
    padding: 7px;
}}
#composerPauseButton:hover {{ background-color: {theme.ITEM_HOVER}; }}
#composerPauseButton:disabled {{
    background: transparent;
    color: palette(mid);
}}
#composerDangerButton {{
    background: transparent;
    color: #ff7777;
    border: none;
    border-radius: 18px;
    padding: 7px;
}}
#composerDangerButton:hover {{ background-color: rgba(255, 92, 92, 0.16); }}
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


class ComposerWidget(QWidget):
    send_requested = Signal(str)
    attachment_requested = Signal(str, str)  # (file_path, caption)
    voice_note_requested = Signal(str)  # converted OGG/Opus path
    voice_note_failed = Signal(str)
    bot_toggle_requested = Signal(bool)  # robot button: enable/disable the bot for this conversation

    def __init__(
        self,
        parent=None,
        *,
        voice_recorder: VoiceNoteRecorder | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        # A plain QWidget only paints its stylesheet background-color when
        # WA_StyledBackground is set; without this the bar wouldn't take the
        # palette(window) color (same as the chat area).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self._emoji_picker = None  # lazily created, reused across openings
        self._recording = False
        self._recording_paused = False
        self._voice_recorder = voice_recorder or VoiceNoteRecorder(self)
        self._voice_recorder.recording_started.connect(self._on_recording_started)
        self._voice_recorder.recording_paused.connect(self._on_recording_paused)
        self._voice_recorder.recording_resumed.connect(self._on_recording_resumed)
        self._voice_recorder.duration_changed.connect(self._update_recording_time)
        self._voice_recorder.level_changed.connect(self._on_recording_level)
        self._voice_recorder.ready.connect(self._on_voice_note_ready)
        self._voice_recorder.canceled.connect(self._on_recording_canceled)
        self._voice_recorder.error.connect(self._on_voice_note_error)

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

        self.recording_bar = QWidget()
        self.recording_bar.setObjectName("recordingBar")
        recording_layout = QHBoxLayout(self.recording_bar)
        recording_layout.setContentsMargins(14, 0, 8, 0)
        recording_layout.setSpacing(8)

        self.recording_dot = QLabel()
        self.recording_dot.setObjectName("recordingDot")
        recording_layout.addWidget(self.recording_dot)

        self.recording_time = QLabel("0:00")
        self.recording_time.setObjectName("recordingTime")
        recording_layout.addWidget(self.recording_time)

        self.voice_waveform = VoiceWaveformWidget()
        recording_layout.addWidget(self.voice_waveform, 1)

        self.pause_recording_button = QToolButton()
        self.pause_recording_button.setObjectName("composerPauseButton")
        self.pause_recording_button.setIconSize(QSize(16, 16))
        self.pause_recording_button.setFixedSize(36, 36)
        self.pause_recording_button.setAutoRaise(True)
        self.pause_recording_button.clicked.connect(self._toggle_voice_recording_pause)
        self._update_pause_button()
        recording_layout.addWidget(self.pause_recording_button)

        self.cancel_recording_button = QToolButton()
        self.cancel_recording_button.setObjectName("composerDangerButton")
        self.cancel_recording_button.setIcon(qta.icon("fa5s.trash", color="#ff7777"))
        self.cancel_recording_button.setIconSize(QSize(16, 16))
        self.cancel_recording_button.setFixedSize(36, 36)
        self.cancel_recording_button.setToolTip("Cancelar nota de voz")
        self.cancel_recording_button.setAutoRaise(True)
        self.cancel_recording_button.clicked.connect(self._cancel_voice_recording)
        recording_layout.addWidget(self.cancel_recording_button)

        self.send_recording_button = QToolButton()
        self.send_recording_button.setObjectName("composerSend")
        self.send_recording_button.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        self.send_recording_button.setIconSize(QSize(16, 16))
        self.send_recording_button.setFixedSize(36, 36)
        self.send_recording_button.setToolTip("Enviar nota de voz")
        self.send_recording_button.clicked.connect(self._send_voice_recording)
        recording_layout.addWidget(self.send_recording_button)

        self.recording_bar.hide()
        layout.addWidget(self.recording_bar, 1)

        self.input = QLineEdit()
        self.input.setObjectName("composerInput")
        self.input.setPlaceholderText("Escribe un mensaje...")
        self.input.returnPressed.connect(self._emit)
        layout.addWidget(self.input, 1)

        self.mic_button = QToolButton()
        self.mic_button.setObjectName("composerIconButton")
        self.mic_button.setIcon(qta.icon("fa5s.microphone", color=theme.TEXT_PRIMARY))
        self.mic_button.setIconSize(QSize(18, 18))
        self.mic_button.setFixedSize(36, 36)
        self.mic_button.setToolTip("Grabar nota de voz")
        self.mic_button.setAutoRaise(True)
        self.mic_button.clicked.connect(self._start_voice_recording)
        layout.addWidget(self.mic_button)

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
        self.mic_button.setEnabled(enabled)
        self.pause_recording_button.setEnabled(enabled)
        self.cancel_recording_button.setEnabled(enabled)
        self.send_recording_button.setEnabled(enabled)

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

    # ------------------------------------------------------------------
    # Voice notes
    # ------------------------------------------------------------------
    def _start_voice_recording(self) -> None:
        self._voice_recorder.start()

    def _cancel_voice_recording(self) -> None:
        self.pause_recording_button.setEnabled(False)
        self.cancel_recording_button.setEnabled(False)
        self.send_recording_button.setEnabled(False)
        self._voice_recorder.cancel()

    def _send_voice_recording(self) -> None:
        self.pause_recording_button.setEnabled(False)
        self.cancel_recording_button.setEnabled(False)
        self.send_recording_button.setEnabled(False)
        self.voice_waveform.set_processing(True)
        self.recording_time.setText("Procesando...")
        self._voice_recorder.finish()

    def _toggle_voice_recording_pause(self) -> None:
        if not self._recording:
            return
        if self._recording_paused:
            self._voice_recorder.resume()
        else:
            self._voice_recorder.pause()

    def _on_recording_started(self) -> None:
        self._recording = True
        self._recording_paused = False
        self.recording_time.setText("0:00")
        self.voice_waveform.reset()
        self._update_pause_button()
        self._set_recording_dot_paused(False)
        self.pause_recording_button.setEnabled(True)
        self.cancel_recording_button.setEnabled(True)
        self.send_recording_button.setEnabled(True)
        self._set_recording_mode(True)

    def _on_recording_paused(self) -> None:
        self._recording_paused = True
        self.voice_waveform.set_paused(True)
        self._set_recording_dot_paused(True)
        self._update_pause_button()

    def _on_recording_resumed(self) -> None:
        self._recording_paused = False
        self.voice_waveform.set_paused(False)
        self._set_recording_dot_paused(False)
        self._update_pause_button()

    def _on_recording_canceled(self) -> None:
        self._recording = False
        self._recording_paused = False
        self._set_recording_mode(False)

    def _on_voice_note_ready(self, file_path: str) -> None:
        self._recording = False
        self._recording_paused = False
        self._set_recording_mode(False)
        self.voice_note_requested.emit(file_path)

    def _on_voice_note_error(self, message: str) -> None:
        self._recording = False
        self._recording_paused = False
        self._set_recording_mode(False)
        self.voice_note_failed.emit(message or "No se pudo grabar la nota de voz.")

    def _on_recording_level(self, level: float) -> None:
        if self._recording:
            self.voice_waveform.add_level(level)

    def _update_recording_time(self, duration_ms: int) -> None:
        if not self._recording:
            return
        seconds = max(0, int(duration_ms / 1000))
        self.recording_time.setText(f"{seconds // 60}:{seconds % 60:02d}")

    def _update_pause_button(self) -> None:
        icon_name = "fa5s.play" if self._recording_paused else "fa5s.pause"
        color = theme.ACCENT if self._recording_paused else theme.TEXT_PRIMARY
        self.pause_recording_button.setIcon(qta.icon(icon_name, color=color))
        self.pause_recording_button.setToolTip(
            "Reanudar nota de voz" if self._recording_paused else "Pausar nota de voz"
        )

    def _set_recording_dot_paused(self, paused: bool) -> None:
        color = theme.TEXT_SECONDARY if paused else "#ff5c5c"
        self.recording_dot.setStyleSheet(f"background-color: {color};")

    def _set_recording_mode(self, recording: bool) -> None:
        for widget in (
            self.attach_button,
            self.emoji_button,
            self.bot_button,
            self.input,
            self.mic_button,
            self.send_button,
        ):
            widget.setVisible(not recording)
        self.recording_bar.setVisible(recording)
        if not recording:
            self.voice_waveform.reset()
            self._update_pause_button()
            self._set_recording_dot_paused(False)
