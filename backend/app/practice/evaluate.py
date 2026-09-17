"""Evaluación de la respuesta hablada, en dos capas (ver plan, M3):

1. Objetiva: derivada de la transcripción y de la duración, sin LLM.
   Es lo que convierte esto en un entrenador medible.
2. Por LLM: compara contra la respuesta del banco — gramática, vocabulario,
   qué keypoints se mencionaron y cuáles no, y si se afirmó algo fuera del
   perfil del candidato.

Nota sobre alcance: `pause_count` queda como None por ahora. Medirlo bien
requiere timestamps por palabra/segmento del ASR (silencios internos, no
solo el fin de turno), que RealtimeSTT no expone en su callback de texto
plano. Se retoma si al usar la app se vuelve una señal que realmente hace
falta ver.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.base import get_default_client
from app.profile.schema import CandidateProfile

FILLER_WORDS = ["um", "uh", "like", "you know", "i mean", "actually", "basically", "so yeah"]

EVAL_SYSTEM_PROMPT = """You are an English interview coach reviewing a candidate's spoken answer.

You will get: the interview question, the candidate's reference answer (from their reviewed answer bank),
the candidate's actual spoken transcript, and the candidate's profile context (to check for invented claims).

Respond with ONLY a JSON object (no markdown fences, no commentary):
{
  "grammar_corrections": [{"original": "...", "suggested": "..."}],
  "vocabulary_notes": "1-2 sentences on word choice/naturalness",
  "keypoints_mentioned": ["..."],
  "keypoints_missed": ["..."],
  "unsupported_claims": ["anything the candidate said that isn't backed by their profile context, or [] if none"],
  "overall_note": "1-2 encouraging but honest sentences"
}
"""


@dataclass
class ObjectiveMetrics:
    word_count: int
    duration_seconds: float
    words_per_minute: float
    filler_count: int
    filler_breakdown: dict[str, int]


def compute_objective_metrics(transcript: str, duration_seconds: float) -> ObjectiveMetrics:
    words = re.findall(r"[A-Za-z']+", transcript)
    word_count = len(words)
    wpm = (word_count / duration_seconds) * 60 if duration_seconds > 0 else 0.0

    lower = transcript.lower()
    breakdown = {}
    for filler in FILLER_WORDS:
        count = len(re.findall(rf"\b{re.escape(filler)}\b", lower))
        if count:
            breakdown[filler] = count

    return ObjectiveMetrics(
        word_count=word_count,
        duration_seconds=duration_seconds,
        words_per_minute=round(wpm, 1),
        filler_count=sum(breakdown.values()),
        filler_breakdown=breakdown,
    )


def _extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró JSON en la respuesta del modelo:\n{raw}")
    return json.loads(match.group(0))


async def evaluate_with_llm(
    *,
    profile: CandidateProfile,
    question_en: str,
    reference_answer_en: str,
    user_transcript: str,
) -> dict:
    client = get_default_client()
    user_prompt = "\n".join(
        [
            "CANDIDATE CONTEXT:",
            profile.as_context_block(),
            "",
            f"QUESTION: {question_en}",
            "",
            f"REFERENCE ANSWER (from the candidate's reviewed bank): {reference_answer_en}",
            "",
            f"CANDIDATE'S ACTUAL SPOKEN TRANSCRIPT: {user_transcript}",
        ]
    )
    raw = await client.chat(EVAL_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
    return _extract_json(raw)
