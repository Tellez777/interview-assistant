"""Cliente Anthropic. Implementa `LLMClient` (ver app/llm/base.py).

Referencia: docs oficiales del SDK (anthropic-sdk-python) vía Context7,
sesión del 2026-09-16. `messages.create` para respuesta completa,
`messages.stream(...)` como context manager async con `text_stream` para
streaming.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError(
                "Falta ANTHROPIC_API_KEY en backend/.env (copia .env.example y complétalo)."
            )
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text")

    async def stream_chat(self, system: str, user: str, *, max_tokens: int = 1024) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
