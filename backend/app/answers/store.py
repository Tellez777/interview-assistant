"""Índice de embeddings sobre el banco de respuestas generado en `generate.py`.

Se corre una vez después de generar/revisar el banco (y de nuevo cada vez
que cambie). La búsqueda en sí (`retrieve.py`) es CPU + milisegundos: no
hace falta GPU ni un servicio externo para esto.

Referencia API: docs de sentence-transformers vía Context7 (sesión
2026-09-16) — `SentenceTransformer.encode(..., normalize_embeddings=True)`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import settings

MODEL_NAME = "all-MiniLM-L6-v2"

_EMBEDDINGS_FILE = "embeddings.npy"
_METADATA_FILE = "index.json"


@dataclass
class AnswerEntry:
    id: str
    category: str
    question_en: str
    answer_en: str
    answer_es: str
    keypoints: list[str]
    reviewed: bool


def _load_answers() -> list[AnswerEntry]:
    entries: list[AnswerEntry] = []
    for path in sorted(settings.answers_dir.glob("*.json")):
        if path.name in (_METADATA_FILE,):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        entries.append(
            AnswerEntry(
                id=data["id"],
                category=data["category"],
                question_en=data["question_en"],
                answer_en=data["answer_en"],
                answer_es=data.get("answer_es", ""),
                keypoints=data.get("keypoints", []),
                reviewed=data.get("reviewed", False),
            )
        )
    return entries


def _embedding_text(entry: AnswerEntry) -> str:
    """Texto que se vectoriza para cada entrada: la pregunta pesa más que
    la respuesta, porque en retrieval buscamos por lo que pregunta el
    entrevistador, no por el contenido de la respuesta."""
    return f"{entry.question_en}\n{entry.category}\n" + " ".join(entry.keypoints)


def build_index(*, only_reviewed: bool = False) -> tuple[int, int]:
    """Construye embeddings.npy + index.json. Devuelve (incluidas, total)."""
    from sentence_transformers import SentenceTransformer

    entries = _load_answers()
    total = len(entries)
    if only_reviewed:
        entries = [e for e in entries if e.reviewed]

    if not entries:
        raise RuntimeError(
            "No hay respuestas para indexar. Corre primero: python -m app.answers.generate"
        )

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    texts = [_embedding_text(e) for e in entries]
    embeddings = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    settings.answers_dir.mkdir(parents=True, exist_ok=True)
    np.save(settings.answers_dir / _EMBEDDINGS_FILE, embeddings.astype(np.float32))

    metadata = [
        {
            "id": e.id,
            "category": e.category,
            "question_en": e.question_en,
            "reviewed": e.reviewed,
        }
        for e in entries
    ]
    (settings.answers_dir / _METADATA_FILE).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return len(entries), total


def load_index() -> tuple[np.ndarray, list[dict]]:
    emb_path = settings.answers_dir / _EMBEDDINGS_FILE
    meta_path = settings.answers_dir / _METADATA_FILE
    if not emb_path.exists() or not meta_path.exists():
        raise RuntimeError(
            "No hay índice construido. Corre primero: python -m app.answers.store"
        )
    embeddings = np.load(emb_path)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return embeddings, metadata


def load_answer(answer_id: str) -> dict:
    path = settings.answers_dir / f"{answer_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    included, total = build_index(only_reviewed=False)
    print(f"Índice construido: {included}/{total} respuestas -> {settings.answers_dir}")
    if included < total:
        print(f"({total - included} sin revisar aún se incluyeron; usa build_index(only_reviewed=True) para excluirlas)")


if __name__ == "__main__":
    main()
