"""Fal.ai image generation provider implementation.

Uses the Fal.ai REST API via ``httpx.AsyncClient`` for async HTTP requests.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.base import ImageProvider, ImageResult

_DEFAULT_BASE_URL = "https://queue.fal.run"
_DEFAULT_MODEL = "fal-ai/flux/schnell"


class FalProvider(ImageProvider):
    """Concrete image generation provider for the Fal.ai API.

    Args:
        api_key: Fal.ai API key.
        base_url: Override the default API base URL.
        model: Model identifier (default: ``fal-ai/flux/schnell``).
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
                timeout=120.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> ImageResult:
        """Generate an image using the Fal.ai API.

        Args:
            prompt: Text description of the desired image.
            width: Desired image width in pixels.
            height: Desired image height in pixels.

        Returns:
            An :class:`ImageResult` with the generated image URL.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "image_size": f"{width}x{height}",
        }

        client = self._get_client()
        response = await client.post(f"/{self._model}", json=body)
        response.raise_for_status()

        data = response.json()

        # Fal.ai returns images in a list with url field
        images = data.get("images", [])
        if images:
            url = images[0].get("url", "")
        else:
            # Some models return a single image_url field
            url = data.get("image_url", data.get("url", ""))

        return ImageResult(
            url=url,
            alt_text=prompt,
            width=width,
            height=height,
        )

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
