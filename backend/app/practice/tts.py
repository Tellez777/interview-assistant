"""Pronuncia las preguntas del simulador con edge-tts (voz neural, gratis,
sin API key). Escuchar la pregunta en inglés entrena la comprensión
auditiva, que es la mitad de la brecha real de Fernando (ver plan, M3).

Referencia API: docs de edge-tts vía Context7 (sesión 2026-09-16) —
`edge_tts.Communicate(text, voice).save(path)`.
"""

from __future__ import annotations

from pathlib import Path

import edge_tts

DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"


async def synthesize_question(text: str, out_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(out_path))
    return out_path
