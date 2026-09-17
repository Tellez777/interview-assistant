"""Genera el banco de respuestas (M2), una vez, offline.

Por cada pregunta en data/questions.yaml, pide al LLM una respuesta
fundamentada ÚNICAMENTE en el perfil del candidato (data/profile.json) y
la guarda en data/answers/<id>.json. El resultado es un BORRADOR: Fernando
debe revisar y corregir cada respuesta antes de que el banco se use en
Practice Mode o en vivo (ver plan, M2, paso 3).

Uso:
    cd backend
    .venv\\Scripts\\python -m app.answers.generate                # todas las que falten
    .venv\\Scripts\\python -m app.answers.generate --only tech_stack_main
    .venv\\Scripts\\python -m app.answers.generate --category SEO
    .venv\\Scripts\\python -m app.answers.generate --force         # regenerar todo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.llm.base import get_default_client
from app.profile.schema import CandidateProfile

SYSTEM_PROMPT = """You are helping a job candidate prepare spoken interview answers in English.

RULES (do not break these):
- Never invent experience, projects, numbers, or job titles beyond what is given in CANDIDATE CONTEXT below.
- If the question touches a KNOWN GAP, use the honest bridge provided for it — do not pretend the gap doesn't exist.
- Answer at approximately B1 English level: simple sentences, natural spoken English, no unnecessarily advanced vocabulary.
- Target 90-150 words, meant to be spoken in 30-60 seconds.
- Prefer concrete numbers and project names over vague claims.
- Avoid corporate-sounding phrases like "spearheaded" or "leveraged a comprehensive solution".
- CANDIDATE CONTEXT is mostly written in Spanish (it's the source material, not the target
  language). "answer_en" must ALWAYS be in English regardless of the context's language —
  never mirror it.

Respond with ONLY a JSON object (no markdown fences, no commentary) with exactly these keys:
{
  "answer_en": "the spoken answer, in English",
  "keypoints": ["3 to 5 short bullets: project/tech/number to mention live"],
  "answer_es": "a natural Spanish translation of answer_en, for the candidate to understand it before memorizing it",
  "sources": ["which profile fields were used, e.g. 'stories.falabella_idempotency', 'gaps.WordPress'"]
}
"""


def load_questions() -> list[dict[str, Any]]:
    return yaml.safe_load(settings.questions_path.read_text(encoding="utf-8"))


def build_user_prompt(profile: CandidateProfile, question: dict[str, Any]) -> str:
    parts = [
        "CANDIDATE CONTEXT:",
        profile.as_context_block(),
        "",
        f"INTERVIEW QUESTION ({question['category']}):",
        question["question_en"],
    ]
    if question.get("hint"):
        parts += ["", f"HINT (which parts of the context to draw from): {question['hint']}"]
    return "\n".join(parts)


def extract_json(raw: str) -> dict[str, Any]:
    """El modelo casi siempre devuelve JSON limpio, pero por si acaso
    tolera fences ```json ... ``` alrededor."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró JSON en la respuesta del modelo:\n{raw}")
    return json.loads(match.group(0))


async def generate_one(profile: CandidateProfile, question: dict[str, Any]) -> dict[str, Any]:
    client = get_default_client()
    user_prompt = build_user_prompt(profile, question)
    raw = await client.chat(SYSTEM_PROMPT, user_prompt, max_tokens=1024)
    data = extract_json(raw)
    data["id"] = question["id"]
    data["category"] = question["category"]
    data["question_en"] = question["question_en"]
    data["reviewed"] = False  # Fernando lo pone en true tras revisar/corregir
    return data


async def run(only: str | None, category: str | None, force: bool) -> None:
    profile = CandidateProfile.load(settings.profile_path)
    questions = load_questions()
    settings.answers_dir.mkdir(parents=True, exist_ok=True)

    if only:
        questions = [q for q in questions if q["id"] == only]
    if category:
        questions = [q for q in questions if q["category"] == category]

    for q in questions:
        out_path = settings.answers_dir / f"{q['id']}.json"
        if out_path.exists() and not force:
            print(f"  [skip] {q['id']} (ya existe, usa --force para regenerar)")
            continue

        print(f"  [gen ] {q['id']} ({q['category']})...")
        try:
            data = await generate_one(profile, q)
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {q['id']}: {exc}")
            continue

        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [ok  ] {q['id']} -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="generar solo esta pregunta por id")
    parser.add_argument("--category", help="generar solo esta categoría")
    parser.add_argument("--force", action="store_true", help="regenerar aunque ya exista")
    args = parser.parse_args()

    asyncio.run(run(args.only, args.category, args.force))

    print(
        "\nListo. Revisa cada archivo en data/answers/ y corrige lo necesario antes de "
        "marcar 'reviewed': true — el banco es tu guion real, no debe quedar sin revisar."
    )


if __name__ == "__main__":
    main()
