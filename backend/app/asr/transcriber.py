"""Wrapper delgado sobre RealtimeSTT.

RealtimeSTT ya resuelve lo difícil (VAD con Silero, parciales en tiempo
real, detección de fin de turno vía `post_speech_silence_duration`), así
que este módulo solo lo configura según `Settings` y expone una interfaz
mínima: alimentar audio y recibir callbacks de texto parcial/final.

Referencia API: docs de RealtimeSTT vía Context7 (sesión 2026-09-16) —
`AudioToTextRecorder(use_microphone=False, enable_realtime_transcription=True,
on_realtime_transcription_update=...)` + `feed_audio(chunk, original_sample_rate=...)`.
"""

from __future__ import annotations

from collections.abc import Callable

from RealtimeSTT import AudioToTextRecorder

from app.config import settings


def make_recorder(
    *,
    on_partial: Callable[[str], None] | None = None,
    on_final: Callable[[str], None] | None = None,
    language: str = "en",
    model: str | None = None,
    realtime_model: str | None = None,
    post_speech_silence_duration: float | None = None,
    silero_sensitivity: float | None = None,
) -> AudioToTextRecorder:
    """Crea un recorder configurado para audio externo (no micrófono directo
    de RealtimeSTT: en M4 el audio viene de `app.audio.capture`, ya sea del
    loopback del entrevistador o del micrófono de Fernando, para poder tener
    dos instancias independientes, una por canal).

    `model`/`realtime_model` sobreescriben los de `Settings` — los usa Live
    Mode en español (`app.live.manager`) para cargar los pesos multilingües
    (`small`/`tiny`) en vez de los especializados en inglés (`small.en`/
    `tiny.en`), que no pueden transcribir otro idioma en absoluto.
    """
    return AudioToTextRecorder(
        use_microphone=False,
        language=language,
        model=model or settings.asr_model,
        device=settings.asr_device,
        compute_type=settings.asr_compute_type,
        enable_realtime_transcription=True,
        realtime_model_type=realtime_model or settings.asr_realtime_model,
        on_realtime_transcription_update=on_partial,
        # OJO: NO pasar silero_use_onnx=True aquí. Contraintuitivamente,
        # pasar ese flag explícito (True o False) fuerza el backend
        # "legacy" de RealtimeSTT, que siempre pasa por torch.hub.load(...)
        # — y eso pide confirmar "repo de confianza" con input(), lo cual
        # truena con EOFError en un servidor sin terminal interactiva.
        # Dejar el parámetro fuera (default None) activa el backend "auto",
        # que prueba ONNX Runtime vía el paquete pip `silero-vad` primero y
        # nunca toca la red ni pide confirmación. Ver plan, M4.
        silero_deactivity_detection=True,
        # 0.6s (el valor original) corta preguntas largas en varios turnos
        # ante cualquier pausa natural del habla — se detectó al probar con
        # una pregunta real de ChatGPT Voice. 1.1s tolera esas pausas sin
        # sentirse laggy al cerrar el turno de verdad.
        post_speech_silence_duration=post_speech_silence_duration or 1.1,
        # OJO: NO subir silero_sensitivity/bajar webrtc_sensitivity "para
        # compensar" un micrófono bajo — se probó (0.6 / 1) y el VAD
        # empezó a alucinar turnos sobre puro silencio/ruido ("You", "The
        # the.", sin que nadie hablara). El problema real del micrófono
        # bajo era otro: `feed_audio()` con bytes ignora el sample rate y
        # asume 16kHz mono, y nuestros dispositivos son estéreo a 44.1/48
        # kHz — sin convertir, Whisper "oía" todo a la velocidad y tono
        # equivocados (ver `app.audio.capture.to_mono_16k_pcm16`). Con eso
        # corregido, la sensibilidad por defecto de RealtimeSTT ya es
        # razonable; el gain de `app.audio.capture` sigue ayudando al
        # micrófono, ahora sobre audio ya bien convertido.
        silero_sensitivity=silero_sensitivity if silero_sensitivity is not None else 0.4,
    )


def transcribe_stream(recorder: AudioToTextRecorder, on_final: Callable[[str], None]) -> None:
    """Bloquea esperando el siguiente turno final y lo entrega a `on_final`.

    Uso previsto en M4: correr esto en un hilo/tarea por canal, en loop,
    junto con `app.audio.capture.stream_chunks(device)` alimentando
    `recorder.feed_audio(chunk, device.sample_rate)` desde otro hilo.
    """
    text = recorder.text()
    on_final(text)
