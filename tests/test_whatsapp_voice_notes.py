from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import voice_note_converter
from app.services.whatsapp_chat_service import WhatsAppChatService


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
