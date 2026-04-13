"""Shared test helpers: mock providers for unit-testing pipeline services.

Provides mock implementations of the three provider ABCs defined in
``app.providers.base``.  Each mock accepts pre-configured responses and
tracks call counts so that tests can assert on interaction patterns
without hitting real external services.

Typical usage::

    from tests.helpers import MockLLMProvider, MockImageProvider, MockWordPressProvider

    llm = MockLLMProvider(responses=['{"title": "Hello"}'])
    result = await llm.generate("Write something")
    assert llm.call_count == 1
"""

from __future__ import annotations

from typing import Any

from app.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
    WordPressProvider,
    WPMediaResult,
    WPPostResult,
)


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """A mock LLM provider that returns pre-configured responses in order.

    Args:
        responses: A list of strings.  Each call to :meth:`generate`
            returns the next response wrapped in an :class:`LLMResponse`.
            If the list is exhausted, a :class:`RuntimeError` is raised.

    Attributes:
        call_count: Number of successful :meth:`generate` calls.
        call_args:  List of dicts recording every ``generate`` call's
            keyword arguments.
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses: list[str] = list(responses or [])
        self._call_index = 0
        self.call_args: list[dict[str, Any]] = []

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.call_args.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._call_index >= len(self.responses):
            raise RuntimeError("MockLLMProvider ran out of responses")
        text = self.responses[self._call_index]
        self._call_index += 1
        return LLMResponse(
            text=text,
            model="mock-model",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 100,
                "total_tokens": 110,
            },
        )

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return self._call_index


# ---------------------------------------------------------------------------
# MockImageProvider
# ---------------------------------------------------------------------------


class MockImageProvider(ImageProvider):
    """A mock image provider that returns a pre-configured :class:`ImageResult`.

    Args:
        result: The :class:`ImageResult` to return from :meth:`generate`.
            Defaults to a generic placeholder result.

    Attributes:
        call_count: Number of :meth:`generate` calls.
        call_args:  List of dicts recording every ``generate`` call's
            keyword arguments.
    """

    def __init__(self, result: ImageResult | None = None) -> None:
        self._result = result or ImageResult(
            url="https://example.com/generated_image.jpg",
            alt_text="A test image",
            width=1024,
            height=1024,
        )
        self.call_args: list[dict[str, Any]] = []

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> ImageResult:
        self.call_args.append(
            {
                "prompt": prompt,
                "width": width,
                "height": height,
            }
        )
        return self._result

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return len(self.call_args)


# ---------------------------------------------------------------------------
# MockWordPressProvider
# ---------------------------------------------------------------------------


class MockWordPressProvider(WordPressProvider):
    """A mock WordPress provider that tracks calls and returns pre-configured results.

    Args:
        media_result: The default :class:`WPMediaResult` for uploads.
            Each successive upload returns a result with an incrementing ID.
        post_result: The :class:`WPPostResult` to return from
            :meth:`create_post` and :meth:`update_post`.

    Attributes:
        upload_media_calls: List of dicts recording every ``upload_media`` call.
        create_post_calls:  List of dicts recording every ``create_post`` call.
        call_count:         Total number of ``upload_media`` + ``create_post``
            calls.
    """

    def __init__(
        self,
        *,
        media_result: WPMediaResult | None = None,
        post_result: WPPostResult | None = None,
    ) -> None:
        self._media_result = media_result or WPMediaResult(
            id=42,
            url="https://example.com/wp-content/uploads/2024/01/image.jpg",
            media_type="image/jpeg",
        )
        self._post_result = post_result or WPPostResult(
            id=99,
            url="https://example.com/my-post/",
            status="draft",
            title="Test Post",
        )
        self.upload_media_calls: list[dict[str, Any]] = []
        self.create_post_calls: list[dict[str, Any]] = []
        self._upload_counter = 100

    async def upload_media(
        self,
        file_data: bytes,
        filename: str,
        *,
        media_type: str = "image/jpeg",
        alt_text: str = "",
        title: str | None = None,
    ) -> WPMediaResult:
        self.upload_media_calls.append(
            {
                "file_data": file_data,
                "filename": filename,
                "media_type": media_type,
                "alt_text": alt_text,
                "title": title,
            }
        )
        result_id = self._upload_counter
        self._upload_counter += 1
        return WPMediaResult(
            id=result_id,
            url=f"https://example.com/wp-content/uploads/{filename}",
            media_type=media_type,
        )

    async def create_post(
        self,
        title: str,
        content: str,
        *,
        status: str = "draft",
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: Any,
    ) -> WPPostResult:
        self.create_post_calls.append(
            {
                "title": title,
                "content": content,
                "status": status,
                "categories": categories,
                "featured_media": featured_media,
                "kwargs": kwargs,
            }
        )
        return self._post_result

    async def update_post(
        self,
        post_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: Any,
    ) -> WPPostResult:
        return self._post_result

    async def list_categories(
        self,
        *,
        per_page: int = 100,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def get_post(self, post_id: int) -> WPPostResult:
        return self._post_result

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return len(self.upload_media_calls) + len(self.create_post_calls)
