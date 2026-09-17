"""Selección de preguntas para una sesión de práctica.

Deliberadamente simple: sin el detector de intención del documento
original. Aquí ni siquiera hace falta esa complejidad porque la categoría
la elige el propio usuario en la UI antes de empezar.
"""

from __future__ import annotations

import random

import yaml

from app.config import settings


def load_questions() -> list[dict]:
    return yaml.safe_load(settings.questions_path.read_text(encoding="utf-8"))


def list_categories() -> list[str]:
    seen: list[str] = []
    for q in load_questions():
        if q["category"] not in seen:
            seen.append(q["category"])
    return seen


def pick_question(*, category: str | None = None, exclude_ids: set[str] | None = None) -> dict | None:
    questions = load_questions()
    if category:
        questions = [q for q in questions if q["category"] == category]
    if exclude_ids:
        remaining = [q for q in questions if q["id"] not in exclude_ids]
        questions = remaining or questions  # si ya se agotaron, permite repetir

    if not questions:
        return None
    return random.choice(questions)
