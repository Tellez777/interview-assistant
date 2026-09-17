"""Tipos de mensajes que viajan por el WebSocket de Live Mode.

Son simples dicts serializables a JSON — no hace falta pydantic aquí, son
mensajes de un solo uso, no datos que se validan o persisten. Cada
constructor deja claro qué forma tiene cada tipo de evento para quien lea
`live/pipeline.py` o el frontend (`useLiveSocket.ts`).

`channel` distingue de quién es la voz: "interviewer" (loopback) o
"candidate" (micrófono de Fernando).
"""

from __future__ import annotations

from typing import Any, Literal

Channel = Literal["interviewer", "candidate"]


def partial_transcript(channel: Channel, text: str) -> dict[str, Any]:
    return {"type": "partial_en", "channel": channel, "text": text}


def final_transcript(channel: Channel, turn_id: str, text: str) -> dict[str, Any]:
    return {"type": "final_en", "channel": channel, "turn_id": turn_id, "text": text}


def translation(turn_id: str, text: str) -> dict[str, Any]:
    return {"type": "translation_es", "turn_id": turn_id, "text": text}


def keypoints(turn_id: str, points: list[str], source_id: str | None, score: float) -> dict[str, Any]:
    return {
        "type": "keypoints",
        "turn_id": turn_id,
        "keypoints": points,
        "source_id": source_id,
        "score": round(score, 3),
    }


def answer_start(turn_id: str, mode: Literal["cached", "llm", "technical"]) -> dict[str, Any]:
    return {"type": "answer_start", "turn_id": turn_id, "mode": mode}


def answer_chunk(turn_id: str, delta: str) -> dict[str, Any]:
    return {"type": "answer_chunk", "turn_id": turn_id, "delta": delta}


def answer_done(turn_id: str) -> dict[str, Any]:
    return {"type": "answer_done", "turn_id": turn_id}


def metrics(turn_id: str, marks_ms: dict[str, float]) -> dict[str, Any]:
    return {"type": "metrics", "turn_id": turn_id, "marks_ms": marks_ms}


def status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}
