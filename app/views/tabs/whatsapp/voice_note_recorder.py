"""Qt recorder wrapper for WhatsApp voice notes."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioInput,
    QMediaCaptureSession,
    QMediaDevices,
    QMediaFormat,
    QMediaRecorder,
)

from ....core.config import Config
from ....services.voice_note_converter import (
    VoiceNoteConversionError,
    convert_wav_to_ogg_opus,
)


class VoiceNoteRecorder(QObject):
    """Records a short WAV clip and converts it to WhatsApp OGG/Opus."""

    recording_started = Signal()
    duration_changed = Signal(int)
    ready = Signal(str)
    canceled = Signal()
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session: QMediaCaptureSession | None = None
        self._audio_input: QAudioInput | None = None
        self._recorder: QMediaRecorder | None = None
        self._recording_path: Path | None = None
        self._pending_action: str | None = None

    @staticmethod
    def can_record() -> bool:
        """Return True when Qt can see at least one audio input."""
        try:
            return bool(QMediaDevices.audioInputs())
        except Exception:  # noqa: BLE001 - Qt backends may fail during startup
            return False

    @property
    def is_recording(self) -> bool:
        if self._recorder is None:
            return False
        state = self._recorder.recorderState()
        return state == QMediaRecorder.RecorderState.RecordingState

    def start(self) -> None:
        if self.is_recording:
            return

        if not self.can_record():
            self.error.emit("No hay microfono disponible.")
            return

        output_dir = Config.CACHE_DIR / "voice_notes"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._recording_path = output_dir / f"voice_note_{uuid4().hex}.wav"
        self._pending_action = None

        try:
            device = QMediaDevices.defaultAudioInput()
            if hasattr(device, "isNull") and device.isNull():
                self.error.emit("No hay microfono disponible.")
                return

            self._session = QMediaCaptureSession(self)
            self._audio_input = QAudioInput(device, self)
            self._recorder = QMediaRecorder(self)
            self._recorder.setOutputLocation(
                QUrl.fromLocalFile(str(self._recording_path))
            )
            self._recorder.setMediaFormat(self._wav_format())
            self._recorder.setAudioChannelCount(1)
            self._recorder.setAudioSampleRate(48000)
            self._recorder.durationChanged.connect(self._on_duration_changed)
            self._recorder.recorderStateChanged.connect(self._on_state_changed)
            self._recorder.errorOccurred.connect(self._on_recorder_error)

            self._session.setAudioInput(self._audio_input)
            self._session.setRecorder(self._recorder)
            self._recorder.record()
            self.recording_started.emit()
        except Exception as exc:  # noqa: BLE001
            self._cleanup_recording()
            self._teardown()
            self.error.emit(f"No se pudo iniciar la grabacion: {exc}")

    def finish(self) -> None:
        if self._recorder is None:
            self.error.emit("No hay una nota de voz grabandose.")
            return
        self._pending_action = "send"
        self._recorder.stop()

    def cancel(self) -> None:
        if self._recorder is None:
            self._cleanup_recording()
            self.canceled.emit()
            return
        self._pending_action = "cancel"
        self._recorder.stop()

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.duration_changed.emit(int(duration_ms))

    def _on_state_changed(self, state) -> None:
        if state != QMediaRecorder.RecorderState.StoppedState:
            return
        action = self._pending_action
        if not action:
            return
        self._pending_action = None

        if action == "cancel":
            self._cleanup_recording()
            self._teardown()
            self.canceled.emit()
            return

        source = self._recording_path
        try:
            if source is None or not source.exists() or source.stat().st_size <= 0:
                raise VoiceNoteConversionError("La nota de voz esta vacia.")
            output = convert_wav_to_ogg_opus(source)
            self._delete_path(source)
            self._recording_path = None
            self.ready.emit(str(output))
        except VoiceNoteConversionError as exc:
            self._cleanup_recording()
            self.error.emit(str(exc))
        finally:
            self._teardown()

    def _on_recorder_error(self, _error, error_string: str = "") -> None:
        self._cleanup_recording()
        self._teardown()
        self.error.emit(error_string or "No se pudo grabar la nota de voz.")

    @staticmethod
    def _wav_format() -> QMediaFormat:
        fmt = QMediaFormat()
        fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
        fmt.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        return fmt

    def _cleanup_recording(self) -> None:
        self._delete_path(self._recording_path)
        if self._recording_path is not None:
            self._delete_path(self._recording_path.with_suffix(".ogg"))
        self._recording_path = None

    @staticmethod
    def _delete_path(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _teardown(self) -> None:
        self._session = None
        self._audio_input = None
        self._recorder = None
        self._pending_action = None
