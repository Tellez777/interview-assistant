"""Historial de sesiones Live en SQLite (mismo patrón que `app.practice.db`).

Guarda cada turno del entrevistador — transcripción, traducción,
keypoints, y la respuesta sugerida (si estaba encendida) — para poder
evaluar qué tan bien está funcionando el pipeline en uso real, no solo en
pruebas sintéticas. Fernando lo pidió explícitamente después de notar que
la respuesta sugerida salió en español un par de veces: sin esto, no hay
forma de revisar después qué pasó exactamente en cada turno.

Se guarda en dos pasos (no todo de una vez), porque un turno se procesa
por etapas y algunas pueden tardar o cancelarse a medio camino:
1. `record_turn_start` — en cuanto se cierra el turno (transcripción
   final), antes de traducir/buscar/generar nada.
2. `update_turn` — se llama varias veces según van llegando traducción,
   keypoints y la respuesta, con los campos que ya estén listos en ese
   momento. Si el turno se cancela a medio camino (pregunta nueva llegó
   antes), el registro queda con lo que sí alcanzó a completarse — eso en
   sí mismo es información útil para evaluar el pipeline.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    stopped_at REAL,
    language TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS live_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES live_sessions(id),
    created_at REAL NOT NULL,
    question_en TEXT NOT NULL,
    translation_es TEXT,
    keypoints_json TEXT,
    keypoints_source_id TEXT,
    keypoints_score REAL,
    answer_mode TEXT,
    answer_text TEXT,
    answer_language TEXT,
    answer_language_ok INTEGER,
    marks_ms_json TEXT,
    error TEXT
);
"""


@contextmanager
def _connect():
    settings.live_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.live_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        # Migración liviana: si la tabla ya existía de antes de agregar
        # `language`, `CREATE TABLE IF NOT EXISTS` no la agrega sola.
        try:
            conn.execute("ALTER TABLE live_sessions ADD COLUMN language TEXT DEFAULT 'en'")
        except sqlite3.OperationalError:
            pass  # ya existe


def start_session(session_id: str, language: str = "en") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO live_sessions (id, started_at, language) VALUES (?, ?, ?)",
            (session_id, time.time(), language),
        )


def stop_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE live_sessions SET stopped_at = ? WHERE id = ?",
            (time.time(), session_id),
        )


def record_turn_start(*, session_id: str, turn_id: str, question_en: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO live_turns (id, session_id, created_at, question_en) VALUES (?, ?, ?, ?)",
            (turn_id, session_id, time.time(), question_en),
        )


def update_turn(turn_id: str, **fields) -> None:
    """Actualiza solo los campos dados. `keypoints_json`/`marks_ms_json`
    se aceptan como objetos Python (se serializan aquí), no como texto."""
    if "keypoints" in fields:
        fields["keypoints_json"] = json.dumps(fields.pop("keypoints"), ensure_ascii=False)
    if "marks_ms" in fields:
        fields["marks_ms_json"] = json.dumps(fields.pop("marks_ms"), ensure_ascii=False)
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE live_turns SET {set_clause} WHERE id = ?", (*fields.values(), turn_id))


def _row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    if item.get("keypoints_json"):
        item["keypoints"] = json.loads(item.pop("keypoints_json"))
    else:
        item["keypoints"] = None
        item.pop("keypoints_json", None)
    if item.get("marks_ms_json"):
        item["marks_ms"] = json.loads(item.pop("marks_ms_json"))
    else:
        item["marks_ms"] = None
        item.pop("marks_ms_json", None)
    return item


def get_sessions(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.started_at, s.stopped_at, s.language, COUNT(t.id) AS turn_count
            FROM live_sessions s
            LEFT JOIN live_turns t ON t.session_id = s.id
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_turns(session_id: str | None = None, limit: int = 200) -> list[dict]:
    with _connect() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM live_turns WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM live_turns ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_dict(r) for r in rows]
