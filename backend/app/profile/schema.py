"""Modelos del perfil del candidato: la fuente única de verdad.

El LLM (generación del banco de respuestas y evaluación en Practice Mode)
solo puede fundamentar sus respuestas en lo que vive aquí. `gaps` es tan
importante como `stories`: cada brecha lleva su propia respuesta puente,
para que el modelo nunca necesite inventar experiencia que no existe.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class Education(BaseModel):
    institution: str
    degree: str
    graduation_date: str  # texto libre, p. ej. "Dic 2024"
    location: str = ""


class Certification(BaseModel):
    name: str
    date: str = ""


class ExperienceEntry(BaseModel):
    role: str
    company: str
    start_date: str
    end_date: str = "Actualidad"
    location: str = ""
    employment_type: str = ""  # p. ej. "tiempo completo", "part-time"
    highlights: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str
    summary: str
    technologies: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)  # p. ej. "100/100 SEO (PageSpeed)"
    url: str = ""


class Story(BaseModel):
    """Historia en formato STAR para preguntas de experiencia/comportamiento."""

    id: str
    title: str
    situation: str
    task: str
    action: str
    result: str
    connects_to: list[str] = Field(default_factory=list)  # categorías de pregunta que cubre
    caution: str = ""  # advertencias sobre detalles a no afirmar con certeza


class Gap(BaseModel):
    """Una brecha frente a vacantes objetivo, con su respuesta puente honesta."""

    topic: str  # p. ej. "WordPress"
    severity: str = "media"  # "alta" | "media" | "baja"
    honest_bridge: str  # la respuesta puente lista para usar, en inglés
    fundamentals: str = ""  # qué fundamentos sí domina debajo de la herramienta


class CandidateProfile(BaseModel):
    full_name: str
    headline: str
    location: str
    email: str = ""
    linkedin: str = ""
    github: str = ""
    english_level: str = "B1"
    summary: str

    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    technologies: dict[str, list[str]] = Field(default_factory=dict)  # categoría -> lista

    stories: list[Story] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "CandidateProfile":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(self.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def as_context_block(self) -> str:
        """Serializa el perfil a texto plano para inyectar en el prompt del LLM."""
        lines: list[str] = [f"CANDIDATE: {self.full_name} — {self.headline}", self.summary, ""]

        lines.append("EXPERIENCE:")
        for e in self.experience:
            lines.append(f"- {e.role} at {e.company} ({e.start_date} – {e.end_date})")
            for h in e.highlights:
                lines.append(f"  * {h}")

        lines.append("\nPROJECTS:")
        for p in self.projects:
            lines.append(f"- {p.name}: {p.summary}")
            if p.technologies:
                lines.append(f"  tech: {', '.join(p.technologies)}")
            for m in p.metrics:
                lines.append(f"  metric: {m}")

        lines.append("\nTECHNOLOGIES:")
        for category, items in self.technologies.items():
            lines.append(f"- {category}: {', '.join(items)}")

        lines.append("\nSTAR STORIES:")
        for s in self.stories:
            lines.append(f"- [{s.id}] {s.title}")
            lines.append(f"  Situation: {s.situation}")
            lines.append(f"  Task: {s.task}")
            lines.append(f"  Action: {s.action}")
            lines.append(f"  Result: {s.result}")
            if s.caution:
                lines.append(f"  Caution: {s.caution}")

        lines.append("\nKNOWN GAPS (never claim experience beyond this):")
        for g in self.gaps:
            lines.append(f"- {g.topic}: {g.honest_bridge}")

        lines.append("\nTALKING POINTS:")
        for t in self.talking_points:
            lines.append(f"- {t}")

        return "\n".join(lines)
