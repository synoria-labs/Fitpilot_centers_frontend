"""Qt microphone capture for WhatsApp voice notes."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices

from ....core.config import Config
from ....core.logging import get_logger
from ....services.voice_note_converter import (
    VoiceNoteConversionError,
    convert_wav_to_ogg_opus,
)

logger = get_logger(__name__)

_TARGET_SAMPLE_RATE = 48000
_TARGET_CHANNELS = 1
_PCM16_WIDTH = 2
_MAX_INT16 = 32767
_MIN_INT16 = -32768

# On Windows the recorded WAV can stay briefly locked right after the writer is
# closed, so an immediate unlink fails. Retry a few times (deferred, non-blocking)
# before giving up so cancelled recordings don't leak temp files.
_DELETE_MAX_RETRIES = 5
_DELETE_RETRY_MS = 120


def select_voice_note_format(device) -> QAudioFormat:
    """Prefer 48 kHz mono PCM16, falling back to the device format."""
    audio_format = QAudioFormat()
    audio_format.setSampleRate(_TARGET_SAMPLE_RATE)
    audio_format.setChannelCount(_TARGET_CHANNELS)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    if device.isFormatSupported(audio_format):
        return audio_format

    preferred = device.preferredFormat()
    if (
        preferred.sampleRate() > 0
        and preferred.channelCount() > 0
        and preferred.sampleFormat() != QAudioFormat.SampleFormat.Unknown
    ):
        return preferred

    raise VoiceNoteConversionError("El microfono no tiene un formato de audio compatible.")


def audio_chunk_to_pcm16_mono(data: bytes, audio_format: QAudioFormat) -> bytes:
    """Convert one Qt audio chunk to little-endian PCM16 mono."""
    if not data:
        return b""

    channels = max(1, int(audio_format.channelCount()))
    bytes_per_sample = int(audio_format.bytesPerSample())
    frame_size = channels * bytes_per_sample
    if bytes_per_sample <= 0 or frame_size <= 0:
        return b""

    usable_size = len(data) - (len(data) % frame_size)
    if usable_size <= 0:
        return b""

    sample_format = audio_format.sampleFormat()
    output = bytearray((usable_size // frame_size) * _PCM16_WIDTH)
    output_index = 0

    for frame_offset in range(0, usable_size, frame_size):
        total = 0.0
        for channel in range(channels):
            offset = frame_offset + (channel * bytes_per_sample)
            total += _sample_to_float(data, offset, sample_format, bytes_per_sample)

        mono = total / channels
        pcm_value = _float_to_pcm16(mono)
        struct.pack_into("<h", output, output_index, pcm_value)
        output_index += _PCM16_WIDTH

    return bytes(output)


def calculate_pcm16_level(pcm_data: bytes) -> float:
    """Return a display-friendly 0..1 level using RMS and peak energy."""
    usable_size = len(pcm_data) - (len(pcm_data) % _PCM16_WIDTH)
    if usable_size <= 0:
        return 0.0

    sample_count = usable_size // _PCM16_WIDTH
    square_sum = 0.0
    peak = 0
    for (sample,) in struct.iter_unpack("<h", pcm_data[:usable_size]):
        absolute = abs(sample)
        peak = max(peak, absolute)
        square_sum += sample * sample

    rms = math.sqrt(square_sum / sample_count) / 32768.0
    peak_level = peak / 32768.0
    return max(0.0, min(1.0, max(rms * 2.2, peak_level * 0.7)))


def _sample_to_float(
    data: bytes,
    offset: int,
    sample_format: QAudioFormat.SampleFormat,
    bytes_per_sample: int,
) -> float:
    if sample_format == QAudioFormat.SampleFormat.Int16 and bytes_per_sample >= 2:
        return struct.unpack_from("<h", data, offset)[0] / 32768.0
    if sample_format == QAudioFormat.SampleFormat.Int32 and bytes_per_sample >= 4:
        return struct.unpack_from("<i", data, offset)[0] / 2147483648.0
    if sample_format == QAudioFormat.SampleFormat.Float and bytes_per_sample >= 4:
        return max(-1.0, min(1.0, struct.unpack_from("<f", data, offset)[0]))
    if sample_format == QAudioFormat.SampleFormat.UInt8 and bytes_per_sample >= 1:
        return (data[offset] - 128) / 128.0
    return 0.0


def _float_to_pcm16(value: float) -> int:
    clamped = max(-1.0, min(1.0, value))
    if clamped <= -1.0:
        return _MIN_INT16
    return max(_MIN_INT16, min(_MAX_INT16, int(round(clamped * _MAX_INT16))))


class VoiceNoteRecorder(QObject):
    """Records microphone PCM, converts it to WhatsApp OGG/Opus, and emits levels."""

    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_PAUSED = "paused"
    STATE_PROCESSING = "processing"

    recording_started = Signal()
    recording_paused = Signal()
    recording_resumed = Signal()
    state_changed = Signal(str)
    duration_changed = Signal(int)
    level_changed = Signal(float)
    ready = Signal(str)
    canceled = Signal()
    error = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        audio_source_factory: Callable | None = None,
    ) -> None:
        super().__init__(parent)
        self._audio_source_factory = audio_source_factory or QAudioSource
        self._audio_source: QAudioSource | None = None
        self._audio_device = None
        self._audio_format: QAudioFormat | None = None
        self._wav_writer: wave.Wave_write | None = None
        self._recording_path: Path | None = None
        self._frames_written = 0
        self._state = self.STATE_IDLE

    @staticmethod
    def can_record() -> bool:
        """Return True when Qt can see at least one audio input."""
        try:
            return bool(QMediaDevices.audioInputs())
        except Exception:  # noqa: BLE001 - Qt backends may fail during startup
            return False

    @property
    def is_recording(self) -> bool:
        return self._state == self.STATE_RECORDING

    @property
    def is_paused(self) -> bool:
        return self._state == self.STATE_PAUSED

    @property
    def is_active(self) -> bool:
        return self._state in {self.STATE_RECORDING, self.STATE_PAUSED}

    def start(self) -> None:
        if self.is_active or self._state == self.STATE_PROCESSING:
            logger.info("Voice note start ignored: recorder already active")
            return

        if not self.can_record():
            self.error.emit("No hay microfono disponible.")
            return

        output_dir = Config.CACHE_DIR / "voice_notes"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._recording_path = output_dir / f"voice_note_{uuid4().hex}.wav"
        self._frames_written = 0
        logger.info("Starting voice note recording: %s", self._recording_path)

        try:
            device = QMediaDevices.defaultAudioInput()
            if hasattr(device, "isNull") and device.isNull():
                raise VoiceNoteConversionError("No hay microfono disponible.")

            self._audio_format = select_voice_note_format(device)
            self._open_wav_writer(self._recording_path, self._audio_format.sampleRate())
            self._audio_source = self._audio_source_factory(device, self._audio_format, self)
            self._audio_source.setBufferSize(
                max(4096, self._audio_format.bytesPerFrame() * 2048)
            )
            self._audio_source.stateChanged.connect(self._on_audio_state_changed)
            self._audio_device = self._audio_source.start()
            if self._audio_device is None:
                raise VoiceNoteConversionError("No se pudo abrir el microfono.")

            self._audio_device.readyRead.connect(self._read_pending_audio)
            self._set_state(self.STATE_RECORDING)
            self.recording_started.emit()
        except Exception as exc:  # noqa: BLE001
            self._cleanup_recording()
            self._teardown()
            self.error.emit(f"No se pudo iniciar la grabacion: {exc}")

    def pause(self) -> None:
        if self._state != self.STATE_RECORDING or self._audio_source is None:
            return

        self._read_pending_audio()
        self._audio_source.suspend()
        self._set_state(self.STATE_PAUSED)
        self.recording_paused.emit()

    def resume(self) -> None:
        if self._state != self.STATE_PAUSED or self._audio_source is None:
            return

        self._set_state(self.STATE_RECORDING)
        self._audio_source.resume()
        self.recording_resumed.emit()

    def finish(self) -> None:
        if not self.is_active:
            self.error.emit("No hay una nota de voz grabandose.")
            return

        logger.info("Finishing voice note recording: %s", self._recording_path)
        self._set_state(self.STATE_PROCESSING)
        source = self._recording_path

        try:
            self._stop_capture()
            if (
                source is None
                or self._frames_written <= 0
                or not source.exists()
                or source.stat().st_size <= 0
            ):
                raise VoiceNoteConversionError("La nota de voz esta vacia.")
            output = convert_wav_to_ogg_opus(source)
            logger.info("Voice note converted: %s -> %s", source, output)
            self._delete_path(source)
            self._recording_path = None
            self.ready.emit(str(output))
        except VoiceNoteConversionError as exc:
            self._cleanup_recording()
            logger.warning("Voice note conversion failed: %s", exc)
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self._cleanup_recording()
            logger.warning("Voice note finish failed: %s", exc)
            self.error.emit(f"No se pudo procesar la nota de voz: {exc}")
        finally:
            self._teardown()

    def cancel(self) -> None:
        if not self.is_active and self._state != self.STATE_PROCESSING:
            self._cleanup_recording()
            self.canceled.emit()
            return

        logger.info("Canceling voice note recording: %s", self._recording_path)
        self._set_state(self.STATE_PROCESSING)
        self._stop_capture()
        self._cleanup_recording()
        self._teardown()
        self.canceled.emit()

    def _open_wav_writer(self, path: Path, sample_rate: int) -> None:
        self._wav_writer = wave.open(str(path), "wb")
        self._wav_writer.setnchannels(_TARGET_CHANNELS)
        self._wav_writer.setsampwidth(_PCM16_WIDTH)
        self._wav_writer.setframerate(sample_rate)

    def _read_pending_audio(self) -> None:
        device = self._audio_device
        if device is None:
            return

        data = bytes(device.readAll())
        if not data or self._state != self.STATE_RECORDING:
            return

        self._handle_audio_bytes(data)

    def _handle_audio_bytes(self, data: bytes) -> None:
        if (
            self._state != self.STATE_RECORDING
            or self._audio_format is None
            or self._wav_writer is None
        ):
            return

        pcm_data = audio_chunk_to_pcm16_mono(data, self._audio_format)
        if not pcm_data:
            return

        self._wav_writer.writeframesraw(pcm_data)
        frames = len(pcm_data) // _PCM16_WIDTH
        self._frames_written += frames
        duration_ms = int((self._frames_written / self._audio_format.sampleRate()) * 1000)
        self.duration_changed.emit(duration_ms)
        self.level_changed.emit(calculate_pcm16_level(pcm_data))

    def _on_audio_state_changed(self, state) -> None:
        if state != QAudio.State.StoppedState or self._state == self.STATE_PROCESSING:
            return
        if self._audio_source is None:
            return
        if self._audio_source.error() == QAudio.Error.NoError:
            return

        audio_error = self._audio_source.error()
        self._cleanup_recording()
        self._teardown()
        logger.warning("Voice note audio source error: %s", audio_error)
        self.error.emit("No se pudo grabar la nota de voz.")

    def _stop_capture(self) -> None:
        if self._audio_source is not None:
            try:
                self._audio_source.stop()
            except Exception:  # noqa: BLE001 - keep cleanup running on stop errors
                logger.exception("Error stopping the microphone capture")
        # Always close the writer so the WAV handle is released and the temp file
        # can be deleted, even if stopping the audio source raised.
        self._close_wav_writer()

    def _close_wav_writer(self) -> None:
        writer = self._wav_writer
        self._wav_writer = None
        if writer is not None:
            writer.close()

    def _set_state(self, state: str) -> None:
        if self._state == state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _cleanup_recording(self) -> None:
        self._close_wav_writer()
        self._delete_path(self._recording_path)
        if self._recording_path is not None:
            self._delete_path(self._recording_path.with_suffix(".ogg"))
        self._recording_path = None

    def _delete_path(self, path: Path | None, *, attempt: int = 0) -> None:
        """Delete a temp recording, retrying on transient Windows file locks.

        The first attempt runs immediately; if the file is still locked the
        unlink is rescheduled (non-blocking) via ``QTimer`` so the GUI thread
        never freezes and cancelled recordings don't leak ``.wav`` files.
        """
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
            logger.info("Deleted temporary voice note: %s", path)
        except OSError as exc:
            if attempt + 1 < _DELETE_MAX_RETRIES:
                QTimer.singleShot(
                    _DELETE_RETRY_MS,
                    lambda: self._delete_path(path, attempt=attempt + 1),
                )
            else:
                logger.warning(
                    "No se pudo eliminar nota de voz temporal %s: %s", path, exc
                )

    def _teardown(self) -> None:
        self._audio_source = None
        self._audio_device = None
        self._audio_format = None
        self._wav_writer = None
        self._frames_written = 0
        self._set_state(self.STATE_IDLE)
