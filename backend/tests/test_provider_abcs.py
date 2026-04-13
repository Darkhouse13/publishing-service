"""Tests for the Provider Abstraction Layer ABCs and dataclasses.

Validates:
- Dataclass construction and field access for all result types
- Frozen (immutable) dataclass behaviour
- ABC instantiation prevention
- Required method enforcement on concrete subclasses
- Async method signatures on minimal concrete implementations
- Re-exports from sub-packages
"""

from __future__ import annotations

from typing import Any

import pytest

from app.providers import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
    WPMediaResult,
    WPPostResult,
    WordPressProvider,
)
from app.providers.base import (
    ImageProvider as BaseImageProvider,
    LLMProvider as BaseLLMProvider,
    WordPressProvider as BaseWPProvider,
)


# ===================================================================
# LLMResponse dataclass tests
# ===================================================================


class TestLLMResponse:
    """Tests for the LLMResponse dataclass."""

    def test_construction_with_all_fields(self) -> None:
        resp = LLMResponse(
            text="Hello world",
            model="deepseek-chat",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            finish_reason="stop",
        )
        assert resp.text == "Hello world"
        assert resp.model == "deepseek-chat"
        assert resp.usage["total_tokens"] == 30
        assert resp.finish_reason == "stop"

    def test_default_usage_is_empty_dict(self) -> None:
        resp = LLMResponse(text="test", model="gpt-4")
        assert resp.usage == {}

    def test_default_finish_reason_is_stop(self) -> None:
        resp = LLMResponse(text="test", model="gpt-4")
        assert resp.finish_reason == "stop"

    def test_frozen_prevents_mutation(self) -> None:
        resp = LLMResponse(text="test", model="gpt-4")
        with pytest.raises(AttributeError):
            resp.text = "mutated"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = LLMResponse(text="hi", model="m")
        b = LLMResponse(text="hi", model="m")
        assert a == b

    def test_inequality(self) -> None:
        a = LLMResponse(text="hi", model="m1")
        b = LLMResponse(text="hi", model="m2")
        assert a != b


# ===================================================================
# ImageResult dataclass tests
# ===================================================================


class TestImageResult:
    """Tests for the ImageResult dataclass."""

    def test_construction_with_all_fields(self) -> None:
        result = ImageResult(
            url="https://cdn.example.com/img.png",
            alt_text="A sunset",
            width=1024,
            height=768,
        )
        assert result.url == "https://cdn.example.com/img.png"
        assert result.alt_text == "A sunset"
        assert result.width == 1024
        assert result.height == 768

    def test_defaults(self) -> None:
        result = ImageResult(url="https://cdn.example.com/img.png")
        assert result.alt_text == ""
        assert result.width == 0
        assert result.height == 0

    def test_frozen_prevents_mutation(self) -> None:
        result = ImageResult(url="https://cdn.example.com/img.png")
        with pytest.raises(AttributeError):
            result.url = "new"  # type: ignore[misc]


# ===================================================================
# WPMediaResult dataclass tests
# ===================================================================


class TestWPMediaResult:
    """Tests for the WPMediaResult dataclass."""

    def test_construction_with_all_fields(self) -> None:
        result = WPMediaResult(
            id=42,
            url="https://blog.com/wp-content/uploads/2024/01/img.jpg",
            media_type="image/jpeg",
        )
        assert result.id == 42
        assert "img.jpg" in result.url
        assert result.media_type == "image/jpeg"

    def test_default_media_type(self) -> None:
        result = WPMediaResult(id=1, url="https://blog.com/file.png")
        assert result.media_type == ""

    def test_frozen_prevents_mutation(self) -> None:
        result = WPMediaResult(id=1, url="https://blog.com/file.png")
        with pytest.raises(AttributeError):
            result.id = 99  # type: ignore[misc]


# ===================================================================
# WPPostResult dataclass tests
# ===================================================================


class TestWPPostResult:
    """Tests for the WPPostResult dataclass."""

    def test_construction_with_all_fields(self) -> None:
        result = WPPostResult(
            id=10,
            url="https://blog.com/hello-world/",
            status="publish",
            title="Hello World",
        )
        assert result.id == 10
        assert "hello-world" in result.url
        assert result.status == "publish"
        assert result.title == "Hello World"

    def test_defaults(self) -> None:
        result = WPPostResult(id=5, url="https://blog.com/post/")
        assert result.status == "draft"
        assert result.title == ""

    def test_frozen_prevents_mutation(self) -> None:
        result = WPPostResult(id=5, url="https://blog.com/post/")
        with pytest.raises(AttributeError):
            result.status = "publish"  # type: ignore[misc]


# ===================================================================
# ABC instantiation tests
# ===================================================================


class TestLLMProviderABC:
    """Tests for the LLMProvider abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    async def test_minimal_concrete_subclass(self) -> None:
        """A concrete subclass that implements all abstract methods can be instantiated."""

        class FakeLLM(LLMProvider):
            def __init__(self) -> None:
                self._closed = False

            async def generate(
                self,
                prompt: str,
                *,
                system_prompt: str | None = None,
                max_tokens: int = 4096,
                temperature: float = 0.7,
            ) -> LLMResponse:
                return LLMResponse(text=f"echo: {prompt}", model="fake")

            async def close(self) -> None:
                self._closed = True

        provider = FakeLLM()
        result = await provider.generate("hello")
        assert result.text == "echo: hello"
        assert result.model == "fake"

        await provider.close()
        assert provider._closed is True

    def test_missing_generate_raises_type_error(self) -> None:
        """A subclass that doesn't implement generate() cannot be instantiated."""

        with pytest.raises(TypeError):

            class IncompleteLLM(LLMProvider):
                async def close(self) -> None:
                    pass

            IncompleteLLM()  # type: ignore[abstract]

    def test_missing_close_raises_type_error(self) -> None:
        """A subclass that doesn't implement close() cannot be instantiated."""

        with pytest.raises(TypeError):

            class IncompleteLLM2(LLMProvider):
                async def generate(
                    self,
                    prompt: str,
                    *,
                    system_prompt: str | None = None,
                    max_tokens: int = 4096,
                    temperature: float = 0.7,
                ) -> LLMResponse:
                    return LLMResponse(text="", model="")

            IncompleteLLM2()  # type: ignore[abstract]

    async def test_generate_with_all_params(self) -> None:
        """Verify the generate method signature accepts all documented params."""

        class SpyLLM(LLMProvider):
            last_kwargs: dict[str, Any]

            async def generate(
                self,
                prompt: str,
                *,
                system_prompt: str | None = None,
                max_tokens: int = 4096,
                temperature: float = 0.7,
            ) -> LLMResponse:
                self.last_kwargs = {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                return LLMResponse(text="", model="spy")

            async def close(self) -> None:
                pass

        provider = SpyLLM()
        await provider.generate(
            "test prompt",
            system_prompt="You are helpful",
            max_tokens=100,
            temperature=0.3,
        )
        assert provider.last_kwargs["prompt"] == "test prompt"
        assert provider.last_kwargs["system_prompt"] == "You are helpful"
        assert provider.last_kwargs["max_tokens"] == 100
        assert provider.last_kwargs["temperature"] == 0.3


class TestImageProviderABC:
    """Tests for the ImageProvider abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            ImageProvider()  # type: ignore[abstract]

    async def test_minimal_concrete_subclass(self) -> None:
        class FakeImage(ImageProvider):
            async def generate(
                self,
                prompt: str,
                *,
                width: int = 1024,
                height: int = 1024,
            ) -> ImageResult:
                return ImageResult(
                    url="https://cdn.example.com/generated.png",
                    alt_text=prompt,
                    width=width,
                    height=height,
                )

            async def close(self) -> None:
                pass

        provider = FakeImage()
        result = await provider.generate("a sunset", width=512, height=512)
        assert result.url == "https://cdn.example.com/generated.png"
        assert result.alt_text == "a sunset"
        assert result.width == 512
        assert result.height == 512

    async def test_generate_default_dimensions(self) -> None:
        class FakeImage2(ImageProvider):
            last_dims: tuple[int, int]

            async def generate(
                self,
                prompt: str,
                *,
                width: int = 1024,
                height: int = 1024,
            ) -> ImageResult:
                self.last_dims = (width, height)
                return ImageResult(url="https://example.com/img.png")

            async def close(self) -> None:
                pass

        provider = FakeImage2()
        await provider.generate("test")
        assert provider.last_dims == (1024, 1024)


class TestWordPressProviderABC:
    """Tests for the WordPressProvider abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            WordPressProvider()  # type: ignore[abstract]

    async def test_minimal_concrete_subclass(self) -> None:
        """Verify all abstract methods can be implemented by a concrete class."""

        class FakeWP(WordPressProvider):
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
                return WPPostResult(
                    id=1,
                    url=f"https://blog.com/{title.lower().replace(' ', '-')}/",
                    status=status,
                    title=title,
                )

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
                return WPPostResult(
                    id=post_id,
                    url="https://blog.com/post/",
                    status=status or "draft",
                    title=title or "",
                )

            async def upload_media(
                self,
                file_data: bytes,
                filename: str,
                *,
                media_type: str = "image/jpeg",
                alt_text: str = "",
                title: str | None = None,
            ) -> WPMediaResult:
                return WPMediaResult(
                    id=99,
                    url=f"https://blog.com/wp-content/uploads/{filename}",
                    media_type=media_type,
                )

            async def list_categories(
                self,
                *,
                per_page: int = 100,
                search: str | None = None,
            ) -> list[dict[str, Any]]:
                return [{"id": 1, "name": "Uncategorized", "slug": "uncategorized"}]

            async def get_post(self, post_id: int) -> WPPostResult:
                return WPPostResult(
                    id=post_id,
                    url="https://blog.com/post/",
                    status="publish",
                    title="Test Post",
                )

            async def close(self) -> None:
                pass

        wp = FakeWP()

        # Test create_post
        post = await wp.create_post("Hello World", "<p>Content</p>", status="publish")
        assert post.id == 1
        assert post.title == "Hello World"
        assert post.status == "publish"

        # Test update_post
        updated = await wp.update_post(1, title="Updated")
        assert updated.id == 1
        assert updated.title == "Updated"

        # Test upload_media
        media = await wp.upload_media(b"fake image bytes", "hero.jpg")
        assert media.id == 99
        assert "hero.jpg" in media.url
        assert media.media_type == "image/jpeg"

        # Test list_categories
        cats = await wp.list_categories()
        assert len(cats) == 1
        assert cats[0]["name"] == "Uncategorized"

        # Test get_post
        fetched = await wp.get_post(1)
        assert fetched.id == 1
        assert fetched.status == "publish"

    def test_missing_method_raises_type_error(self) -> None:
        """A subclass missing any abstract method cannot be instantiated."""

        with pytest.raises(TypeError):

            class IncompleteWP(WordPressProvider):
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
                    return WPPostResult(id=0, url="")

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
                    return WPPostResult(id=0, url="")

                async def upload_media(
                    self,
                    file_data: bytes,
                    filename: str,
                    *,
                    media_type: str = "image/jpeg",
                    alt_text: str = "",
                    title: str | None = None,
                ) -> WPMediaResult:
                    return WPMediaResult(id=0, url="")

                async def list_categories(
                    self,
                    *,
                    per_page: int = 100,
                    search: str | None = None,
                ) -> list[dict[str, Any]]:
                    return []

                async def get_post(self, post_id: int) -> WPPostResult:
                    return WPPostResult(id=0, url="")

                # Missing close()

            IncompleteWP()  # type: ignore[abstract]


# ===================================================================
# Re-export / import tests
# ===================================================================


class TestReExports:
    """Verify that ABCs and dataclasses are accessible from expected import paths."""

    def test_top_level_package_exports(self) -> None:
        """app.providers re-exports all public names."""
        from app.providers import (
            ImageProvider,
            ImageResult,
            LLMProvider,
            LLMResponse,
            WPMediaResult,
            WPPostResult,
            WordPressProvider,
        )

        # Verify they are the same objects as in base module
        from app.providers.base import (
            ImageProvider as IP,
            ImageResult as IR,
            LLMProvider as LP,
            LLMResponse as LR,
            WPMediaResult as WM,
            WPPostResult as WP,
            WordPressProvider as WPP,
        )

        assert LLMProvider is LP
        assert LLMResponse is LR
        assert ImageProvider is IP
        assert ImageResult is IR
        assert WordPressProvider is WPP
        assert WPPostResult is WP
        assert WPMediaResult is WM

    def test_llm_subpackage_import(self) -> None:
        """app.providers.llm exports LLMProvider."""
        from app.providers.llm import LLMProvider

        assert LLMProvider is BaseLLMProvider

    def test_image_subpackage_import(self) -> None:
        """app.providers.image exports ImageProvider."""
        from app.providers.image import ImageProvider

        assert ImageProvider is BaseImageProvider

    def test_wordpress_subpackage_import(self) -> None:
        """app.providers.wordpress exports WordPressProvider."""
        from app.providers.wordpress import WordPressProvider

        assert WordPressProvider is BaseWPProvider
