"""Diagnóstico de entorno para M0.

Qué hace, en orden:
1. Lista dispositivos de entrada y dispositivos loopback WASAPI disponibles.
2. [solo modo interactivo, por defecto] Graba 30 s del loopback por defecto
   (reproduce un video/audio en inglés mientras corre esto) y 5 s del
   micrófono por defecto, para que TÚ confirmes de oído que cada uno
   capturó lo correcto. Esto requiere que lo corras en tu propia terminal;
   un agente no puede reproducir audio ni hablar por ti.
3. Reporta si CUDA está disponible para CTranslate2 (motor de faster-whisper).
4. Compara tiempo de transcripción con el modelo `small.en` en GPU (si hay
   CUDA) contra CPU int8, y calcula el real-time factor (RTF =
   tiempo_transcripcion / duracion_audio). RTF < 1 significa que transcribe
   más rápido de lo que dura el audio. Con --skip-recording usa un WAV
   sintético (generado con edge-tts) en vez de tu loopback grabado, para
   poder correr el benchmark sin intervención humana.

Uso:
    cd backend
    .venv\\Scripts\\python scripts\\check_env.py                  # completo, interactivo
    .venv\\Scripts\\python scripts\\check_env.py --skip-recording  # solo dispositivos + benchmark
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio.capture import record_to_wav
from app.audio.devices import (
    get_default_input,
    get_default_loopback,
    list_input_devices,
    list_loopback_devices,
)

SCRATCH_DIR = Path(__file__).resolve().parent.parent / "scratch"
LOOPBACK_WAV = SCRATCH_DIR / "loopback_check.wav"
MIC_WAV = SCRATCH_DIR / "mic_check.wav"
SYNTHETIC_WAV = SCRATCH_DIR / "synthetic_benchmark.wav"

SYNTHETIC_BENCHMARK_TEXT = (
    "Tell me about a difficult technical problem you faced in your previous job. "
    "One technical problem I faced was an issue where a system was sending multiple "
    "duplicate records in production. I investigated the cause, found that a retry "
    "mechanism was combined with an operation that was not idempotent, corrected the "
    "problem, and validated the solution. This also helped reduce HTTP response times "
    "between twenty and thirty percent. I always prefer to measure first and find the "
    "root cause before making random changes to a system that is already in production."
)


async def _make_synthetic_wav(out_path: Path) -> Path:
    """Genera un WAV de referencia con edge-tts, convertido a WAV desde el
    MP3 que produce, para poder benchmarkear la transcripción sin que un
    humano tenga que reproducir audio ni hablar."""
    import edge_tts

    mp3_path = out_path.with_suffix(".mp3")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=SYNTHETIC_BENCHMARK_TEXT, voice="en-US-EmmaMultilingualNeural")
    await communicate.save(str(mp3_path))

    # faster-whisper/ctranslate2 puede leer mp3 directamente (usa PyAV
    # internamente), así que no hace falta convertir a WAV de verdad.
    return mp3_path


def audio_duration_seconds(path: Path) -> float:
    """Duración del audio. Soporta WAV (stdlib) y cualquier formato que
    PyAV entienda (mp3, etc.) para el WAV sintético del benchmark."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()

    import av

    with av.open(str(path)) as container:
        return float(container.duration) / 1_000_000  # container.duration está en microsegundos


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def check_devices() -> tuple:
    section("Dispositivos de entrada")
    for d in list_input_devices():
        print(f"  [{d.index}] {d.name}  ({d.sample_rate} Hz, {d.channels} ch)")

    section("Dispositivos loopback (WASAPI)")
    for d in list_loopback_devices():
        print(f"  [{d.index}] {d.name}  ({d.sample_rate} Hz, {d.channels} ch)")

    try:
        default_loopback = get_default_loopback()
        print(f"\nLoopback por defecto: [{default_loopback.index}] {default_loopback.name}")
    except (OSError, LookupError) as exc:
        print(f"\nERROR: no se encontró loopback por defecto: {exc}")
        raise SystemExit(1)

    try:
        default_input = get_default_input()
        print(f"Micrófono por defecto: [{default_input.index}] {default_input.name}")
    except OSError as exc:
        print(f"\nERROR: no se encontró micrófono por defecto: {exc}")
        raise SystemExit(1)

    return default_loopback, default_input


def record_samples(default_loopback, default_input) -> None:
    section("Grabación de verificación")
    input(
        "Reproduce ahora un video/audio en inglés (YouTube, etc.) y presiona Enter "
        "para grabar 30 s del audio del sistema..."
    )
    record_to_wav(default_loopback, seconds=30.0, out_path=LOOPBACK_WAV)
    print(f"Guardado: {LOOPBACK_WAV}  -> ábrelo y confirma que se oye el video/audio, no tu voz.")

    input("\nAhora presiona Enter y habla al micrófono durante 5 s...")
    record_to_wav(default_input, seconds=5.0, out_path=MIC_WAV)
    print(f"Guardado: {MIC_WAV}  -> ábrelo y confirma que se oye tu voz.")


def check_cuda() -> bool:
    section("CUDA / CTranslate2")
    try:
        from app.cuda_dlls import register_cuda_dll_dirs

        register_cuda_dll_dirs()
        import ctranslate2

        n = ctranslate2.get_cuda_device_count()
        print(f"Dispositivos CUDA visibles para CTranslate2: {n}")
        return n > 0
    except Exception as exc:  # noqa: BLE001 - diagnóstico, queremos ver cualquier fallo
        print(f"No se pudo consultar CUDA vía ctranslate2: {exc}")
        return False


def benchmark_transcription(cuda_available: bool, audio_path: Path) -> None:
    section(f"Benchmark de transcripción (small.en, {audio_path.name})")
    if not audio_path.exists():
        print(f"No existe {audio_path}; se omite el benchmark.")
        return

    duration = audio_duration_seconds(audio_path)
    from app.cuda_dlls import register_cuda_dll_dirs

    register_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    configs = []
    if cuda_available:
        configs.append(("cuda", "int8_float16"))
    configs.append(("cpu", "int8"))

    results = {}
    for device, compute_type in configs:
        label = f"{device}/{compute_type}"
        try:
            t0 = time.perf_counter()
            model = WhisperModel("small.en", device=device, compute_type=compute_type)
            t_load = time.perf_counter() - t0

            t0 = time.perf_counter()
            segments, _ = model.transcribe(str(audio_path), language="en")
            text = " ".join(s.text for s in segments)
            t_transcribe = time.perf_counter() - t0

            rtf = t_transcribe / duration if duration else float("inf")
            results[label] = (t_load, t_transcribe, rtf)
            print(f"\n[{label}]")
            print(f"  Carga del modelo: {t_load:.2f}s")
            print(f"  Transcripción:    {t_transcribe:.2f}s  (RTF = {rtf:.2f})")
            print(f"  Texto: {text.strip()[:200]}...")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{label}] FALLÓ: {exc}")
            if device == "cuda":
                print(
                    "  Sugerencia: instala nvidia-cublas-cu12 y nvidia-cudnn-cu12 vía pip, "
                    "o usa ASR_DEVICE=cpu en .env si sigue fallando."
                )

    if results:
        section("Recomendación")
        best = min(results.items(), key=lambda kv: kv[1][1])
        print(f"Más rápido: {best[0]} -> configura ASR_DEVICE y ASR_COMPUTE_TYPE acorde en backend/.env")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-recording",
        action="store_true",
        help="omite la grabación interactiva (loopback/mic) y usa un WAV sintético para el benchmark",
    )
    args = parser.parse_args()

    default_loopback, default_input = check_devices()

    if args.skip_recording:
        section("Grabación de verificación (omitida con --skip-recording)")
        print(
            "IMPORTANTE: esto NO confirma que el loopback capture correctamente tu audio del "
            "sistema. Corre este script sin --skip-recording, en tu propia terminal, para "
            "verificarlo de oído antes de dar M0 por bueno."
        )
        benchmark_path = asyncio.run(_make_synthetic_wav(SYNTHETIC_WAV))
    else:
        record_samples(default_loopback, default_input)
        benchmark_path = LOOPBACK_WAV

    cuda_available = check_cuda()
    benchmark_transcription(cuda_available, benchmark_path)
    section("Listo")
    print("Revisa los tiempos de arriba y, si no usaste --skip-recording, los WAV en backend/scratch/.")


if __name__ == "__main__":
    main()
