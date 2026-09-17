"""Transcripción de un archivo de audio ya grabado (no streaming).

Se usa en Practice Mode (M3): el navegador graba la respuesta completa del
usuario como un blob (webm/opus) y se sube de una vez, así que no hace
falta la maquinaria de streaming/VAD de RealtimeSTT — basta con
faster-whisper directo, que es lo mismo que ya validamos en
`scripts/check_env.py`.

El streaming de verdad (RealtimeSTT + feed_audio) es para M4 (Live Mode),
ver `app/asr/transcriber.py`.
"""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from app.config import settings

_model: WhisperModel | None = None
_model_device: str = ""


def _get_model() -> WhisperModel:
    """Carga el modelo una sola vez (singleton de proceso). Si el device
    configurado (p. ej. cuda) falla por falta de librerías del sistema,
    cae a CPU en vez de tumbar el endpoint — mismo criterio que
    check_env.py."""
    global _model, _model_device
    if _model is not None:
        return _model

    try:
        _model = WhisperModel(
            settings.asr_model, device=settings.asr_device, compute_type=settings.asr_compute_type
        )
        _model_device = settings.asr_device
    except Exception as exc:  # noqa: BLE001
        print(f"[transcribe_file] Fallback a CPU: {exc}")
        _model = WhisperModel(settings.asr_model, device="cpu", compute_type="int8")
        _model_device = "cpu"

    return _model


def audio_duration_seconds(path: Path) -> float:
    import av

    with av.open(str(path)) as container:
        return float(container.duration) / 1_000_000


def transcribe_file(path: Path, language: str = "en") -> tuple[str, float]:
    """Devuelve (texto_transcrito, duración_segundos)."""
    model = _get_model()
    segments, _ = model.transcribe(str(path), language=language)
    text = " ".join(segment.text.strip() for segment in segments)
    duration = audio_duration_seconds(path)
    return text.strip(), duration
