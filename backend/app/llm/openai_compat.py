"""Cliente para la API real de OpenAI o cualquier endpoint compatible con
ella: el gateway propio (IA Engine), Groq, etc. Implementa `LLMClient`.

Si `base_url` se deja vacío, el SDK usa la URL real de OpenAI
(https://api.openai.com/v1) — en ese caso sí hace falta una API key de
verdad. Con un `base_url` propio (gateway/Groq/etc.), la key puede no
aplicar y se manda un valor dummy.

Referencia: docs oficiales del SDK `openai` vía Context7, sesión 2026-09-16.
`AsyncOpenAI(base_url=...)` + `chat.completions.create` / `.stream(...)`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        if not model:
            raise ValueError("Falta OPENAI_COMPAT_MODEL en backend/.env")
        if not base_url and not api_key:
            raise ValueError(
                "Sin OPENAI_COMPAT_BASE_URL (es decir, usando la API real de OpenAI), "
                "hace falta OPENAI_COMPAT_API_KEY en backend/.env"
            )
        self._client = AsyncOpenAI(base_url=base_url or None, api_key=api_key or "unused")
        self._model = model

    async def chat(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        completion = await self._client.chat.completions.create(
            model=self._model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return completion.choices[0].message.content or ""

    async def stream_chat(self, system: str, user: str, *, max_tokens: int = 1024) -> AsyncIterator[str]:
        async with self._client.chat.completions.stream(
            model=self._model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        ) as stream:
            async for event in stream:
                if event.type == "content.delta" and event.delta:
                    yield event.delta
