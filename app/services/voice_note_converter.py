"""Audio conversion helpers for WhatsApp voice notes."""
from __future__ import annotations

import array
import importlib
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)

# Low sample rate used only to build the visual waveform: plenty of resolution
# for an envelope while keeping the decoded buffer tiny (a few KB per note).
_WAVEFORM_SAMPLE_RATE = 8000
_WAVEFORM_DEFAULT_BARS = 48


class VoiceNoteConversionError(RuntimeError):
    """Raised when a recorded audio file cannot be converted to OGG/Opus."""


def _load_imageio_ffmpeg():
    try:
        return importlib.import_module("imageio_ffmpeg")
    except ImportError:
        logger.warning("imageio-ffmpeg is missing; attempting runtime install")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "imageio-ffmpeg"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise VoiceNoteConversionError(
            "Falta instalar imageio-ffmpeg en el entorno del frontend. "
            "Ejecuta: python -m pip install -r requirements.txt"
            + (f"\n\nDetalle: {details}" if details else "")
        )

    try:
        return importlib.import_module("imageio_ffmpeg")
    except ImportError as exc:
        raise VoiceNoteConversionError(
            "imageio-ffmpeg se instalo, pero Python no pudo importarlo. "
            "Reinicia el frontend e intenta de nuevo."
        ) from exc


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

    imageio_ffmpeg = _load_imageio_ffmpeg()

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


def compute_waveform_bars(
    audio_path: str | Path,
    bar_count: int = _WAVEFORM_DEFAULT_BARS,
) -> List[float]:
    """Decode an audio file and return ``bar_count`` normalized peaks (0..1).

    Used to draw a real waveform for chat audio bubbles. The file is decoded
    with the packaged ffmpeg to low-rate PCM16 mono, then split into evenly
    sized buckets whose peak amplitude becomes each bar's height. Returns an
    empty list on any failure so the caller can fall back to a flat skeleton.

    Safe to call off the GUI thread (blocking subprocess + pure-Python math).
    """
    source = Path(audio_path)
    bar_count = max(1, int(bar_count))
    if not source.exists() or not source.is_file():
        return []

    try:
        imageio_ffmpeg = _load_imageio_ffmpeg()
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            str(_WAVEFORM_SAMPLE_RATE),
            "-f",
            "s16le",
            "-",
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
    except Exception as exc:  # noqa: BLE001 - ffmpeg missing/unavailable
        logger.debug("No se pudo calcular la onda de %s: %s", source, exc)
        return []

    if result.returncode != 0:
        logger.debug(
            "ffmpeg no pudo decodificar la onda de %s: %s",
            source,
            (result.stderr or b"").decode("utf-8", "replace").strip(),
        )
        return []

    pcm = result.stdout or b""
    usable = len(pcm) - (len(pcm) % 2)  # whole int16 samples only
    if usable <= 0:
        return []

    samples = array.array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":  # ffmpeg emits little-endian s16le
        samples.byteswap()

    total = len(samples)
    bars: List[float] = []
    for index in range(bar_count):
        start = (index * total) // bar_count
        end = max(start + 1, ((index + 1) * total) // bar_count)
        peak = 0
        for value in samples[start:end]:
            magnitude = -value if value < 0 else value
            if magnitude > peak:
                peak = magnitude
        bars.append(peak / 32768.0)

    loudest = max(bars)
    if loudest <= 0.0:
        return []

    # Normalize so the loudest bar fills the height, then soften the curve a
    # little so quiet passages stay visible (matches the live recorder bars).
    return [min(1.0, (bar / loudest) ** 0.85) for bar in bars]
