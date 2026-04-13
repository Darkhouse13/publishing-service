"""DeepSeek LLM provider implementation.

Uses the DeepSeek Chat Completions API (OpenAI-compatible format)
via ``httpx.AsyncClient`` for async HTTP requests.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.base import LLMProvider, LLMResponse

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(LLMProvider):
    """Concrete LLM provider for the DeepSeek API.

    DeepSeek's API follows the OpenAI Chat Completions format:
    ``POST /v1/chat/completions`` with a ``messages`` array.

    Args:
        api_key: DeepSeek API key (``sk-...``).
        base_url: Override the default API base URL.
        model: Model identifier (default: ``deepseek-chat``).
        _transport: Internal parameter for injecting a mock transport in tests.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._transport = _transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and cache the ``httpx.AsyncClient``."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                transport=self._transport,
                timeout=60.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate text using the DeepSeek Chat Completions API.

        Args:
            prompt: The user prompt / message content.
            system_prompt: Optional system instructions.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 – 2.0).

        Returns:
            An :class:`LLMResponse` with the generated text and metadata.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        client = self._get_client()
        response = await client.post("/chat/completions", json=body)
        response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]

        return LLMResponse(
            text=choice["message"]["content"],
            model=data.get("model", self._model),
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
