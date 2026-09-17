"""Interfaz común para clientes de LLM.

Tanto `answers/generate.py` (M2, offline) como `practice/evaluate.py` (M3)
hablan contra este `Protocol`, no contra un SDK concreto. Cambiar de
proveedor (Anthropic, un gateway compatible con OpenAI, etc.) es cuestión
de instanciar otra clase que lo implemente — nada más se toca.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class LLMClient(Protocol):
    async def chat(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Devuelve la respuesta completa de una sola vez."""
        ...

    async def stream_chat(self, system: str, user: str, *, max_tokens: int = 1024) -> AsyncIterator[str]:
        """Va entregando fragmentos de texto conforme el modelo los genera.

        Necesario en M4 (Live Mode) para mostrar la respuesta sugerida en
        streaming en vez de esperar a que termine por completo.
        """
        ...


def get_default_client(*, model: str | None = None) -> LLMClient:
    """Instancia el cliente configurado en `Settings.llm_provider`.

    `model` sobreescribe el modelo por defecto de ese proveedor — lo usa
    Live Mode para las preguntas técnicas/de código, que se mandan a un
    modelo más grande que el conversacional rápido (ver `app.live.pipeline`).
    """
    from app.config import settings

    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_client import AnthropicClient, DEFAULT_MODEL

        return AnthropicClient(api_key=settings.anthropic_api_key, model=model or DEFAULT_MODEL)

    if settings.llm_provider == "openai_compat":
        from app.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient(
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key,
            model=model or settings.openai_compat_model,
        )

    raise ValueError(f"LLM_PROVIDER desconocido: {settings.llm_provider!r}")
