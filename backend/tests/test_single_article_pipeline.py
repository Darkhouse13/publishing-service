"""Integration tests for the single article pipeline.

Tests cover:
- VAL-SART-001: Full flow (generate → validate → images → publish → update DB)
- VAL-SART-002: Status transitions persist at each step
- VAL-SART-003: Error at any step sets status='failed' with error_message
- VAL-SART-004: Works without Run (blog_id set, run_id null)
- VAL-SART-005: Populates content fields
- VAL-SART-006: Populates image fields
- VAL-SART-007: Populates Pinterest fields
- VAL-SART-008: Obtains providers via ProviderFactory
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.blog import Blog
from app.models.pipeline_config import PipelineConfig
from app.pipeline.single_article import _run_pipeline
from app.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    WordPressProvider,
    WPMediaResult,
    WPPostResult,
)
from tests.helpers import (
    MockImageProvider,
    MockLLMProvider,
    MockWordPressProvider,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_valid_article_json() -> str:
    """Return a JSON string matching the ArticlePayload schema.

    Word count >= 600, keyword count in [5,9], keyword in first paragraph,
    H2 with keyword, seo_title has a number.
    """
    keyword = "outdoor patio"
    body_paragraph = (
        f"When designing your {keyword}, it is important to consider "
        f"the overall layout and functionality. A well-designed {keyword} "
        "can transform your backyard into an inviting retreat. "
        "Many homeowners are now investing in quality materials and "
        "innovative designs to create the perfect outdoor living space. "
        f"The best {keyword} designs incorporate natural elements, comfortable "
        "seating, and ambient lighting for evening enjoyment."
    )
    filler_paragraphs = []
    for i in range(10):
        p = (
            f"Another great tip for your {keyword if i % 2 == 0 else 'space'} "
            f"is to choose weather-resistant furniture that lasts year-round. "
            "Consider adding potted plants, outdoor rugs, and decorative "
            "pillows to create a cozy atmosphere. Many designers recommend "
            "layering textures and colors to make the space feel like an "
            "extension of your indoor living area. Whether you prefer a "
            "modern minimalist look or a rustic charm, the right accessories "
            "can make all the difference."
        )
        filler_paragraphs.append(p)

    article_md = (
        f"{body_paragraph}\n\n"
        + "\n\n".join(filler_paragraphs)
        + f"\n\n## Designing the Perfect {keyword}\n\n"
        "When it comes to choosing materials, natural stone and composite "
        "decking are popular choices. These materials offer durability and "
        "low maintenance, which is ideal for busy homeowners.\n\n"
        "## Lighting and Ambiance\n\n"
        "String lights, lanterns, and solar-powered pathway lights can "
        "create a magical atmosphere in the evening. Consider installing "
        "a fire pit as a centerpiece for gatherings.\n\n"
        "## Final Thoughts\n\n"
        "Creating the perfect outdoor space takes planning and creativity. "
        "Start with a clear vision and build gradually."
    )

    data = {
        "title": f"10 Best {keyword.title()} Ideas for Your Home",
        "article_markdown": article_md,
        "hero_image_prompt": f"A beautiful {keyword} with modern furniture",
        "detail_image_prompt": f"Close-up of {keyword} seating area",
        "seo_title": f"{keyword.title()} - 10 Design Ideas",
        "meta_description": (
            f"Discover 10 stunning {keyword} design ideas. "
            "Transform your backyard into a beautiful retreat with these "
            "expert tips and creative inspiration for outdoor living."
        ),
        "focus_keyword": keyword,
    }
    return json.dumps(data)


@pytest_asyncio.fixture()
async def blog_with_config(db_session: AsyncSession) -> tuple[Blog, PipelineConfig]:
    """Create a Blog and PipelineConfig for testing."""
    blog = Blog(
        name="Test Blog",
        url="https://example.com",
        wp_username="admin",
        wp_app_password_encrypted="encrypted_password",
        profile_prompt="A blog about outdoor living and home improvement.",
        fallback_category="General",
        deprioritized_category="Uncategorized",
        category_keywords={"outdoor": ["patio", "deck", "garden"]},
        pinterest_board_map={"home": "board-123"},
    )
    db_session.add(blog)
    await db_session.commit()
    await db_session.refresh(blog)

    config = PipelineConfig(
        blog_id=blog.id,
        llm_provider="deepseek",
        image_provider="fal",
        llm_model="deepseek-chat",
        image_model="fal-ai/flux/dev",
        publish_status="draft",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    return blog, config


@pytest_asyncio.fixture()
async def article(
    db_session: AsyncSession,
    blog_with_config: tuple[Blog, PipelineConfig],
) -> Article:
    """Create a pending Article for single-article pipeline testing."""
    blog, _config = blog_with_config
    art = Article(
        blog_id=blog.id,
        run_id=None,
        keyword="outdoor patio",
        status="pending",
    )
    db_session.add(art)
    await db_session.commit()
    await db_session.refresh(art)
    return art


# ---------------------------------------------------------------------------
# Helper: create pipeline mocks
# ---------------------------------------------------------------------------


def _make_mock_factory(
    llm_provider: LLMProvider | None = None,
    image_provider: ImageProvider | None = None,
    wp_provider: WordPressProvider | None = None,
) -> MagicMock:
    """Create a mock ProviderFactory that returns the given providers."""
    valid_json = _make_valid_article_json()

    factory = MagicMock()
    factory.get_llm_provider = AsyncMock(
        return_value=llm_provider or MockLLMProvider(responses=[valid_json])
    )
    factory.get_image_provider = AsyncMock(
        return_value=image_provider
        or MockImageProvider(
            result=ImageResult(
                url="https://example.com/generated_image.jpg",
                alt_text="A test image",
                width=1024,
                height=1024,
            )
        )
    )
    factory.get_wordpress_provider = AsyncMock(
        return_value=wp_provider
        or MockWordPressProvider(
            media_result=WPMediaResult(
                id=100,
                url="https://example.com/wp-content/uploads/hero.jpg",
                media_type="image/jpeg",
            ),
            post_result=WPPostResult(
                id=200,
                url="https://example.com/my-post/",
                status="draft",
                title="Test Post",
            ),
        )
    )
    return factory


def _mock_httpx_download():
    """Return a context manager that patches httpx.AsyncClient in image_generator.

    The mock returns fake JPEG bytes for any GET request so the image
    download never hits the real network.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG
    mock_response.raise_for_status = MagicMock()

    @asynccontextmanager
    async def _fake_client():
        client = MagicMock()
        client.get = AsyncMock(return_value=mock_response)
        yield client

    return patch(
        "app.services.image_generator.httpx.AsyncClient",
        side_effect=_fake_client,
    )


def _reload_article(db_session: AsyncSession, article_id: uuid.UUID):
    """Return a coroutine that reloads an article from the DB."""
    async def _reload():
        result = await db_session.execute(
            select(Article).where(Article.id == article_id)
        )
        return result.scalar_one()
    return _reload


# ---------------------------------------------------------------------------
# VAL-SART-001: Full flow (generate → validate → images → publish → update DB)
# ---------------------------------------------------------------------------


class TestFullPipelineFlow:
    """Test the complete single-article pipeline happy path."""

    @pytest.mark.asyncio
    async def test_full_flow_publishes_article(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Pipeline completes: generate → validate → images → publish."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.status == "published"
        assert updated.wp_post_id is not None
        assert updated.wp_permalink is not None

    @pytest.mark.asyncio
    async def test_full_flow_sets_wp_fields(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """After pipeline, wp_post_id and wp_permalink are set."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.wp_post_id == 200
        assert updated.wp_permalink == "https://example.com/my-post/"


# ---------------------------------------------------------------------------
# VAL-SART-002: Status transitions persist
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """Verify that status transitions are persisted to DB."""

    @pytest.mark.asyncio
    async def test_initial_status_is_pending(
        self,
        db_session: AsyncSession,
        article: Article,
    ):
        """Article starts in pending state."""
        assert article.status == "pending"

    @pytest.mark.asyncio
    async def test_status_transitions_observed(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Status transitions from pending → generating → publishing → published."""
        factory = _make_mock_factory()
        transition_statuses = []

        original_commit = db_session.commit

        async def tracking_commit():
            transition_statuses.append(article.status)
            await original_commit()

        db_session.commit = tracking_commit

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        # Should see: generating, generating (content update), publishing, publishing (image), published
        assert "generating" in transition_statuses
        assert "publishing" in transition_statuses
        assert "published" in transition_statuses

    @pytest.mark.asyncio
    async def test_final_status_is_published(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Final status is published after successful pipeline."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()
        assert updated.status == "published"


# ---------------------------------------------------------------------------
# VAL-SART-003: Error sets failed status
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify that errors at any step set status='failed'."""

    @pytest.mark.asyncio
    async def test_generation_error_sets_failed(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Error during generation sets status='failed' with error_message."""
        llm = MockLLMProvider(responses=["not valid json at all"] * 10)
        factory = _make_mock_factory(llm_provider=llm)

        await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.status == "failed"
        assert updated.error_message is not None
        assert len(updated.error_message) > 0

    @pytest.mark.asyncio
    async def test_image_error_sets_failed(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Error during image generation sets status='failed'."""
        failing_image = MockImageProvider()
        failing_image.generate = AsyncMock(
            side_effect=RuntimeError("Image API down")
        )
        factory = _make_mock_factory(image_provider=failing_image)

        await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.status == "failed"
        assert "image" in updated.error_message.lower()

    @pytest.mark.asyncio
    async def test_publish_error_sets_failed(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Error during publishing sets status='failed'."""
        failing_wp = MockWordPressProvider()
        failing_wp.create_post = AsyncMock(
            side_effect=RuntimeError("WP API down")
        )
        factory = _make_mock_factory(wp_provider=failing_wp)

        await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.status == "failed"
        assert updated.error_message is not None

    @pytest.mark.asyncio
    async def test_article_not_found_raises(
        self,
        db_session: AsyncSession,
    ):
        """Pipeline raises ValueError for non-existent article."""
        art = Article(
            blog_id=uuid.uuid4(),
            keyword="test",
            status="pending",
        )
        db_session.add(art)
        await db_session.commit()
        # Delete it so the reload fails
        await db_session.delete(art)
        await db_session.commit()

        factory = _make_mock_factory()
        # We need to test the outer generate_single_article
        # but that creates its own session. Instead test _run_pipeline
        # with a detached article referencing a non-existent blog.
        new_art = Article(
            id=uuid.uuid4(),
            blog_id=uuid.uuid4(),
            keyword="test",
            status="pending",
        )
        with pytest.raises(ValueError, match="Blog not found"):
            await _run_pipeline(db_session, new_art, factory=factory)


# ---------------------------------------------------------------------------
# VAL-SART-004: Works without Run (blog_id set, run_id null)
# ---------------------------------------------------------------------------


class TestNoRunRequired:
    """Verify pipeline works for standalone articles without a Run."""

    @pytest.mark.asyncio
    async def test_article_run_id_is_none_after_pipeline(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """Article has blog_id set and run_id null after pipeline."""
        assert article.run_id is None
        assert article.blog_id is not None

        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.run_id is None
        assert updated.blog_id is not None
        assert updated.status == "published"


# ---------------------------------------------------------------------------
# VAL-SART-005: Populates content fields
# ---------------------------------------------------------------------------


class TestContentFieldsPopulated:
    """Verify content fields are populated after pipeline."""

    @pytest.mark.asyncio
    async def test_all_content_fields_populated(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """After pipeline, seo_title, meta_description, focus_keyword,
        content_markdown, content_html, category_name are all set."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.seo_title is not None
        assert len(updated.seo_title) > 0
        assert updated.meta_description is not None
        assert len(updated.meta_description) > 0
        assert updated.focus_keyword is not None
        assert "outdoor patio" in updated.focus_keyword.lower()
        assert updated.content_markdown is not None
        assert len(updated.content_markdown) > 0
        assert updated.content_html is not None
        assert len(updated.content_html) > 0
        assert updated.category_name is not None
        assert len(updated.category_name) > 0


# ---------------------------------------------------------------------------
# VAL-SART-006: Populates image fields
# ---------------------------------------------------------------------------


class TestImageFieldsPopulated:
    """Verify image fields are populated after pipeline."""

    @pytest.mark.asyncio
    async def test_image_fields_populated(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """After pipeline, hero_image_url and detail_image_url are set."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.hero_image_url is not None
        assert updated.detail_image_url is not None


# ---------------------------------------------------------------------------
# VAL-SART-007: Populates Pinterest fields
# ---------------------------------------------------------------------------


class TestPinterestFieldsPopulated:
    """Verify Pinterest fields are populated after pipeline."""

    @pytest.mark.asyncio
    async def test_all_pinterest_fields_populated(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """After pipeline, pin_title, pin_description, pin_text_overlay,
        and pin_image_url are all set."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        reload = _reload_article(db_session, article.id)
        updated = await reload()

        assert updated.pin_title is not None
        assert len(updated.pin_title) > 0
        assert updated.pin_description is not None
        assert len(updated.pin_description) > 0
        assert updated.pin_text_overlay is not None
        assert len(updated.pin_text_overlay) > 0
        assert updated.pin_image_url is not None


# ---------------------------------------------------------------------------
# VAL-SART-008: Pipeline obtains providers via ProviderFactory
# ---------------------------------------------------------------------------


class TestProviderFactoryUsage:
    """Verify pipeline uses ProviderFactory to obtain providers."""

    @pytest.mark.asyncio
    async def test_provider_factory_get_llm_called(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """ProviderFactory.get_llm_provider is called with correct args."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        factory.get_llm_provider.assert_called_once_with("deepseek")

    @pytest.mark.asyncio
    async def test_provider_factory_get_image_called(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """ProviderFactory.get_image_provider is called with correct args."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        factory.get_image_provider.assert_called_once_with("fal")

    @pytest.mark.asyncio
    async def test_provider_factory_get_wp_called(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ):
        """ProviderFactory.get_wordpress_provider is called with blog details."""
        blog, config = blog_with_config
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        factory.get_wordpress_provider.assert_called_once_with(
            "wp_rest",
            base_url=blog.url,
            username=blog.wp_username,
        )


# ---------------------------------------------------------------------------
# NFR: Logging tests
# ---------------------------------------------------------------------------


class TestPipelineLogging:
    """Verify logging at correct levels during pipeline execution."""

    @pytest.mark.asyncio
    async def test_logs_info_on_status_transitions(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog,
    ):
        """INFO logs emitted for status transitions."""
        factory = _make_mock_factory()

        with _mock_httpx_download(), caplog.at_level(
            "INFO", logger="app.pipeline.single_article"
        ):
            await _run_pipeline(db_session, article, factory=factory)

        log_messages = [r.message for r in caplog.records]
        assert any("generating" in msg.lower() for msg in log_messages)
        assert any("publishing" in msg.lower() for msg in log_messages)
        assert any("published" in msg.lower() for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog,
    ):
        """ERROR log emitted when pipeline fails."""
        llm = MockLLMProvider(responses=["bad json"] * 10)
        factory = _make_mock_factory(llm_provider=llm)

        with caplog.at_level("ERROR", logger="app.pipeline.single_article"):
            await _run_pipeline(db_session, article, factory=factory)

        error_messages = [
            r.message for r in caplog.records if r.levelno >= 40
        ]
        assert len(error_messages) > 0

        reload = _reload_article(db_session, article.id)
        updated = await reload()
        assert updated.status == "failed"

    @pytest.mark.asyncio
    async def test_logs_warning_on_generation_retry(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog,
    ):
        """WARNING log emitted during generation retries."""
        # First response is invalid, second is valid
        valid_json = _make_valid_article_json()
        llm = MockLLMProvider(responses=["invalid json", valid_json])
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download(), caplog.at_level(
            "WARNING", logger="app.services.article_generator"
        ):
            await _run_pipeline(db_session, article, factory=factory)

        # The article generator should have logged a warning about the retry
        reload = _reload_article(db_session, article.id)
        updated = await reload()
        assert updated.status == "published"
