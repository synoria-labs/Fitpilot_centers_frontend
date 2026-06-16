"""Audio conversion helpers for WhatsApp voice notes."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import imageio_ffmpeg


class VoiceNoteConversionError(RuntimeError):
    """Raised when a recorded audio file cannot be converted to OGG/Opus."""


def convert_wav_to_ogg_opus(
    source_path: str | Path,
    output_path: Optional[str | Path] = None,
) -> Path:
    """Convert a recorded WAV file to WhatsApp-compatible OGG/Opus."""
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise VoiceNoteConversionError("No se encontro el audio grabado.")

    output = Path(output_path) if output_path is not None else source.with_suffix(".ogg")
    output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
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
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise VoiceNoteConversionError(
            result.stderr.strip() or "No se pudo convertir la nota de voz."
        )
    if not output.exists() or output.stat().st_size <= 0:
        raise VoiceNoteConversionError(
            "La conversion de audio no genero un archivo valido."
        )
    return output
