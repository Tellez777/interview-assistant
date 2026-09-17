"""Qué pasa cuando se cierra un turno del entrevistador.

Implementa la estrategia "retrieval primero, LLM como fallback" del plan
(M4): traducción y búsqueda en el banco corren en paralelo; si hay un
match fuerte y revisado se usa esa respuesta cacheada (rápido, y es la que
Fernando ya aprobó); si no, se cae a una llamada al LLM en streaming con
el perfil completo como contexto — igual que `app/answers/generate.py`,
pero en texto plano en vez de JSON, porque aquí se transmite token a token.

Dos casos especiales, agregados tras la primera prueba real con Fernando:
- **Preguntas técnicas/de código** ("write a SQL query...", "how would you
  implement...") se detectan con una heurística simple y van a un modelo
  más grande con un prompt distinto, que sí permite bloques de código y
  profundidad técnica — el modelo conversacional rápido (gpt-5.4-mini) no
  es el indicado para esto.
- **Anti-repetición**: dentro de la misma sesión, se le dice al LLM qué
  historias ya usó en turnos anteriores, para que no recicle siempre la
  más "vistosa" (ej. la de idempotencia de Falabella) en preguntas que
  también podrían responderse con otra experiencia.

Nada de esto corre si `generate_full_answer` es False: en ese caso solo se
mandan traducción y keypoints, sin tocar el LLM. Ver la nota ética del
plan sobre por qué la respuesta completa va detrás de un toggle apagado
por defecto.
"""

from __future__ import annotations

import asyncio
import re
import traceback
from collections.abc import Callable

from app.answers.retrieve import search
from app.answers.store import load_answer
from app.config import settings
from app.live import db as live_db
from app.live import events
from app.llm.base import get_default_client
from app.metrics import Timeline
from app.profile.schema import CandidateProfile
from app.translation.translate import translate_en_to_es, translate_es_to_en

# Qué tan buena tiene que ser la mejor coincidencia del banco para usarla
# directo en vez de llamar al LLM. Punto de partida; se ajusta viendo
# scores reales en uso (ver plan, M4).
CACHE_SCORE_THRESHOLD = 0.55

# Cuántas historias recientes recordar para evitar que el LLM repita
# siempre la misma en preguntas distintas dentro de la misma sesión.
RECENT_SOURCES_LIMIT = 4

LIVE_SYSTEM_PROMPT_EN = """You are helping a job candidate answer an interview question live, in spoken English.

RULES:
- Never invent experience, projects, numbers, or job titles beyond what is given in CANDIDATE CONTEXT.
- If the question touches a KNOWN GAP, use the honest bridge provided for it.
- Answer at approximately B1 English level: simple sentences, natural spoken English.
- Target 60-120 words — this is meant to be spoken in under 40 seconds.
- Prefer concrete numbers and project names over vague claims.
- CANDIDATE CONTEXT below is mostly written in Spanish (that's the source
  material, not the target language). Regardless of what language the
  context is in, your answer must ALWAYS be in English. Never mirror the
  context's language.
- If a RECENTLY USED note is included, avoid reusing that same story or
  example unless it is genuinely the only relevant one for this question
  — vary your material across the interview like a real candidate would.

Respond with ONLY the spoken answer, in plain text, in English. No JSON, no markdown, no preamble like "Sure, here's an answer".
"""

# Variante en español: se usa cuando la entrevista real (o esa parte de
# ella) resulta ser en español, no en inglés — ver plan, M4, sección
# "¿preparado para español?". El CONTEXTO DEL CANDIDATO ya está mayormente
# en español, así que aquí no hace falta la instrucción de "ignora el
# idioma del contexto": coinciden.
LIVE_SYSTEM_PROMPT_ES = """Estás ayudando a un candidato a responder, en voz alta y en español, una pregunta de entrevista de trabajo en vivo.

REGLAS:
- Nunca inventes experiencia, proyectos, números o puestos más allá de lo que aparece en CONTEXTO DEL CANDIDATO.
- Si la pregunta toca una BRECHA CONOCIDA, usa el puente honesto que se provee para esa brecha.
- Responde en español neutro y natural, como se diría en voz alta, no como un texto escrito.
- Apunta a 60-120 palabras — para poder decirse en menos de 40 segundos.
- Prefiere números y nombres de proyectos concretos sobre afirmaciones vagas.
- Si se incluye una nota de RECIÉN USADO, evita repetir esa misma historia o ejemplo a menos que sea
  genuinamente la única relevante para esta pregunta — varía el material a lo largo de la entrevista, como lo
  haría un candidato real.

Responde ÚNICAMENTE con la respuesta hablada, en texto plano, en español. Sin JSON, sin markdown, sin preámbulo como "Claro, aquí está la respuesta".
"""

TECHNICAL_SYSTEM_PROMPT_EN = """You are helping a job candidate answer a TECHNICAL interview question live — the
kind that expects real technical depth: writing a code snippet, a SQL query, explaining an algorithm, or walking
through implementation details.

RULES:
- Never invent experience, projects, numbers, or job titles beyond what is given in CANDIDATE CONTEXT.
- If the question touches a KNOWN GAP (e.g. WordPress), be honest about the gap first, then answer with the
  fundamentals you do have, using the honest bridge provided.
- This is NOT a simplified B1-level answer — use normal technical English, precise terminology, and real code
  when the question calls for it.
- When code or a query is relevant, include it in a fenced code block (triple backticks), then briefly explain it
  in 2-4 spoken sentences. Keep the code itself short and directly relevant, not a full production-grade solution.
- Ground technical choices in the candidate's actual stack from CANDIDATE CONTEXT (React, Next.js, Node.js,
  Python, PHP, MySQL, PostgreSQL, MongoDB, etc.) — don't reach for technologies not listed there.
- CANDIDATE CONTEXT below is mostly written in Spanish (source material only). Your answer must ALWAYS be in
  English regardless of the context's language.

Respond with ONLY the answer, in English. You may use markdown code fences for code, but no JSON wrapper and no
preamble like "Sure, here's the answer".
"""

TECHNICAL_SYSTEM_PROMPT_ES = """Estás ayudando a un candidato a responder una pregunta TÉCNICA de entrevista en vivo — del tipo que
espera profundidad técnica real: escribir un fragmento de código, una consulta SQL, explicar un algoritmo o
caminar por detalles de implementación.

REGLAS:
- Nunca inventes experiencia, proyectos, números o puestos más allá de lo que aparece en CONTEXTO DEL CANDIDATO.
- Si la pregunta toca una BRECHA CONOCIDA (p. ej. WordPress), sé honesto sobre la brecha primero, y luego
  responde con los fundamentos que sí tiene, usando el puente honesto que se provee.
- Esta NO es una respuesta simplificada — usa terminología técnica precisa y código real cuando la pregunta lo
  amerite.
- Cuando el código o una consulta sea relevante, inclúyelo en un bloque de código (triple backtick), y luego
  explícalo brevemente en 2-4 frases habladas. Mantén el código corto y directamente relevante, no una solución
  de producción completa.
- Fundamenta las decisiones técnicas en el stack real del candidato según CONTEXTO DEL CANDIDATO (React, Next.js,
  Node.js, Python, PHP, MySQL, PostgreSQL, MongoDB, etc.) — no menciones tecnologías que no estén ahí.
- Tu respuesta debe estar SIEMPRE en español.

Responde ÚNICAMENTE con la respuesta, en español (el código en sí, obviamente, va en su sintaxis normal). Puedes
usar fences de markdown para el código, pero sin envoltura JSON ni preámbulo como "Claro, aquí está la respuesta".
"""

# Heurística para enrutar a TECHNICAL_SYSTEM_PROMPT + el modelo más grande
# en vez del conversacional rápido. Deliberadamente simple (sin otra
# llamada al LLM de por medio, que sumaría latencia) — ver plan, M4.
_TECHNICAL_PATTERNS_EN = re.compile(
    r"\b("
    r"write (a |an |some )?(code|function|query|script|algorithm|snippet)"
    r"|implement"
    r"|how would you (code|write|implement|build|design)"
    r"|what would the (code|query|function) (look like|be)"
    r"|show me (the )?code"
    r"|sql query"
    r"|write.{0,15}\bsql\b"
    r"|pseudocode"
    r"|regular expression|regex"
    r"|time complexity|big o"
    r"|debug this|fix this (code|bug)"
    r"|code (a |an )?(solution|example)"
    r")\b",
    re.IGNORECASE,
)

# Equivalente en español, para cuando Live Mode corre en modo "es" — el
# entrevistador puede preguntar "escríbeme una consulta SQL" en vez de
# "write a SQL query".
_TECHNICAL_PATTERNS_ES = re.compile(
    r"\b("
    r"escribe (una |un )?(consulta|función|query|script|algoritmo)"
    r"|implementa(r|rías)?"
    r"|cómo (lo )?(programarías|implementarías|construirías|diseñarías|harías)"
    r"|muéstrame (el )?código"
    r"|consulta sql|query sql"
    r"|escribe.{0,15}\bsql\b"
    r"|pseudocódigo"
    r"|expresión regular|regex"
    r"|complejidad (temporal|de tiempo)|big o"
    r"|depura este (código|bug)|arregla este (código|bug)"
    r"|código (de )?(una solución|un ejemplo)"
    r")\b",
    re.IGNORECASE,
)


def is_technical_question(text: str, *, language: str = "en") -> bool:
    pattern = _TECHNICAL_PATTERNS_ES if language == "es" else _TECHNICAL_PATTERNS_EN
    return bool(pattern.search(text))


def _detect_language(text: str, *, expected: str = "en") -> tuple[str | None, bool | None]:
    """(idioma_detectado, coincide_con_expected). `(None, None)` si el
    texto es demasiado corto para detectar con confianza. Ver plan, M4 —
    Fernando reportó que la respuesta sugerida salió en español un par de
    veces con `gpt-5.4-mini`; esto lo deja registrado en vez de tener que
    notarlo a ojo cada vez. `expected` es "en" o "es" según el modo de la
    sesión Live."""
    from langdetect import LangDetectException, detect

    if not text or len(text.split()) < 4:
        return None, None
    try:
        lang = detect(text)
    except LangDetectException:
        return None, None
    return lang, lang == expected


def _build_prompt(
    profile: CandidateProfile,
    question: str,
    *,
    language: str = "en",
    recent_source_ids: list[str] | None = None,
) -> str:
    if language == "es":
        parts = [f"CONTEXTO DEL CANDIDATO:\n{profile.as_context_block()}"]
        if recent_source_ids:
            parts.append(
                "USADO RECIENTEMENTE en esta misma entrevista — prefiere una historia/ejemplo distinto si "
                "aplica: " + ", ".join(recent_source_ids)
            )
        parts.append(f"PREGUNTA DE LA ENTREVISTA:\n{question}")
        parts.append("Responde la pregunta de arriba, en español.")
        return "\n\n".join(parts)

    parts = [
        f"CANDIDATE CONTEXT (source material, written in Spanish):\n{profile.as_context_block()}",
    ]
    if recent_source_ids:
        parts.append(
            "RECENTLY USED in this same interview — prefer a different story/example if one fits: "
            + ", ".join(recent_source_ids)
        )
    parts.append(f"INTERVIEW QUESTION:\n{question}")
    parts.append(
        "Answer the question above. Remember: your answer must be in English, even though "
        "the context above is in Spanish."
    )
    return "\n\n".join(parts)


def _build_technical_prompt(profile: CandidateProfile, question: str, *, language: str = "en") -> str:
    if language == "es":
        return (
            f"CONTEXTO DEL CANDIDATO:\n{profile.as_context_block()}\n\n"
            f"PREGUNTA TÉCNICA DE LA ENTREVISTA:\n{question}\n\n"
            "Responde la pregunta de arriba con profundidad técnica real, en español."
        )
    return (
        f"CANDIDATE CONTEXT (source material, written in Spanish):\n{profile.as_context_block()}\n\n"
        f"TECHNICAL INTERVIEW QUESTION:\n{question}\n\n"
        "Answer the question above with real technical depth, in English."
    )


async def handle_interviewer_turn(
    *,
    turn_id: str,
    text: str,
    emit: Callable[[dict], None],
    generate_full_answer: bool,
    timeline: Timeline,
    recent_source_ids: list[str] | None = None,
    language: str = "en",
) -> None:
    """Orquesta traducción + keypoints + (cache | LLM | técnico) para un
    turno ya cerrado del canal del entrevistador. `emit` manda un evento
    al WebSocket (ver `app/live/events.py`); debe ser no bloqueante.

    Todo el cuerpo va envuelto en try/except: esta corrutina se agenda con
    `asyncio.run_coroutine_threadsafe` y nadie llama `.result()` sobre el
    Future que devuelve (ver `app.live.manager`), así que una excepción
    sin capturar aquí desaparece en silencio — pasó exactamente eso con el
    bug real de `event.content` vs `event.delta` en `openai_compat.py`:
    la respuesta sugerida se quedaba colgada sin ningún traceback visible.
    """
    try:
        await _handle_interviewer_turn(
            turn_id=turn_id,
            text=text,
            emit=emit,
            generate_full_answer=generate_full_answer,
            timeline=timeline,
            recent_source_ids=recent_source_ids,
            language=language,
        )
    except asyncio.CancelledError:
        live_db.update_turn(turn_id, error="cancelled (nueva pregunta llegó antes de terminar)")
        raise
    except Exception as exc:  # noqa: BLE001 - reportar cualquier falla, no solo las previstas
        traceback.print_exc()
        live_db.update_turn(turn_id, error=f"{type(exc).__name__}: {exc}")
        emit(events.error(f"{type(exc).__name__}: {exc}"))


async def _handle_interviewer_turn(
    *,
    turn_id: str,
    text: str,
    emit: Callable[[dict], None],
    generate_full_answer: bool,
    timeline: Timeline,
    recent_source_ids: list[str] | None,
    language: str = "en",
) -> None:
    if language == "es":
        # El banco de respuestas está indexado en inglés (ver
        # app.answers.store), así que hay que traducir la pregunta antes
        # de buscar. Como el retrieval depende de esa traducción, aquí no
        # se pueden lanzar en paralelo como en el modo inglés — el costo
        # es aceptable (~450ms) porque es una sesión nueva, no una
        # regresión del modo ya medido y validado.
        translated = await asyncio.to_thread(translate_es_to_en, text)
        results = await asyncio.to_thread(search, translated, 1)
    else:
        translate_task = asyncio.create_task(asyncio.to_thread(translate_en_to_es, text))
        retrieve_task = asyncio.create_task(asyncio.to_thread(search, text, 1))
        translated, results = await asyncio.gather(translate_task, retrieve_task)

    timeline.mark("translation")
    emit(events.translation(turn_id, translated))

    best = results[0] if results else None
    answer_doc: dict | None = None
    if best:
        answer_doc = load_answer(best["id"])
        emit(events.keypoints(turn_id, answer_doc.get("keypoints", []), best["id"], best["score"]))
    else:
        emit(events.keypoints(turn_id, [], None, 0.0))
    timeline.mark("keypoints")

    live_db.update_turn(
        turn_id,
        translation_es=translated,
        keypoints=(answer_doc.get("keypoints", []) if answer_doc else []),
        keypoints_source_id=(best["id"] if best else None),
        keypoints_score=(best["score"] if best else None),
    )

    if not generate_full_answer:
        marks = timeline.gaps_ms()
        emit(events.metrics(turn_id, marks))
        live_db.update_turn(turn_id, marks_ms=marks)
        return

    technical = is_technical_question(text, language=language)
    # Una respuesta cacheada del banco solo sirve si existe en el idioma
    # de la sesión: `answer_es` se generó junto con `answer_en` desde el
    # principio (ver app.answers.generate) pero nunca se había usado hasta
    # ahora. Si por lo que sea faltara en alguna entrada vieja, cae al LLM
    # en vez de mostrar la respuesta en el idioma equivocado.
    answer_field = "answer_es" if language == "es" else "answer_en"
    # Una pregunta técnica/de código nunca debería contestarse con una
    # respuesta cacheada conversacional del banco — el banco no tiene
    # ejemplos de código.
    use_cache = bool(
        not technical
        and best
        and answer_doc
        and best["score"] >= CACHE_SCORE_THRESHOLD
        and best.get("reviewed")
        and answer_doc.get(answer_field)
    )
    answer_text = ""

    if use_cache:
        answer_mode = "cached"
        emit(events.answer_start(turn_id, "cached"))
        timeline.mark("answer_first_token")
        answer_text = answer_doc[answer_field]
        emit(events.answer_chunk(turn_id, answer_text))
        emit(events.answer_done(turn_id))
    else:
        profile = CandidateProfile.load(settings.profile_path)

        if technical:
            answer_mode = "technical"
            emit(events.answer_start(turn_id, "technical"))
            client = get_default_client(model=settings.openai_compat_technical_model or None)
            system_prompt = TECHNICAL_SYSTEM_PROMPT_ES if language == "es" else TECHNICAL_SYSTEM_PROMPT_EN
            user_prompt = _build_technical_prompt(profile, text, language=language)
            max_tokens = 600
        else:
            answer_mode = "llm"
            emit(events.answer_start(turn_id, "llm"))
            client = get_default_client()
            system_prompt = LIVE_SYSTEM_PROMPT_ES if language == "es" else LIVE_SYSTEM_PROMPT_EN
            user_prompt = _build_prompt(profile, text, language=language, recent_source_ids=recent_source_ids)
            max_tokens = 300

        first_token = True
        async for delta in client.stream_chat(system_prompt, user_prompt, max_tokens=max_tokens):
            if first_token:
                timeline.mark("answer_first_token")
                first_token = False
            answer_text += delta
            emit(events.answer_chunk(turn_id, delta))
        emit(events.answer_done(turn_id))

    if recent_source_ids is not None and best:
        recent_source_ids.append(best["id"])
        del recent_source_ids[:-RECENT_SOURCES_LIMIT]

    detected_lang, matches_expected = _detect_language(answer_text, expected=language)
    marks = timeline.gaps_ms()
    emit(events.metrics(turn_id, marks))
    live_db.update_turn(
        turn_id,
        answer_mode=answer_mode,
        answer_text=answer_text,
        answer_language=detected_lang,
        answer_language_ok=(None if matches_expected is None else int(matches_expected)),
        marks_ms=marks,
    )
