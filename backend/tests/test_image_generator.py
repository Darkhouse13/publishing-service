"""Tests for ImageGeneratorService — image generation and download via provider.

Tests cover:
- Calls provider.generate() with correct prompt and dimensions
- Downloads image from returned URL via httpx
- Saves to output_dir with naming convention {image_kind}_{uuid_hex[:10]}.jpg
- Returns absolute local path
- Error handling when provider fails or download fails
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.base import ImageProvider, ImageResult
from app.services.image_generator import (
    ImageDownloadError,
    ImageGeneratorService,
    _build_filename,
)


# ---------------------------------------------------------------------------
# Mock Image Provider
# ---------------------------------------------------------------------------


class MockImageProvider(ImageProvider):
    """A mock image provider that returns a pre-configured ImageResult."""

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


class FailingImageProvider(ImageProvider):
    """A mock image provider that always raises an error."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or RuntimeError("Image generation failed")

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> ImageResult:
        raise self._error

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helper to create fake JPEG bytes and mock httpx context
# ---------------------------------------------------------------------------

FAKE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
    b"\xff\xd9"
)


def _mock_httpx_context(
    content: bytes = FAKE_JPEG_BYTES,
    raise_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Create a mocked httpx.AsyncClient that returns the given content.

    Returns:
        Tuple of (mock_client_cls, mock_client) for assertion purposes.
    """
    mock_response = MagicMock()
    mock_response.content = content
    if raise_error:
        mock_response.raise_for_status.side_effect = raise_error
    else:
        mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_client_cls = MagicMock(return_value=mock_client)
    return mock_client_cls, mock_client


# ---------------------------------------------------------------------------
# Unit tests for _build_filename helper
# ---------------------------------------------------------------------------


class TestBuildFilename:
    """Tests for the _build_filename utility function."""

    def test_filename_format(self) -> None:
        """Filename follows {image_kind}_{uuid_hex[:10]}.jpg pattern."""
        filename = _build_filename("hero")
        assert filename.startswith("hero_")
        assert filename.endswith(".jpg")
        # Extract the middle part: should be 10 hex chars
        middle = filename[len("hero_") : -len(".jpg")]
        assert len(middle) == 10
        assert re.match(r"^[0-9a-f]{10}$", middle)

    def test_filename_different_kinds(self) -> None:
        """Different image kinds produce different prefixes."""
        hero = _build_filename("hero")
        detail = _build_filename("detail")
        assert hero.startswith("hero_")
        assert detail.startswith("detail_")

    def test_filename_unique(self) -> None:
        """Two calls produce different filenames (different UUIDs)."""
        first = _build_filename("hero")
        second = _build_filename("hero")
        assert first != second


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


class TestImageGeneratorService:
    """Tests for ImageGeneratorService.generate_image()."""

    async def test_calls_provider_with_prompt(self, tmp_path: Path) -> None:
        """VAL-IMGS-001: Service calls provider.generate() with the prompt."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            await service.generate_image(
                prompt="A beautiful sunset over the ocean",
                image_kind="hero",
                output_dir=tmp_path,
            )

        assert provider.call_count == 1
        assert provider.call_args[0]["prompt"] == "A beautiful sunset over the ocean"

    async def test_calls_provider_with_dimensions(self, tmp_path: Path) -> None:
        """Service calls provider.generate() with width and height."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            await service.generate_image(
                prompt="A mountain scene",
                image_kind="detail",
                output_dir=tmp_path,
                width=768,
                height=512,
            )

        assert provider.call_args[0]["width"] == 768
        assert provider.call_args[0]["height"] == 512

    async def test_downloads_image_from_url(self, tmp_path: Path) -> None:
        """Service downloads image from the URL returned by provider."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, mock_client = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        # Verify httpx client.get was called with the provider's URL
        mock_client.get.assert_awaited_once_with(
            "https://example.com/generated_image.jpg"
        )

    async def test_saves_image_to_output_dir(self, tmp_path: Path) -> None:
        """VAL-IMGS-002: Service saves image to the specified output directory."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            result_path = await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        # File exists
        assert Path(result_path).exists()
        # File has content
        assert Path(result_path).stat().st_size > 0
        # File is in the output directory
        assert str(Path(result_path).parent) == str(tmp_path)

    async def test_saves_with_correct_naming_convention(self, tmp_path: Path) -> None:
        """File follows {image_kind}_{uuid_hex[:10]}.jpg naming."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            result_path = await service.generate_image(
                prompt="Test prompt",
                image_kind="detail",
                output_dir=tmp_path,
            )

        filename = Path(result_path).name
        assert re.match(r"^detail_[0-9a-f]{10}\.jpg$", filename)

    async def test_returns_absolute_local_path(self, tmp_path: Path) -> None:
        """VAL-IMGS-003: Method returns the absolute local file path."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            result_path = await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        assert os.path.isabs(result_path)
        assert result_path.endswith(".jpg")
        assert "hero_" in result_path

    async def test_provider_failure_raises_error(self, tmp_path: Path) -> None:
        """Service raises ImageDownloadError when provider fails."""
        provider = FailingImageProvider(RuntimeError("API rate limit exceeded"))
        service = ImageGeneratorService(provider=provider)

        with pytest.raises(ImageDownloadError) as exc_info:
            await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        assert "API rate limit exceeded" in str(exc_info.value)

    async def test_download_failure_raises_error(self, tmp_path: Path) -> None:
        """Service raises ImageDownloadError when download fails."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context(
            content=b"",
            raise_error=Exception("HTTP 404"),
        )

        with patch("httpx.AsyncClient", mock_cls):
            with pytest.raises(ImageDownloadError) as exc_info:
                await service.generate_image(
                    prompt="Test prompt",
                    image_kind="hero",
                    output_dir=tmp_path,
                )

        assert "HTTP 404" in str(exc_info.value)

    async def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        """Service creates the output directory if it doesn't exist."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        nested_dir = tmp_path / "images" / "hero"
        assert not nested_dir.exists()

        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            result_path = await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=nested_dir,
            )

        assert nested_dir.exists()
        assert Path(result_path).exists()

    async def test_method_is_async(self) -> None:
        """VAL-NFR-002: generate_image is an async method."""
        import inspect

        assert inspect.iscoroutinefunction(
            ImageGeneratorService.generate_image
        )

    async def test_default_dimensions(self, tmp_path: Path) -> None:
        """Default dimensions are 1024x1024."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        assert provider.call_args[0]["width"] == 1024
        assert provider.call_args[0]["height"] == 1024

    async def test_uses_httpx_async_client(self, tmp_path: Path) -> None:
        """Service uses httpx.AsyncClient for downloading the image."""
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        # Verify httpx.AsyncClient was instantiated
        mock_cls.assert_called_once()

    async def test_file_content_matches_download(self, tmp_path: Path) -> None:
        """Saved file content matches the bytes downloaded from URL."""
        custom_bytes = b"\xff\xd8\xff\xe0CUSTOM_IMAGE_DATA\xff\xd9"
        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context(content=custom_bytes)

        with patch("httpx.AsyncClient", mock_cls):
            result_path = await service.generate_image(
                prompt="Test prompt",
                image_kind="hero",
                output_dir=tmp_path,
            )

        saved_content = Path(result_path).read_bytes()
        assert saved_content == custom_bytes

    async def test_log_info_on_success(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """VAL-NFR-003: Service logs at INFO level on successful generation."""
        import logging

        provider = MockImageProvider()
        service = ImageGeneratorService(provider=provider)
        mock_cls, _ = _mock_httpx_context()

        with patch("httpx.AsyncClient", mock_cls):
            with caplog.at_level(logging.INFO, logger="app.services.image_generator"):
                await service.generate_image(
                    prompt="Test prompt",
                    image_kind="hero",
                    output_dir=tmp_path,
                )

        assert any(
            "saved" in record.message.lower()
            for record in caplog.records
        )

    async def test_log_error_on_provider_failure(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """VAL-NFR-005: Service logs at ERROR level on failure."""
        import logging

        provider = FailingImageProvider(RuntimeError("API error"))
        service = ImageGeneratorService(provider=provider)

        with caplog.at_level(logging.ERROR, logger="app.services.image_generator"):
            with pytest.raises(ImageDownloadError):
                await service.generate_image(
                    prompt="Test prompt",
                    image_kind="hero",
                    output_dir=tmp_path,
                )

        assert any(
            "failed" in record.message.lower()
            for record in caplog.records
        )
