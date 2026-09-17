"""Historial de sesiones de práctica en SQLite (stdlib, sin dependencia extra).

Guarda cada turno (pregunta + respuesta hablada + evaluación) para que el
panel de progreso (M3, frontend) pueda mostrar WPM a lo largo del tiempo,
categorías más débiles y errores que se repiten.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    question_id TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at REAL NOT NULL,
    transcript TEXT NOT NULL,
    words_per_minute REAL,
    duration_seconds REAL,
    pause_count INTEGER,
    filler_count INTEGER,
    llm_feedback_json TEXT
);
"""


@contextmanager
def _connect():
    settings.practice_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.practice_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def start_session() -> str:
    session_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, started_at) VALUES (?, ?)",
            (session_id, time.time()),
        )
    return session_id


def record_turn(
    *,
    session_id: str,
    question_id: str,
    category: str,
    transcript: str,
    words_per_minute: float | None,
    duration_seconds: float | None,
    pause_count: int | None,
    filler_count: int | None,
    llm_feedback: dict | None,
) -> str:
    turn_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO turns (
                id, session_id, question_id, category, created_at, transcript,
                words_per_minute, duration_seconds, pause_count, filler_count,
                llm_feedback_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                question_id,
                category,
                time.time(),
                transcript,
                words_per_minute,
                duration_seconds,
                pause_count,
                filler_count,
                json.dumps(llm_feedback, ensure_ascii=False) if llm_feedback else None,
            ),
        )
    return turn_id


def get_progress(limit: int = 100) -> list[dict]:
    """Turnos más recientes primero, con el feedback del LLM ya deserializado."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM turns ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        if item["llm_feedback_json"]:
            item["llm_feedback"] = json.loads(item.pop("llm_feedback_json"))
        else:
            item["llm_feedback"] = None
            item.pop("llm_feedback_json", None)
        result.append(item)
    return result


def get_weakest_categories(limit: int = 5) -> list[dict]:
    """Categorías con menor words_per_minute promedio (proxy simple de fluidez)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT category, AVG(words_per_minute) AS avg_wpm, COUNT(*) AS attempts
            FROM turns
            WHERE words_per_minute IS NOT NULL
            GROUP BY category
            ORDER BY avg_wpm ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
