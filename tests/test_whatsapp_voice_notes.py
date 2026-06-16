from __future__ import annotations

import subprocess
import struct
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtMultimedia import QAudioFormat

from app.services import voice_note_converter
from app.services.voice_note_converter import compute_waveform_bars
from app.services.whatsapp_chat_service import WhatsAppChatService
from app.views.tabs.whatsapp.composer_widget import ComposerWidget
from app.views.tabs.whatsapp.voice_note_recorder import (
    VoiceNoteRecorder,
    audio_chunk_to_pcm16_mono,
    calculate_pcm16_level,
)


class _FakeGraphQLClient:
    def __init__(self):
        self.calls = []
        self.last_error = None

    async def execute_multipart(
        self,
        query,
        variables,
        *,
        file_path,
        file_variable,
    ):
        self.calls.append(
            {
                "query": query,
                "variables": variables,
                "file_path": file_path,
                "file_variable": file_variable,
            }
        )
        return {
            "sendMediaMessage": {
                "success": True,
                "error": None,
                "message": None,
            }
        }


class _FakeAudioSource:
    def __init__(self):
        self.suspended = False
        self.resumed = False
        self.stopped = False

    def suspend(self):
        self.suspended = True

    def resume(self):
        self.resumed = True

    def stop(self):
        self.stopped = True


class _FakeWaveWriter:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def writeframesraw(self, data):
        self.data.extend(data)

    def close(self):
        self.closed = True


class _FakeVoiceRecorder(QObject):
    recording_started = Signal()
    recording_paused = Signal()
    recording_resumed = Signal()
    duration_changed = Signal(int)
    level_changed = Signal(float)
    ready = Signal(str)
    canceled = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []

    def start(self):
        self.calls.append("start")
        self.recording_started.emit()

    def pause(self):
        self.calls.append("pause")
        self.recording_paused.emit()

    def resume(self):
        self.calls.append("resume")
        self.recording_resumed.emit()

    def finish(self):
        self.calls.append("finish")

    def cancel(self):
        self.calls.append("cancel")
        self.canceled.emit()


def _audio_format(
    sample_format: QAudioFormat.SampleFormat = QAudioFormat.SampleFormat.Int16,
    *,
    channels: int = 1,
    sample_rate: int = 48000,
) -> QAudioFormat:
    audio_format = QAudioFormat()
    audio_format.setSampleRate(sample_rate)
    audio_format.setChannelCount(channels)
    audio_format.setSampleFormat(sample_format)
    return audio_format


@pytest.mark.asyncio
async def test_send_media_message_passes_voice_note_flag():
    client = _FakeGraphQLClient()
    service = WhatsAppChatService(client)

    result = await service.send_media_message(
        conversation_id=42,
        file_path="voice-note.ogg",
        voice_note=True,
    )

    assert result["success"] is True
    assert client.calls[0]["variables"]["input"] == {
        "conversationId": 42,
        "voiceNote": True,
    }


def test_audio_chunk_to_pcm16_mono_converts_float_stereo():
    audio_format = _audio_format(QAudioFormat.SampleFormat.Float, channels=2)
    source = struct.pack("<ffff", 1.0, 1.0, -1.0, -1.0)

    assert audio_chunk_to_pcm16_mono(source, audio_format) == struct.pack(
        "<hh",
        32767,
        -32768,
    )


def test_calculate_pcm16_level_uses_real_sample_energy():
    assert calculate_pcm16_level(b"") == 0.0
    assert calculate_pcm16_level(struct.pack("<hhhh", 0, 0, 0, 0)) == 0.0
    assert (
        0.0
        < calculate_pcm16_level(struct.pack("<hhhh", 1000, -1000, 1000, -1000))
        < 1.0
    )
    assert calculate_pcm16_level(struct.pack("<hh", 32767, -32768)) == pytest.approx(
        1.0
    )


def test_voice_note_recorder_pause_resume_excludes_paused_audio(qtbot):
    recorder = VoiceNoteRecorder()
    audio_source = _FakeAudioSource()
    writer = _FakeWaveWriter()
    durations = []

    recorder._audio_source = audio_source
    recorder._audio_format = _audio_format()
    recorder._wav_writer = writer
    recorder._state = VoiceNoteRecorder.STATE_RECORDING
    recorder.duration_changed.connect(durations.append)

    chunk = struct.pack("<" + "h" * 480, *([1000] * 480))
    recorder._handle_audio_bytes(chunk)
    recorder.pause()
    recorder._handle_audio_bytes(chunk)
    recorder.resume()
    recorder._handle_audio_bytes(chunk)

    assert audio_source.suspended is True
    assert audio_source.resumed is True
    assert len(writer.data) == 480 * 2 * 2
    assert durations == [10, 20]


def test_voice_note_recorder_finish_stops_and_converts(monkeypatch, tmp_path):
    recorder = VoiceNoteRecorder()
    audio_source = _FakeAudioSource()
    source = tmp_path / "voice.wav"
    output = tmp_path / "voice.ogg"
    ready = []

    writer = wave.open(str(source), "wb")
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(48000)
    writer.writeframesraw(struct.pack("<" + "h" * 480, *([1000] * 480)))

    def fake_convert(path):
        assert path == source
        output.write_bytes(b"ogg")
        return output

    monkeypatch.setattr(
        "app.views.tabs.whatsapp.voice_note_recorder.convert_wav_to_ogg_opus",
        fake_convert,
    )
    recorder._audio_source = audio_source
    recorder._recording_path = source
    recorder._wav_writer = writer
    recorder._frames_written = 480
    recorder._state = VoiceNoteRecorder.STATE_RECORDING
    recorder.ready.connect(ready.append)

    recorder.finish()

    assert audio_source.stopped is True
    assert ready == [str(output)]
    assert not source.exists()


def test_composer_pause_button_toggles_recorder(qtbot):
    fake_recorder = _FakeVoiceRecorder()
    widget = ComposerWidget(voice_recorder=fake_recorder)
    qtbot.addWidget(widget)
    widget.show()

    widget._start_voice_recording()
    qtbot.mouseClick(widget.pause_recording_button, Qt.MouseButton.LeftButton)
    assert fake_recorder.calls == ["start", "pause"]
    assert widget._recording_paused is True
    assert widget.pause_recording_button.toolTip() == "Reanudar nota de voz"

    qtbot.mouseClick(widget.pause_recording_button, Qt.MouseButton.LeftButton)
    assert fake_recorder.calls == ["start", "pause", "resume"]
    assert widget._recording_paused is False
    assert widget.pause_recording_button.toolTip() == "Pausar nota de voz"


def test_convert_wav_to_ogg_opus_uses_packaged_ffmpeg(monkeypatch, tmp_path):
    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "voice.ogg"
    captured = {}

    def fake_get_ffmpeg_exe():
        return "ffmpeg-bin"

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"ogg")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setitem(
        sys.modules,
        "imageio_ffmpeg",
        SimpleNamespace(get_ffmpeg_exe=fake_get_ffmpeg_exe),
    )
    monkeypatch.setattr(voice_note_converter.subprocess, "run", fake_run)

    result = voice_note_converter.convert_wav_to_ogg_opus(source, output)

    assert result == output
    assert captured["command"] == [
        "ffmpeg-bin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-application",
        "voip",
        str(output),
    ]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["check"] is False


def test_voice_note_recorder_delete_path_logs_on_success(tmp_path):
    recorder = VoiceNoteRecorder()
    target = tmp_path / "voice.wav"
    target.write_bytes(b"data")

    recorder._delete_path(target)

    assert not target.exists()


class _FlakyPath:
    """Path-like that fails ``unlink`` a fixed number of times, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.attempts = 0
        self.deleted = False

    def unlink(self, missing_ok: bool = False) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise OSError("file is locked")
        self.deleted = True


def test_voice_note_recorder_delete_path_retries_on_lock(qtbot):
    recorder = VoiceNoteRecorder()
    flaky = _FlakyPath(fail_times=2)

    recorder._delete_path(flaky)  # first attempt fails, schedules deferred retries

    qtbot.waitUntil(lambda: flaky.deleted, timeout=3000)
    assert flaky.attempts == 3


def _fake_ffmpeg(monkeypatch, returncode: int, stdout: bytes, stderr: bytes = b""):
    monkeypatch.setattr(
        voice_note_converter,
        "_load_imageio_ffmpeg",
        lambda: SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg-bin"),
    )

    def fake_run(command, **kwargs):
        assert command[0] == "ffmpeg-bin"
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(voice_note_converter.subprocess, "run", fake_run)


def test_compute_waveform_bars_returns_normalized_peaks(monkeypatch, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"ogg")
    pcm = struct.pack("<8h", 0, 8000, 0, 16000, 0, 24000, 0, 32000)
    _fake_ffmpeg(monkeypatch, 0, pcm)

    bars = compute_waveform_bars(source, bar_count=4)

    assert len(bars) == 4
    assert bars == sorted(bars)  # rising envelope
    assert bars[-1] == pytest.approx(1.0)  # loudest bucket fills the height
    assert all(0.0 <= bar <= 1.0 for bar in bars)


def test_compute_waveform_bars_returns_empty_on_ffmpeg_error(monkeypatch, tmp_path):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"ogg")
    _fake_ffmpeg(monkeypatch, 1, b"", b"boom")

    assert compute_waveform_bars(source, bar_count=8) == []


def test_compute_waveform_bars_returns_empty_for_missing_file(tmp_path):
    assert compute_waveform_bars(tmp_path / "nope.ogg") == []


def test_load_imageio_ffmpeg_installs_when_missing(monkeypatch):
    fake_module = SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg-bin")
    import_calls = []
    run_calls = []

    def fake_import_module(name):
        import_calls.append(name)
        if len(import_calls) == 1:
            raise ImportError("missing")
        return fake_module

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(voice_note_converter.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(voice_note_converter.subprocess, "run", fake_run)

    assert voice_note_converter._load_imageio_ffmpeg() is fake_module
    assert import_calls == ["imageio_ffmpeg", "imageio_ffmpeg"]
    assert run_calls[0][0] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "imageio-ffmpeg",
    ]
    assert run_calls[0][1]["shell"] is False
