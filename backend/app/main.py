"""API FastAPI para Practice Mode (M3) y Live Mode (M4).

Practice Mode: el frontend pide una pregunta, la reproduce (TTS), graba la
respuesta del usuario como un blob de audio y lo sube completo. El backend
transcribe, evalúa (objetivo + LLM) y guarda el turno.

Live Mode: una sola sesión global (`app.live.manager.get_session`) captura
loopback + micrófono directo en el backend (no vía navegador — ver plan,
M4) y transmite eventos de texto por WebSocket (`/api/live/stream`).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.answers.store import load_answer
from app.asr.transcribe_file import transcribe_file
from app.config import settings
from app.live import db as live_db
from app.live import manager as live_manager
from app.practice import db, session as practice_session
from app.practice.evaluate import compute_objective_metrics, evaluate_with_llm
from app.practice.tts import synthesize_question
from app.profile.schema import CandidateProfile

SCRATCH_DIR = Path(__file__).resolve().parent.parent / "scratch"
TTS_CACHE_DIR = SCRATCH_DIR / "tts"
UPLOADS_DIR = SCRATCH_DIR / "uploads"

app = FastAPI(title="Asistente de Entrevistas — Practice Mode API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    live_db.init_db()
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/profile")
def get_profile() -> dict:
    return CandidateProfile.load(settings.profile_path).model_dump()


@app.get("/api/categories")
def get_categories() -> list[str]:
    return practice_session.list_categories()


@app.post("/api/practice/sessions")
def create_session() -> dict:
    return {"session_id": db.start_session()}


def _question_with_reference(question: dict) -> dict:
    result = dict(question)
    try:
        answer = load_answer(question["id"])
        result["reference"] = {
            "answer_en": answer["answer_en"],
            "keypoints": answer.get("keypoints", []),
            "reviewed": answer.get("reviewed", False),
        }
    except FileNotFoundError:
        result["reference"] = None
    return result


@app.get("/api/practice/questions/next")
def next_question(category: str | None = None, exclude: str = "") -> dict:
    exclude_ids = {qid for qid in exclude.split(",") if qid}
    question = practice_session.pick_question(category=category, exclude_ids=exclude_ids)
    if question is None:
        raise HTTPException(404, "No hay preguntas para esa categoría.")
    return _question_with_reference(question)


@app.get("/api/practice/questions/{question_id}/audio")
async def question_audio(question_id: str) -> FileResponse:
    questions = {q["id"]: q for q in practice_session.load_questions()}
    question = questions.get(question_id)
    if question is None:
        raise HTTPException(404, "Pregunta no encontrada.")

    cache_path = TTS_CACHE_DIR / f"{question_id}.mp3"
    if not cache_path.exists():
        await synthesize_question(question["question_en"], cache_path)
    return FileResponse(cache_path, media_type="audio/mpeg")


@app.post("/api/practice/sessions/{session_id}/turns")
async def submit_turn(
    session_id: str,
    question_id: str = Form(...),
    audio: UploadFile = File(...),
) -> dict:
    questions = {q["id"]: q for q in practice_session.load_questions()}
    question = questions.get(question_id)
    if question is None:
        raise HTTPException(404, "Pregunta no encontrada.")

    upload_path = UPLOADS_DIR / f"{uuid.uuid4()}_{audio.filename or 'answer.webm'}"
    upload_path.write_bytes(await audio.read())

    try:
        transcript, duration_seconds = transcribe_file(upload_path)
    finally:
        upload_path.unlink(missing_ok=True)

    objective = compute_objective_metrics(transcript, duration_seconds)

    llm_feedback: dict | None = None
    reference_answer_en = ""
    try:
        reference_answer_en = load_answer(question_id)["answer_en"]
    except FileNotFoundError:
        pass

    if reference_answer_en:
        try:
            profile = CandidateProfile.load(settings.profile_path)
            llm_feedback = await evaluate_with_llm(
                profile=profile,
                question_en=question["question_en"],
                reference_answer_en=reference_answer_en,
                user_transcript=transcript,
            )
        except Exception as exc:  # noqa: BLE001 - no tumbar el turno si el LLM falla
            llm_feedback = {"error": str(exc)}

    turn_id = db.record_turn(
        session_id=session_id,
        question_id=question_id,
        category=question["category"],
        transcript=transcript,
        words_per_minute=objective.words_per_minute,
        duration_seconds=objective.duration_seconds,
        pause_count=None,
        filler_count=objective.filler_count,
        llm_feedback=llm_feedback,
    )

    return {
        "turn_id": turn_id,
        "transcript": transcript,
        "objective": {
            "word_count": objective.word_count,
            "duration_seconds": objective.duration_seconds,
            "words_per_minute": objective.words_per_minute,
            "filler_count": objective.filler_count,
            "filler_breakdown": objective.filler_breakdown,
        },
        "llm_feedback": llm_feedback,
    }


@app.get("/api/practice/progress")
def get_progress(limit: int = 100) -> list[dict]:
    return db.get_progress(limit=limit)


@app.get("/api/practice/progress/weakest")
def get_weakest(limit: int = 5) -> list[dict]:
    return db.get_weakest_categories(limit=limit)


# --- Live Mode (M4) ---


@app.post("/api/live/sessions/start")
def start_live_session(language: str = "en") -> dict:
    """Idempotente: si ya había una sesión corriendo, la reinicia limpia
    en vez de rechazar con 409 — así un doble clic o repetir una prueba
    manual nunca deja la app atorada pidiendo un restart del backend.

    `language`: "en" (default) o "es" — elige el modelo de ASR, la
    dirección de traducción y el idioma de la respuesta sugerida. Ver
    app.live.manager y app.live.pipeline."""
    if language not in ("en", "es"):
        raise HTTPException(status_code=400, detail="language debe ser 'en' o 'es'")
    session = live_manager.get_session()
    session.start(language=language)
    return {"running": session.running, "language": session.language}


@app.post("/api/live/sessions/stop")
def stop_live_session() -> dict:
    session = live_manager.get_session()
    session.stop()
    return {"running": session.running}


@app.post("/api/live/sessions/full-answer")
def set_full_answer(enabled: bool) -> dict:
    """Prende/apaga la generación de respuesta completa. Apagado por
    defecto en cada sesión nueva — ver nota ética del plan, M4."""
    session = live_manager.get_session()
    session.generate_full_answer = enabled
    return {"generate_full_answer": session.generate_full_answer}


@app.get("/api/live/sessions/status")
def live_session_status() -> dict:
    session = live_manager.get_session()
    return {
        "running": session.running,
        "generate_full_answer": session.generate_full_answer,
        "language": session.language,
    }


@app.websocket("/api/live/stream")
async def live_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    session = live_manager.get_session()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    session.attach(loop, queue.put_nowait)

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass


@app.get("/api/live/sessions")
def get_live_sessions(limit: int = 50) -> list[dict]:
    return live_db.get_sessions(limit=limit)


@app.get("/api/live/turns")
def get_live_turns(session_id: str | None = None, limit: int = 200) -> list[dict]:
    return live_db.get_turns(session_id=session_id, limit=limit)
