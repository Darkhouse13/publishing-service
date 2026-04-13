"""Tests for PublisherService — WordPress publishing flow.

Tests cover:
- VAL-PUBS-001: Converts markdown to well-formed HTML
- VAL-PUBS-002: Uploads hero and detail images (2 upload_media calls)
- VAL-PUBS-003: Injects detail image after first paragraph
- VAL-PUBS-004: Creates post with media, categories, SEO meta
- VAL-PUBS-005: Returns PublishResult with post_id and permalink
- Respects publish_status from config (draft/publish)
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any

import pytest

from app.providers.base import (
    WordPressProvider,
    WPMediaResult,
    WPPostResult,
)
from app.services.publisher import (
    PublishResult,
    PublisherService,
    PublishingError,
    markdown_to_html,
    inject_detail_image_after_first_paragraph,
)


# ---------------------------------------------------------------------------
# Mock WordPress Provider
# ---------------------------------------------------------------------------


class MockWordPressProvider(WordPressProvider):
    """A mock WordPress provider that tracks calls and returns pre-configured results."""

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
        # Return incrementing IDs for each upload
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


class FailingUploadProvider(MockWordPressProvider):
    """A mock WordPress provider that fails on upload_media."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self._error = error or RuntimeError("Upload failed")

    async def upload_media(
        self,
        file_data: bytes,
        filename: str,
        *,
        media_type: str = "image/jpeg",
        alt_text: str = "",
        title: str | None = None,
    ) -> WPMediaResult:
        raise self._error


class FailingCreatePostProvider(MockWordPressProvider):
    """A mock WordPress provider that fails on create_post."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self._error = error or RuntimeError("Post creation failed")

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
        raise self._error


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def wp_provider() -> MockWordPressProvider:
    """Provide a fresh MockWordPressProvider."""
    return MockWordPressProvider()


@pytest.fixture()
def service() -> PublisherService:
    """Provide a PublisherService with a mock provider."""
    provider = MockWordPressProvider()
    return PublisherService(provider=provider)


@pytest.fixture()
def sample_markdown() -> str:
    """Provide sample markdown content."""
    return (
        "# How to Build a Patio\n\n"
        "Building a patio is a great way to enjoy your outdoor space. "
        "You can choose from various materials like concrete, stone, or pavers.\n\n"
        "## Choosing Materials\n\n"
        "When selecting materials for your patio, consider durability and aesthetics. "
        "Concrete is affordable, while natural stone offers a premium look.\n\n"
        "## Planning Your Layout\n\n"
        "A good layout is essential for any patio project. "
        "Measure your space carefully and plan for proper drainage."
    )


@pytest.fixture()
def hero_image_path(tmp_path: Path) -> Path:
    """Create a temporary hero image file."""
    path = tmp_path / "hero_test.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0FAKE_HERO\xff\xd9")
    return path


@pytest.fixture()
def detail_image_path(tmp_path: Path) -> Path:
    """Create a temporary detail image file."""
    path = tmp_path / "detail_test.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0FAKE_DETAIL\xff\xd9")
    return path


# ---------------------------------------------------------------------------
# Tests: markdown_to_html
# ---------------------------------------------------------------------------


class TestMarkdownToHtml:
    """Tests for the markdown_to_html helper function."""

    def test_converts_paragraphs(self) -> None:
        """VAL-PUBS-001: Markdown paragraphs are wrapped in <p> tags."""
        html = markdown_to_html("Hello world")
        assert "<p>" in html
        assert "</p>" in html
        assert "Hello world" in html

    def test_converts_headings(self) -> None:
        """VAL-PUBS-001: Markdown headings are converted to HTML h-tags."""
        html = markdown_to_html("## My Heading")
        assert "<h2>" in html or "<h2 " in html
        assert "My Heading" in html

    def test_converts_h1(self) -> None:
        """H1 headings are converted to h1 tags."""
        html = markdown_to_html("# Title")
        assert "<h1>" in html or "<h1 " in html
        assert "Title" in html

    def test_converts_bold_and_italic(self) -> None:
        """Bold and italic formatting is converted."""
        html = markdown_to_html("**bold** and *italic*")
        assert "<strong>" in html or "<b>" in html
        assert "<em>" in html or "<i>" in html

    def test_converts_links(self) -> None:
        """Markdown links are converted to HTML anchor tags."""
        html = markdown_to_html("[click here](https://example.com)")
        assert "<a" in html
        assert "https://example.com" in html

    def test_empty_input_raises(self) -> None:
        """Empty markdown raises PublishingError."""
        with pytest.raises(PublishingError):
            markdown_to_html("")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only markdown raises PublishingError."""
        with pytest.raises(PublishingError):
            markdown_to_html("   \n  \t  ")

    def test_complex_markdown(self) -> None:
        """Complex markdown with multiple elements is converted correctly."""
        md = (
            "# Title\n\n"
            "A paragraph with **bold** text.\n\n"
            "## Section\n\n"
            "Another paragraph with [a link](https://example.com).\n\n"
            "- List item 1\n"
            "- List item 2\n"
        )
        html = markdown_to_html(md)
        assert "<h1>" in html or "<h1 " in html
        assert "<h2>" in html or "<h2 " in html
        assert "<p>" in html
        assert "<strong>" in html or "<b>" in html
        assert "<a" in html
        assert "<li>" in html


# ---------------------------------------------------------------------------
# Tests: inject_detail_image_after_first_paragraph
# ---------------------------------------------------------------------------


class TestInjectDetailImage:
    """Tests for the inject_detail_image_after_first_paragraph helper."""

    def test_injects_after_first_paragraph(self) -> None:
        """VAL-PUBS-003: Detail image is injected after first </p>."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        result = inject_detail_image_after_first_paragraph(
            content_html=html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="Detail image",
        )
        # Detail image should appear after first </p>
        first_p_end = result.find("</p>")
        assert first_p_end != -1
        after_first_p = result[first_p_end + len("</p>"):]
        assert "<img" in after_first_p
        assert "https://example.com/detail.jpg" in after_first_p

    def test_image_is_before_second_paragraph(self) -> None:
        """Detail image appears between first and second paragraph."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        result = inject_detail_image_after_first_paragraph(
            content_html=html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="Detail image",
        )
        # The second <p> should come AFTER the detail image
        first_p_close = result.index("</p>")
        second_p_open = result.index("<p>", first_p_close + 1)
        detail_img_pos = result.index("detail.jpg")
        assert first_p_close < detail_img_pos < second_p_open

    def test_no_paragraph_appends_image(self) -> None:
        """When no </p> found, image is appended to end."""
        html = "<div>No paragraphs here</div>"
        result = inject_detail_image_after_first_paragraph(
            content_html=html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="Detail image",
        )
        assert "<img" in result
        assert "detail.jpg" in result

    def test_alt_text_included(self) -> None:
        """Alt text is set on the injected image."""
        html = "<p>First paragraph.</p>"
        result = inject_detail_image_after_first_paragraph(
            content_html=html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="My custom alt text",
        )
        assert "My custom alt text" in result

    def test_empty_html_raises(self) -> None:
        """Empty HTML raises PublishingError."""
        with pytest.raises(PublishingError):
            inject_detail_image_after_first_paragraph(
                content_html="",
                detail_image_url="https://example.com/detail.jpg",
                alt_text="Detail",
            )

    def test_empty_url_raises(self) -> None:
        """Empty detail URL raises PublishingError."""
        with pytest.raises(PublishingError):
            inject_detail_image_after_first_paragraph(
                content_html="<p>Content</p>",
                detail_image_url="",
                alt_text="Detail",
            )

    def test_image_has_loading_lazy(self) -> None:
        """Injected image includes loading='lazy' attribute."""
        html = "<p>First paragraph.</p>"
        result = inject_detail_image_after_first_paragraph(
            content_html=html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="Detail",
        )
        assert 'loading="lazy"' in result


# ---------------------------------------------------------------------------
# Tests: PublishResult dataclass
# ---------------------------------------------------------------------------


class TestPublishResult:
    """Tests for the PublishResult dataclass."""

    def test_has_wp_post_id(self) -> None:
        """VAL-PUBS-005: PublishResult has wp_post_id field."""
        result = PublishResult(wp_post_id=123, wp_permalink="https://example.com/post/")
        assert result.wp_post_id == 123

    def test_has_wp_permalink(self) -> None:
        """VAL-PUBS-005: PublishResult has wp_permalink field."""
        result = PublishResult(wp_post_id=123, wp_permalink="https://example.com/post/")
        assert result.wp_permalink == "https://example.com/post/"

    def test_frozen(self) -> None:
        """PublishResult is frozen (immutable)."""
        result = PublishResult(wp_post_id=123, wp_permalink="https://example.com/post/")
        with pytest.raises(AttributeError):
            result.wp_post_id = 456  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: PublisherService
# ---------------------------------------------------------------------------


class TestPublisherService:
    """Tests for PublisherService.publish_article()."""

    async def test_converts_markdown_to_html(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-001: Markdown content is converted to HTML before publishing."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio step by step.",
            seo_title="How to Build a Patio - Complete Guide",
            publish_status="draft",
        )
        # Verify the post content contains HTML tags, not markdown
        post_content = wp_provider.create_post_calls[0]["content"]
        assert "<p>" in post_content or "<h2>" in post_content or "<h1>" in post_content
        # Verify markdown syntax is NOT present (headings converted)
        assert "## Choosing Materials" not in post_content

    async def test_uploads_hero_and_detail_images(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-002: Both hero and detail images are uploaded (2 upload_media calls)."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        assert len(wp_provider.upload_media_calls) == 2

    async def test_uploads_hero_image_with_focus_keyword_alt_text(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Hero image is uploaded with alt text containing the focus keyword."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        hero_call = wp_provider.upload_media_calls[0]
        assert "patio building" in hero_call["alt_text"].lower() or "patio" in hero_call["alt_text"].lower()

    async def test_uploads_detail_image_with_alt_text(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Detail image is uploaded with alt text."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        detail_call = wp_provider.upload_media_calls[1]
        assert detail_call["alt_text"]  # Non-empty alt text

    async def test_injects_detail_image_after_first_paragraph(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-003: Detail image is injected after first paragraph in HTML."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        post_content = wp_provider.create_post_calls[0]["content"]
        # The detail image should be after the first </p> and before the second <p>
        first_close = post_content.index("</p>")
        detail_url = "detail_test.jpg"
        detail_pos = post_content.index(detail_url)
        assert detail_pos > first_close
        # There should be no second <p> between first close and detail image
        between = post_content[first_close + len("</p>"):detail_pos]
        assert "<p>" not in between

    async def test_creates_post_with_featured_media(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-004: Post is created with featured_media set to hero image ID."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["featured_media"] is not None
        # Hero was first upload (ID 100), detail was second (ID 101)
        assert post_call["featured_media"] == 100

    async def test_creates_post_with_categories(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-004: Post is created with category IDs."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
            categories=[5, 10],
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["categories"] == [5, 10]

    async def test_creates_post_with_seo_meta(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-004: Post is created with SEO metadata (rank_math fields)."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio step by step.",
            seo_title="How to Build a Patio - Complete Guide",
            publish_status="draft",
        )
        post_call = wp_provider.create_post_calls[0]
        kwargs = post_call["kwargs"]
        # SEO meta should be passed in kwargs
        assert "rank_math_title" in kwargs or "meta" in kwargs

    async def test_creates_post_with_title(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Post is created with the correct title."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="My Awesome Post Title",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["title"] == "My Awesome Post Title"

    async def test_returns_publish_result(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-PUBS-005: Returns PublishResult with wp_post_id and wp_permalink."""
        service = PublisherService(provider=wp_provider)
        result = await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        assert isinstance(result, PublishResult)
        assert result.wp_post_id is not None
        assert result.wp_permalink is not None
        assert isinstance(result.wp_post_id, int)
        assert isinstance(result.wp_permalink, str)

    async def test_respects_publish_status_draft(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Respects publish_status='draft' from config."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["status"] == "draft"

    async def test_respects_publish_status_publish(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """VAL-CROSS-010: Respects publish_status='publish' from config."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="publish",
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["status"] == "publish"

    async def test_upload_failure_raises_publishing_error(
        self,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Upload failure raises PublishingError."""
        provider = FailingUploadProvider(RuntimeError("Upload timeout"))
        service = PublisherService(provider=provider)
        with pytest.raises(PublishingError) as exc_info:
            await service.publish_article(
                title="How to Build a Patio",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )
        assert "Upload timeout" in str(exc_info.value)

    async def test_post_creation_failure_raises_publishing_error(
        self,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Post creation failure raises PublishingError."""
        provider = FailingCreatePostProvider(RuntimeError("Post creation failed"))
        service = PublisherService(provider=provider)
        with pytest.raises(PublishingError) as exc_info:
            await service.publish_article(
                title="How to Build a Patio",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )
        assert "Post creation failed" in str(exc_info.value)

    async def test_missing_title_raises_error(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Empty title raises PublishingError."""
        service = PublisherService(provider=wp_provider)
        with pytest.raises(PublishingError):
            await service.publish_article(
                title="",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )

    async def test_missing_markdown_raises_error(
        self,
        wp_provider: MockWordPressProvider,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Empty markdown raises PublishingError."""
        service = PublisherService(provider=wp_provider)
        with pytest.raises(PublishingError):
            await service.publish_article(
                title="My Post",
                content_markdown="",
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )

    async def test_missing_focus_keyword_raises_error(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """Empty focus_keyword raises PublishingError."""
        service = PublisherService(provider=wp_provider)
        with pytest.raises(PublishingError):
            await service.publish_article(
                title="My Post",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )

    async def test_missing_hero_image_raises_error(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        detail_image_path: Path,
    ) -> None:
        """Non-existent hero image file raises PublishingError."""
        service = PublisherService(provider=wp_provider)
        with pytest.raises(PublishingError):
            await service.publish_article(
                title="My Post",
                content_markdown=sample_markdown,
                hero_image_path=Path("/nonexistent/hero.jpg"),
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )

    async def test_missing_detail_image_raises_error(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
    ) -> None:
        """Non-existent detail image file raises PublishingError."""
        service = PublisherService(provider=wp_provider)
        with pytest.raises(PublishingError):
            await service.publish_article(
                title="My Post",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=Path("/nonexistent/detail.jpg"),
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )

    async def test_no_categories_default_none(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """When no categories provided, they default to None."""
        service = PublisherService(provider=wp_provider)
        await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        post_call = wp_provider.create_post_calls[0]
        assert post_call["categories"] is None

    async def test_method_is_async(self) -> None:
        """VAL-NFR-002: publish_article is an async method."""
        assert inspect.iscoroutinefunction(PublisherService.publish_article)

    async def test_log_info_on_success(
        self,
        wp_provider: MockWordPressProvider,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """VAL-NFR-003: Logs at INFO level on successful publish."""
        service = PublisherService(provider=wp_provider)
        with caplog.at_level(logging.INFO, logger="app.services.publisher"):
            await service.publish_article(
                title="How to Build a Patio",
                content_markdown=sample_markdown,
                hero_image_path=hero_image_path,
                detail_image_path=detail_image_path,
                focus_keyword="patio building",
                meta_description="Learn how to build a patio.",
                seo_title="How to Build a Patio",
                publish_status="draft",
            )
        assert any(
            "published" in record.message.lower() or "publish" in record.message.lower()
            for record in caplog.records
        )

    async def test_log_error_on_failure(
        self,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """VAL-NFR-005: Logs at ERROR level on failure."""
        provider = FailingUploadProvider(RuntimeError("Upload error"))
        service = PublisherService(provider=provider)
        with caplog.at_level(logging.ERROR, logger="app.services.publisher"):
            with pytest.raises(PublishingError):
                await service.publish_article(
                    title="How to Build a Patio",
                    content_markdown=sample_markdown,
                    hero_image_path=hero_image_path,
                    detail_image_path=detail_image_path,
                    focus_keyword="patio building",
                    meta_description="Learn how to build a patio.",
                    seo_title="How to Build a Patio",
                    publish_status="draft",
                )
        assert any(
            "failed" in record.message.lower() or "error" in record.message.lower()
            for record in caplog.records
        )

    async def test_publish_result_post_id_matches_wp_response(
        self,
        sample_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
    ) -> None:
        """PublishResult.wp_post_id matches the WPPostResult.id."""
        provider = MockWordPressProvider(
            post_result=WPPostResult(
                id=777,
                url="https://example.com/custom-post/",
                status="draft",
                title="Custom Post",
            )
        )
        service = PublisherService(provider=provider)
        result = await service.publish_article(
            title="How to Build a Patio",
            content_markdown=sample_markdown,
            hero_image_path=hero_image_path,
            detail_image_path=detail_image_path,
            focus_keyword="patio building",
            meta_description="Learn how to build a patio.",
            seo_title="How to Build a Patio",
            publish_status="draft",
        )
        assert result.wp_post_id == 777
        assert result.wp_permalink == "https://example.com/custom-post/"
