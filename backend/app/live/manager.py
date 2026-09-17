"""Ciclo de vida de la sesión Live. Una sola sesión global — en esta
laptop solo hay una entrevista a la vez, así que no hace falta un
registro de sesiones concurrentes (ver plan, M4).

Solo se captura el canal del entrevistador (loopback del sistema). El
canal del micrófono de Fernando se probó y se descartó: en la práctica,
sin audífonos, el micrófono capta acústicamente el audio de las bocinas
(las mismas bocinas por las que sale la voz del entrevistador) y termina
transcribiendo una mezcla ilegible de ambas voces — no aporta nada que
Practice Mode no cubra ya, así que no vale la complejidad de mantenerlo.

Dos hilos por sesión:
- `capture_loop`: lee chunks de `app.audio.capture.stream_chunks` y los
  entrega a `recorder.feed_audio()`. Bloqueante por diseño (E/S de audio),
  por eso vive en su propio hilo, no en el event loop de asyncio.
- `final_loop`: llama a `recorder.text()` (bloqueante: espera a que
  RealtimeSTT cierre el turno vía VAD) y, al volver, agenda el
  procesamiento del turno en el event loop principal con
  `asyncio.run_coroutine_threadsafe` — ahí es donde vive
  `app.live.pipeline.handle_interviewer_turn`.

Los parciales (`on_realtime_transcription_update`) llegan desde un hilo
interno de RealtimeSTT; `_emit` los puentea hacia el WebSocket con
`loop.call_soon_threadsafe`, que es la forma segura de cruzar de un hilo
normal al event loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import uuid
from collections.abc import Callable

from app.answers.retrieve import search
from app.asr.transcriber import make_recorder
from app.audio.capture import play_silence_keepalive, stream_chunks, to_mono_16k_pcm16
from app.audio.devices import get_default_loopback
from app.live import db as live_db
from app.live import events, pipeline
from app.metrics import Timeline
from app.config import settings
from app.translation.translate import translate_en_to_es, translate_es_to_en


def _force_kill_process(process: object) -> None:
    """Termina un `multiprocessing.Process` de RealtimeSTT si sigue vivo.

    Red de seguridad post-`recorder.shutdown()` — ver nota en `stop()`.
    `process` puede ser `None` o no tener `is_alive`/`terminate` según la
    versión/estado interno de RealtimeSTT, de ahí los `getattr`.
    """
    is_alive = getattr(process, "is_alive", None)
    if process is None or not callable(is_alive) or not is_alive():
        return
    terminate = getattr(process, "terminate", None)
    if callable(terminate):
        terminate()
    join = getattr(process, "join", None)
    if callable(join):
        join(timeout=3)
    if is_alive():
        kill = getattr(process, "kill", None)
        if callable(kill):
            kill()


class LiveSession:
    def __init__(self) -> None:
        self.running = False
        self.generate_full_answer = False

        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._recorder = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._emit_fn: Callable[[dict], None] | None = None
        # Turno del entrevistador actualmente en proceso (traducción/
        # retrieval/LLM). Si llega uno nuevo antes de que termine, se
        # cancela el anterior — ver nota en start().
        self._current_turn_future: concurrent.futures.Future | None = None
        self.session_id: str | None = None
        # Historias/keypoints usados recientemente en esta sesión, para
        # que el LLM no repita siempre la misma — ver app.live.pipeline.
        self.recent_source_ids: list[str] = []
        # "en" (default, todo lo ya validado) o "es" — se elige en el
        # frontend antes de dar "Iniciar" (ver plan, M4, sección
        # "¿preparado para español?"). Controla el modelo de ASR, la
        # dirección de traducción, qué campo del banco se usa como
        # respuesta cacheada, y el idioma del prompt del LLM.
        self.language: str = "en"

    def attach(self, loop: asyncio.AbstractEventLoop, emit_fn: Callable[[dict], None]) -> None:
        """`emit_fn` normalmente empuja el evento a un `asyncio.Queue` que
        el WebSocket está leyendo. Se vuelve a llamar en cada nueva
        conexión del frontend."""
        self._loop = loop
        self._emit_fn = emit_fn

    def _emit(self, event: dict) -> None:
        if self._loop is not None and self._emit_fn is not None:
            self._loop.call_soon_threadsafe(self._emit_fn, event)

    def start(self, *, language: str = "en") -> None:
        # Idempotente a propósito: si ya había una sesión corriendo, se
        # apaga limpio y se levanta una nueva en vez de rechazar con 409.
        # Antes de esto, un 409 atorado obligaba a reiniciar el backend a
        # mano cada vez que se quería repetir una prueba manual.
        if self.running:
            self.stop()

        # OJO: NO resetear self.generate_full_answer aquí. El frontend ya
        # lo manda en False en cada carga de página (ver LiveView.tsx) —
        # eso es lo que cumple la postura de "apagado por defecto" del
        # plan (M4). Resetearlo también aquí rompe el flujo normal de
        # "marcar el toggle y luego dar Iniciar", porque el checkbox llama
        # a /full-answer ANTES de que se llame a /start.

        self.language = language
        self._stop_event.clear()
        self.session_id = str(uuid.uuid4())
        self.recent_source_ids = []
        live_db.start_session(self.session_id, language=self.language)
        self._emit(events.status("Calentando modelos (traducción, retrieval)..."))

        # Evita que la primera traducción/búsqueda real de la sesión pague
        # el costo de cargar el modelo (~7 s medido para argostranslate).
        # En modo español se calienta también la dirección es→en, que es
        # la que usa el retrieval contra el banco (indexado en inglés) —
        # ver app.live.pipeline.
        translate_en_to_es("warmup")
        if self.language == "es":
            translate_es_to_en("calentamiento")
        search("warmup", top_k=1)

        loopback = get_default_loopback()

        # Ver docstring de `play_silence_keepalive`: sin esto, WASAPI deja
        # de entregar audio al loopback en cuanto no hay nada sonando en
        # el sistema, y el turno del entrevistador nunca llega a cerrar.
        keepalive_thread = threading.Thread(
            target=play_silence_keepalive, args=(self._stop_event,), daemon=True, name="live-keepalive"
        )
        keepalive_thread.start()

        def _log_partial(text: str) -> None:
            # DEBUG temporal (ver plan, M4): imprime cada parcial a stdout
            # para poder comparar contra lo que muestra el frontend.
            print(f"[live:interviewer] partial: {text!r}", flush=True)
            self._emit(events.partial_transcript("interviewer", text))

        # Los modelos ".en" (ver Settings.asr_model) son especializados en
        # inglés y no transcriben otro idioma en absoluto — en modo "es"
        # hace falta el multilingüe (small/tiny), no solo cambiar la
        # bandera `language`.
        asr_model = settings.asr_model if self.language == "en" else settings.asr_model_es
        asr_realtime_model = (
            settings.asr_realtime_model if self.language == "en" else settings.asr_realtime_model_es
        )
        recorder = make_recorder(
            on_partial=_log_partial,
            language=self.language,
            model=asr_model,
            realtime_model=asr_realtime_model,
        )
        self._recorder = recorder

        def capture_loop() -> None:
            for chunk in stream_chunks(loopback, self._stop_event):
                converted = to_mono_16k_pcm16(
                    chunk, channels=loopback.channels, sample_rate=loopback.sample_rate
                )
                recorder.feed_audio(converted)

        def final_loop() -> None:
            while not self._stop_event.is_set():
                text = recorder.text()
                print(f"[live:interviewer] FINAL: {text!r}", flush=True)
                if self._stop_event.is_set() or not text or not text.strip():
                    continue

                turn_id = str(uuid.uuid4())
                self._emit(events.final_transcript("interviewer", turn_id, text))
                if self.session_id is not None:
                    live_db.record_turn_start(session_id=self.session_id, turn_id=turn_id, question_en=text)

                if self._loop is None:
                    continue

                # Si el turno anterior seguía traduciendo/generando
                # respuesta cuando llegó este, cancelarlo. Sin esto, dos
                # turnos consecutivos (frecuentes cuando el VAD fragmenta
                # una pregunta larga) terminan compartiendo el mismo
                # stream del LLM y truenan con "async generator already
                # executing" — el bug detrás de que la respuesta sugerida
                # se quedara sin funcionar.
                if self._current_turn_future is not None and not self._current_turn_future.done():
                    self._current_turn_future.cancel()

                self._current_turn_future = asyncio.run_coroutine_threadsafe(
                    pipeline.handle_interviewer_turn(
                        turn_id=turn_id,
                        text=text,
                        emit=self._emit,
                        generate_full_answer=self.generate_full_answer,
                        timeline=Timeline(),
                        recent_source_ids=self.recent_source_ids,
                        language=self.language,
                    ),
                    self._loop,
                )

        capture_thread = threading.Thread(target=capture_loop, daemon=True, name="live-capture-interviewer")
        final_thread = threading.Thread(target=final_loop, daemon=True, name="live-final-interviewer")
        capture_thread.start()
        final_thread.start()
        self._threads = [capture_thread, final_thread, keepalive_thread]

        self.running = True
        lang_label = "español" if self.language == "es" else "inglés"
        self._emit(events.status(f"Live Mode activo ({lang_label}) — entrevistador: {loopback.name}"))

    def stop(self) -> None:
        if not self.running:
            return
        if self._current_turn_future is not None and not self._current_turn_future.done():
            self._current_turn_future.cancel()
        self._stop_event.set()
        if self._recorder is not None:
            try:
                self._recorder.shutdown()
            except Exception:  # noqa: BLE001 - no dejar que un shutdown roto tumbe el resto
                pass
            # Red de seguridad: se detectó (con nvidia-smi, VRAM subiendo a
            # 3.3/4 GB tras varios ciclos start/stop) que el proceso worker
            # de faster-whisper de RealtimeSTT a veces sobrevive a
            # `recorder.shutdown()` y se queda residente en la GPU. Se
            # mata explícito por si acaso, en vez de confiar únicamente en
            # la limpieza interna de la librería. Ver plan, M4.
            _force_kill_process(getattr(self._recorder, "transcript_process", None))
            _force_kill_process(getattr(self._recorder, "reader_process", None))
        self._recorder = None
        self._threads.clear()
        self.running = False
        if self.session_id is not None:
            live_db.stop_session(self.session_id)
        self._emit(events.status("Live Mode detenido"))


_session: LiveSession | None = None


def get_session() -> LiveSession:
    global _session
    if _session is None:
        _session = LiveSession()
    return _session
