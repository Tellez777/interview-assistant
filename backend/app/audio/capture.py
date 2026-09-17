"""Captura de audio: grabación simple a WAV y streaming de chunks PCM.

`record_to_wav` se usa hoy en el diagnóstico de M0 (verificar que el
loopback y el micrófono capturan lo correcto). `stream_chunks` es la pieza
que en M4 alimenta `RealtimeSTT.feed_audio()` en tiempo real.

IMPORTANTE (bug real encontrado y corregido — ver plan, M4):
`AudioToTextRecorder.feed_audio(chunk, original_sample_rate)` **ignora
por completo `original_sample_rate` cuando `chunk` es `bytes`** (ese
parámetro solo se usa en la rama de entrada `numpy.ndarray`, que sí
resamplea/reduce a mono internamente). Con bytes crudos, RealtimeSTT
asume que ya vienen en 16 kHz mono. Nuestros dispositivos capturan a
44100/48000 Hz en estéreo, así que alimentarlo sin convertir hace que
Whisper "escuche" el audio a la velocidad y tono equivocados — eso
explica una detección de voz pobre o inexistente en ambos canales.
`to_mono_16k_pcm16` hace la conversión real (downmix + resample) antes de
entregarle nada a RealtimeSTT.
"""

from __future__ import annotations

import threading
import wave
from collections.abc import Iterator
from math import gcd
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
from scipy.signal import resample_poly

from app.audio.devices import DeviceInfo

CHUNK_FRAMES = 1024
TARGET_SAMPLE_RATE = 16000


def to_mono_16k_pcm16(chunk: bytes, *, channels: int, sample_rate: int, gain: float = 1.0) -> bytes:
    """Convierte un chunk PCM int16 (posiblemente estéreo, a `sample_rate`)
    a mono 16 kHz int16 — el formato que RealtimeSTT asume siempre que se
    le pasan bytes crudos. Aplica `gain` en el mismo paso (más barato que
    hacer una pasada aparte) y recorta al rango de int16 al final.
    """
    samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)

    if channels > 1:
        # Intercalado (LRLRLR...) -> promedio de canales.
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    if sample_rate != TARGET_SAMPLE_RATE:
        g = gcd(TARGET_SAMPLE_RATE, sample_rate)
        up, down = TARGET_SAMPLE_RATE // g, sample_rate // g
        samples = resample_poly(samples, up, down)

    if gain != 1.0:
        samples = samples * gain

    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


def play_silence_keepalive(stop_event: threading.Event) -> None:
    """Mantiene un stream de silencio digital sonando en la salida por
    defecto mientras `stop_event` no esté marcado.

    Bug real de Windows encontrado en vivo (ver plan, M4): si nada se está
    reproduciendo por el sistema, WASAPI puede dejar de entregar buffers
    al stream de loopback — `stream.read()` se queda bloqueado durante
    minutos esperando datos que nunca llegan. Se confirmó midiendo CPU de
    un proceso de grabación de "silencio" que llevaba minutos vivo usando
    ~0% CPU: bloqueado en I/O, no procesando nada. Con un output activo
    (aunque sea silencio puro, inaudible) el motor de audio de Windows no
    se duerme y el loopback sigue entregando buffers en tiempo real,
    incluyendo los de silencio real que el VAD necesita ver para poder
    cerrar el turno.

    Corre en su propio hilo, iniciado junto con el resto de Live Mode
    (ver `app.live.manager`).
    """
    with pyaudio.PyAudio() as p:
        default_output = p.get_default_output_device_info()
        channels = max(int(default_output["maxOutputChannels"]), 1)
        rate = int(default_output["defaultSampleRate"])
        silent_chunk = b"\x00" * (CHUNK_FRAMES * channels * 2)  # int16 = 2 bytes/sample

        with p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            output=True,
            output_device_index=default_output["index"],
            frames_per_buffer=CHUNK_FRAMES,
        ) as stream:
            while not stop_event.is_set():
                stream.write(silent_chunk)


def record_to_wav(device: DeviceInfo, seconds: float, out_path: Path) -> Path:
    """Graba `seconds` segundos del dispositivo dado y los guarda en `out_path`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = pyaudio.paInt16
    channels = max(device.channels, 1)

    with pyaudio.PyAudio() as p:
        sample_size = p.get_sample_size(fmt)
        with p.open(
            format=fmt,
            channels=channels,
            rate=device.sample_rate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=CHUNK_FRAMES,
        ) as stream:
            frames = []
            total_chunks = int(device.sample_rate / CHUNK_FRAMES * seconds)
            for _ in range(total_chunks):
                frames.append(stream.read(CHUNK_FRAMES, exception_on_overflow=False))

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_size)
            wf.setframerate(device.sample_rate)
            wf.writeframes(b"".join(frames))

    return out_path


def stream_chunks(device: DeviceInfo, stop_event: threading.Event | None = None) -> Iterator[bytes]:
    """Generador de chunks PCM crudos desde `device`.

    Uso (M4): `for chunk in stream_chunks(loopback, stop_event): recorder.feed_audio(chunk, device.sample_rate)`.
    Sin `stop_event` es infinito y el llamador debe romper el loop él mismo
    (p. ej. con un `break`). Con `stop_event`, el generador termina solo en
    cuanto se marca el evento — es lo que usa `app.live.manager` para
    apagar los hilos de captura de forma ordenada.
    """
    fmt = pyaudio.paInt16
    channels = max(device.channels, 1)

    with pyaudio.PyAudio() as p:
        with p.open(
            format=fmt,
            channels=channels,
            rate=device.sample_rate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=CHUNK_FRAMES,
        ) as stream:
            while stop_event is None or not stop_event.is_set():
                yield stream.read(CHUNK_FRAMES, exception_on_overflow=False)
