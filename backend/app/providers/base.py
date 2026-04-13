"""Provider ABCs and result dataclasses for the Provider Abstraction Layer.

Defines the abstract interfaces that all concrete providers must implement:
- :class:`LLMProvider` — text generation (DeepSeek, OpenAI, etc.)
- :class:`ImageProvider` — image generation (Fal.ai, DALL-E, etc.)
- :class:`WordPressProvider` — WordPress REST API operations

Each provider method is async and returns a typed dataclass so callers
never depend on a specific vendor's response format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMResponse:
    """Structured response from an LLM completion request.

    Attributes:
        text: The generated text content.
        model: The model identifier used for generation (e.g. ``"deepseek-chat"``).
        usage: Token usage statistics. Keys typically include
            ``"prompt_tokens"``, ``"completion_tokens"``, ``"total_tokens"``.
        finish_reason: Why generation stopped (e.g. ``"stop"``, ``"length"``).
    """

    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


@dataclass(frozen=True)
class ImageResult:
    """Result of an image generation request.

    Attributes:
        url: Publicly accessible URL of the generated image.
        alt_text: Description of the image content (for accessibility).
        width: Image width in pixels.
        height: Image height in pixels.
    """

    url: str
    alt_text: str = ""
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class WPMediaResult:
    """Result of a WordPress media upload.

    Attributes:
        id: The WordPress media item ID.
        url: The URL of the uploaded media.
        media_type: MIME type of the uploaded file (e.g. ``"image/jpeg"``).
    """

    id: int
    url: str
    media_type: str = ""


@dataclass(frozen=True)
class WPPostResult:
    """Result of a WordPress post creation or update.

    Attributes:
        id: The WordPress post ID.
        url: The public permalink of the post.
        status: Publication status (e.g. ``"publish"``, ``"draft"``).
        title: The post title.
    """

    id: int
    url: str
    status: str = "draft"
    title: str = ""


# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract interface for LLM text generation providers.

    Concrete implementations must support generating text from a prompt
    with optional system instructions and generation parameters.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate text from a prompt.

        Args:
            prompt: The user prompt / message content.
            system_prompt: Optional system instructions to guide generation.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (0.0 – 2.0).

        Returns:
            A :class:`LLMResponse` containing the generated text and metadata.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release underlying resources (e.g. HTTP client)."""


class ImageProvider(ABC):
    """Abstract interface for image generation providers.

    Concrete implementations must support generating an image from a
    text prompt and returning a publicly accessible URL.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
    ) -> ImageResult:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the desired image.
            width: Desired image width in pixels.
            height: Desired image height in pixels.

        Returns:
            An :class:`ImageResult` with the image URL and metadata.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release underlying resources (e.g. HTTP client)."""


class WordPressProvider(ABC):
    """Abstract interface for WordPress REST API providers.

    Concrete implementations must support the core publishing operations:
    creating posts, uploading media, and querying categories.
    """

    @abstractmethod
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
        """Create a new WordPress post.

        Args:
            title: Post title.
            content: Post body HTML.
            status: Publication status (``"draft"``, ``"publish"``, etc.).
            categories: List of WordPress category IDs.
            featured_media: ID of the featured image media attachment.
            **kwargs: Additional WordPress REST API fields.

        Returns:
            A :class:`WPPostResult` with the created post's details.
        """

    @abstractmethod
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
        """Update an existing WordPress post.

        Args:
            post_id: The ID of the post to update.
            title: New title (if provided).
            content: New body HTML (if provided).
            status: New publication status (if provided).
            categories: New category IDs (if provided).
            featured_media: New featured image ID (if provided).
            **kwargs: Additional fields to update.

        Returns:
            A :class:`WPPostResult` with the updated post's details.
        """

    @abstractmethod
    async def upload_media(
        self,
        file_data: bytes,
        filename: str,
        *,
        media_type: str = "image/jpeg",
        alt_text: str = "",
        title: str | None = None,
    ) -> WPMediaResult:
        """Upload a media file to WordPress.

        Args:
            file_data: Raw file bytes.
            filename: Name for the uploaded file (e.g. ``"hero.jpg"``).
            media_type: MIME type of the file.
            alt_text: Alternative text for accessibility.
            title: Optional media library title.

        Returns:
            A :class:`WPMediaResult` with the uploaded media's details.
        """

    @abstractmethod
    async def list_categories(
        self,
        *,
        per_page: int = 100,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """List WordPress categories.

        Args:
            per_page: Maximum number of categories to return.
            search: Filter categories by name.

        Returns:
            A list of category dicts (``id``, ``name``, ``slug``, etc.).
        """

    @abstractmethod
    async def get_post(self, post_id: int) -> WPPostResult:
        """Retrieve a single WordPress post by ID.

        Args:
            post_id: The WordPress post ID.

        Returns:
            A :class:`WPPostResult` with the post's details.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release underlying resources (e.g. HTTP client)."""
