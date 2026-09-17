"""Medición de latencia por etapa del pipeline.

La métrica que importa (ver plan, sección 28 del documento original) no es
el tiempo hasta la respuesta completa, sino el "Time To First Useful
Information": cuánto tarda en aparecer el primer texto, la primera
traducción, el primer token de respuesta. Sin medir esto, afinar la
latencia en M4 es adivinar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Timeline:
    """Una serie de hitos con timestamp relativo, para un solo turno de
    pregunta/respuesta. Uso:

        t = Timeline()
        t.mark("speech_end")
        ...
        t.mark("first_partial_transcript")
        ...
        t.mark("first_translation")
        ...
        t.mark("first_answer_token")
        print(t.deltas_ms())
    """

    _t0: float = field(default_factory=time.perf_counter)
    _marks: list[tuple[str, float]] = field(default_factory=list)

    def mark(self, label: str) -> float:
        """Registra un hito y devuelve los ms transcurridos desde el inicio."""
        elapsed = (time.perf_counter() - self._t0) * 1000
        self._marks.append((label, elapsed))
        return elapsed

    def deltas_ms(self) -> dict[str, float]:
        """ms desde el inicio de la timeline para cada hito registrado."""
        return {label: round(elapsed, 1) for label, elapsed in self._marks}

    def gaps_ms(self) -> dict[str, float]:
        """ms entre cada hito y el anterior (o el inicio, para el primero)."""
        gaps: dict[str, float] = {}
        prev = 0.0
        for label, elapsed in self._marks:
            gaps[label] = round(elapsed - prev, 1)
            prev = elapsed
        return gaps
