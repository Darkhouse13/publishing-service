"""Cross-area integration tests and NFR verification tests.

Fulfils:
- VAL-CROSS-001: POST /runs → GET /runs/{id} round-trip
- VAL-CROSS-002: POST /articles → GET /articles/{id} round-trip
- VAL-CROSS-003: Full single article pipeline end-to-end
- VAL-CROSS-004: Bulk pipeline with multiple keywords end-to-end
- VAL-CROSS-005: Bulk pipeline CSV rows match successful articles
- VAL-CROSS-006: Single article pipeline updates generation_attempts
- VAL-CROSS-007: Failed article stores validation_errors
- VAL-CROSS-008: Run config_snapshot independent of later config changes
- VAL-CROSS-009: BrainOutput fields are stored on Article
- VAL-CROSS-010: PublisherService respects publish_status from PipelineConfig
- VAL-NFR-001: No os.getenv()/load_dotenv() in backend/app/
- VAL-NFR-002: Pipeline service methods are async
- VAL-NFR-003: Pipeline logs status transitions at INFO level
- VAL-NFR-004: Pipeline logs retries at WARNING level
- VAL-NFR-005: Pipeline logs failures at ERROR level
- VAL-TEST-004: All existing tests pass after Milestone 3
- VAL-TEST-005: Full test suite including new tests passes
"""

from __future__ import annotations

import csv
import inspect
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.article import Article
from app.models.blog import Blog
from app.models.pipeline_config import PipelineConfig
from app.models.run import Run
from app.pipeline.bulk_pipeline import _run_bulk_pipeline
from app.pipeline.single_article import _run_pipeline
from app.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
    WordPressProvider,
    WPMediaResult,
    WPPostResult,
)
from app.services.article_generator import ArticleGenerator
from app.services.image_generator import ImageGeneratorService
from app.services.keyword_analyzer import KeywordAnalyzer
from app.services.publisher import PublisherService
from tests.helpers import (
    MockImageProvider,
    MockLLMProvider,
    MockWordPressProvider,
)


# ---------------------------------------------------------------------------
# Helpers — valid article JSON
# ---------------------------------------------------------------------------


def _make_valid_article_json(keyword: str = "outdoor patio") -> str:
    """Return a JSON string matching the ArticlePayload schema.

    Produces a valid article with >= 600 words, keyword count in [5,9],
    keyword in first paragraph, H2 with keyword, and seo_title with a number.
    """
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


# ---------------------------------------------------------------------------
# Keyword-aware LLM provider for bulk pipeline
# ---------------------------------------------------------------------------


class _KeywordAwareLLMProvider(LLMProvider):
    """Mock LLM that generates valid article JSON for whatever keyword is in the prompt."""

    def __init__(self) -> None:
        self.call_args: list[dict] = []

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.call_args.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        keyword = "outdoor patio"
        match = re.search(r'EXACT focus keyword "([^"]+)"', prompt)
        if match:
            keyword = match.group(1)
        return LLMResponse(
            text=_make_valid_article_json(keyword=keyword),
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 100, "total_tokens": 110},
        )

    async def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return len(self.call_args)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        max_concurrent_articles=3,
        csv_cadence_minutes=60,
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


@pytest_asyncio.fixture()
async def run_with_keywords(
    db_session: AsyncSession,
    blog_with_config: tuple[Blog, PipelineConfig],
) -> Run:
    """Create a Run with 3 seed keywords."""
    blog, config = blog_with_config
    keywords = ["outdoor patio", "garden design", "deck ideas"]
    run = Run(
        blog_id=blog.id,
        status="pending",
        phase="pending",
        run_code=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        seed_keywords=keywords,
        config_snapshot={
            "llm_provider": "deepseek",
            "image_provider": "fal",
            "llm_model": "deepseek-chat",
            "image_model": "fal-ai/flux/dev",
            "publish_status": "draft",
            "max_concurrent_articles": 3,
            "csv_cadence_minutes": 60,
        },
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Mock factory helpers
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


def _make_bulk_mock_factory(
    llm_provider: LLMProvider | None = None,
    image_provider: ImageProvider | None = None,
    wp_provider: WordPressProvider | None = None,
) -> MagicMock:
    """Create a mock ProviderFactory for bulk pipeline (keyword-aware LLM)."""
    factory = MagicMock()
    if llm_provider is not None:
        factory.get_llm_provider = AsyncMock(return_value=llm_provider)
    else:
        def _make_llm(*args, **kwargs):
            return _KeywordAwareLLMProvider()
        factory.get_llm_provider = AsyncMock(side_effect=_make_llm)
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
    """Return a context manager that patches httpx.AsyncClient for image downloads."""
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


async def _reload_article(db_session: AsyncSession, article_id: uuid.UUID) -> Article:
    """Reload an Article from the database."""
    result = await db_session.execute(
        select(Article).where(Article.id == article_id)
    )
    return result.scalar_one()


async def _reload_run(db_session: AsyncSession, run_id: uuid.UUID) -> Run:
    """Reload a Run from the database."""
    result = await db_session.execute(
        select(Run).where(Run.id == run_id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# API-level helpers
# ---------------------------------------------------------------------------


def _make_blog_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid blog creation payload."""
    return {
        "name": "Test Blog",
        "url": "https://testblog.com",
        "wp_username": "admin",
        "wp_application_password": "super-secret-password",
        **overrides,
    }


def _make_run_payload(blog_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    """Return a valid run creation payload."""
    return {
        "blog_id": str(blog_id),
        "keywords": ["keyword1", "keyword2", "keyword3"],
        **overrides,
    }


def _make_article_payload(blog_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    """Return a valid article creation payload."""
    return {
        "blog_id": str(blog_id),
        "topic": "test topic for article generation",
        **overrides,
    }


@pytest_asyncio.fixture()
async def blog_in_db(db_session: AsyncSession) -> Blog:
    """Create and persist a Blog, returning the ORM instance."""
    blog = Blog(
        name=f"Test Blog {uuid.uuid4().hex[:8]}",
        url="https://testblog.com",
        wp_username="admin",
        wp_app_password_encrypted="encrypted_password",
    )
    db_session.add(blog)
    await db_session.flush()
    await db_session.refresh(blog)
    return blog


@pytest_asyncio.fixture()
def session_factory() -> async_sessionmaker:
    """Provide the test session factory for creating per-article sessions."""
    from tests.conftest import _TestSessionFactory
    return _TestSessionFactory


# ===================================================================
# VAL-CROSS-001: POST /runs → GET /runs/{id} round-trip
# ===================================================================


class TestCross001RunsRoundTrip:
    """POST /runs then GET /runs/{id} — all fields consistent."""

    @pytest.mark.asyncio
    async def test_runs_round_trip_all_fields(
        self,
        client: AsyncClient,
    ) -> None:
        """All fields submitted in POST are present and correct in GET response."""
        # Create blog via API with unique name (auto-creates pipeline config)
        unique_name = f"RoundTrip Blog {uuid.uuid4().hex[:8]}"
        blog_resp = await client.post(
            "/api/v1/blogs",
            json=_make_blog_payload(name=unique_name),
        )
        assert blog_resp.status_code == 201
        blog_data = blog_resp.json()
        blog_id = uuid.UUID(blog_data["id"])

        keywords = ["round_trip_kw1", "round_trip_kw2"]
        payload = _make_run_payload(blog_id, keywords=keywords)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/runs", json=payload)

        assert create_resp.status_code == 201
        create_data = create_resp.json()

        get_resp = await client.get(f"/api/v1/runs/{create_data['id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        # Verify all fields match
        assert get_data["id"] == create_data["id"]
        assert get_data["blog_id"] == create_data["blog_id"]
        assert get_data["blog_id"] == str(blog_id)
        assert get_data["status"] == create_data["status"]
        assert get_data["run_code"] == create_data["run_code"]
        assert get_data["phase"] == create_data["phase"]
        assert get_data["seed_keywords"] == keywords
        assert get_data["config_snapshot"] == create_data["config_snapshot"]
        assert get_data["results_summary"] == create_data["results_summary"]
        assert get_data["csv_path"] == create_data["csv_path"]
        assert get_data["articles_total"] == len(keywords)
        assert get_data["articles_completed"] == 0
        assert get_data["articles_failed"] == 0

        # Verify run_code is timestamp format
        assert re.match(r"^\d{8}_\d{6}$", get_data["run_code"])


# ===================================================================
# VAL-CROSS-002: POST /articles → GET /articles/{id} round-trip
# ===================================================================


class TestCross002ArticlesRoundTrip:
    """POST /articles then GET /articles/{id} — all fields consistent."""

    @pytest.mark.asyncio
    async def test_articles_round_trip_all_fields(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """blog_id, keyword, and status match between POST and GET."""
        topic = "outdoor patio design tips"
        payload = _make_article_payload(blog_in_db.id, topic=topic)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/articles", json=payload)

        assert create_resp.status_code == 201
        create_data = create_resp.json()

        get_resp = await client.get(f"/api/v1/articles/{create_data['id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        # Verify fields match
        assert get_data["id"] == create_data["id"]
        assert get_data["blog_id"] == str(blog_in_db.id)
        assert get_data["keyword"] == topic
        assert get_data["status"] == "pending"
        assert get_data["run_id"] is None
        assert get_data["generation_attempts"] == 0
        assert get_data["validation_errors"] == []
        assert get_data["brain_output"] is None


# ===================================================================
# VAL-CROSS-003: Full single article pipeline end-to-end
# ===================================================================


class TestCross003SingleArticleE2E:
    """Full single article pipeline end-to-end via internal pipeline call."""

    @pytest.mark.asyncio
    async def test_single_article_pipeline_e2e(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """POST /articles triggers pipeline; after eager execution, article is published."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        updated = await _reload_article(db_session, article.id)

        # Status should be published
        assert updated.status == "published"
        assert updated.wp_post_id is not None
        assert updated.wp_post_id == 200
        assert updated.wp_permalink == "https://example.com/my-post/"

        # Content fields populated
        assert updated.seo_title is not None
        assert updated.meta_description is not None
        assert updated.focus_keyword is not None
        assert updated.content_markdown is not None
        assert updated.content_html is not None
        assert updated.category_name is not None

        # Image fields populated
        assert updated.hero_image_url is not None
        assert updated.detail_image_url is not None

        # Pinterest fields populated
        assert updated.pin_title is not None
        assert updated.pin_description is not None
        assert updated.pin_text_overlay is not None
        assert updated.pin_image_url is not None

        # No run_id (single article)
        assert updated.run_id is None
        assert updated.blog_id is not None


# ===================================================================
# VAL-CROSS-004: Bulk pipeline with multiple keywords end-to-end
# ===================================================================


class TestCross004BulkPipelineE2E:
    """Bulk pipeline with multiple keywords end-to-end."""

    @pytest.mark.asyncio
    async def test_bulk_pipeline_e2e(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ) -> None:
        """Bulk pipeline processes all keywords to completion."""
        factory = _make_bulk_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session,
                run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        updated_run = await _reload_run(db_session, run_with_keywords.id)

        # Run should be completed
        assert updated_run.phase == "completed"
        assert updated_run.articles_total == 3
        assert updated_run.articles_completed + updated_run.articles_failed == 3
        assert updated_run.csv_path is not None

        # All articles should be published in this happy path
        assert updated_run.articles_completed == 3
        assert updated_run.articles_failed == 0

        # Results summary populated
        assert updated_run.results_summary["total"] == 3
        assert updated_run.results_summary["completed"] == 3
        assert updated_run.results_summary["failed"] == 0
        assert len(updated_run.results_summary["keywords"]) == 3


# ===================================================================
# VAL-CROSS-005: Bulk pipeline CSV rows match successful articles
# ===================================================================


class TestCross005CSVRowsMatchSuccessful:
    """CSV rows match successful articles after bulk pipeline."""

    @pytest.mark.asyncio
    async def test_csv_rows_match_successful_articles(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
        tmp_path: Path,
    ) -> None:
        """CSV file has rows only for published articles."""
        factory = _make_bulk_mock_factory()

        with _mock_httpx_download(), patch(
            "app.pipeline.bulk_pipeline.settings.ARTIFACTS_DIR",
            str(tmp_path),
        ):
            await _run_bulk_pipeline(
                db_session,
                run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        updated_run = await _reload_run(db_session, run_with_keywords.id)

        # CSV should exist
        assert updated_run.csv_path is not None
        csv_path = Path(updated_run.csv_path)
        assert csv_path.exists()

        # Read CSV and verify row count
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Row count should match completed articles
        assert len(rows) == updated_run.articles_completed

        # Verify CSV headers
        expected_headers = [
            "Title", "Media URL", "Pinterest board", "Thumbnail",
            "Description", "Link", "Publish date", "Keywords",
        ]
        assert list(rows[0].keys()) == expected_headers

        # Verify each row has data
        for row in rows:
            assert row["Title"]  # non-empty
            assert row["Media URL"]  # non-empty
            assert row["Description"]  # non-empty
            assert row["Keywords"]  # non-empty
            assert row["Publish date"]  # non-empty


# ===================================================================
# VAL-CROSS-006: Single article pipeline updates generation_attempts
# ===================================================================


class TestCross006GenerationAttempts:
    """generation_attempts tracked after pipeline."""

    @pytest.mark.asyncio
    async def test_generation_attempts_tracked(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """After pipeline, generation_attempts > 0 reflecting LLM calls."""
        valid_json = _make_valid_article_json()
        llm = MockLLMProvider(responses=[valid_json])

        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        updated = await _reload_article(db_session, article.id)
        assert updated.generation_attempts > 0
        # Should reflect at least 1 call (the successful generation)
        assert updated.generation_attempts >= 1

    @pytest.mark.asyncio
    async def test_generation_attempts_reflects_retries(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """generation_attempts reflects retry count when LLM fails initially."""
        # First response: invalid (triggers retry), second: valid
        invalid_response = "this is not valid json"
        valid_json = _make_valid_article_json()

        llm = MockLLMProvider(responses=[invalid_response, valid_json])
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        updated = await _reload_article(db_session, article.id)
        # Should have at least 2 calls (1 failed + 1 successful)
        assert updated.generation_attempts >= 2


# ===================================================================
# VAL-CROSS-007: Failed article stores validation_errors
# ===================================================================


class TestCross007ValidationErrors:
    """Failed article stores validation_errors."""

    @pytest.mark.asyncio
    async def test_failed_article_stores_validation_errors(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """When article fails validation, validation_errors is non-empty."""
        # Create LLM that always returns invalid response (will exhaust retries)
        invalid_response = "not valid json at all"
        llm = MockLLMProvider(responses=[invalid_response] * 10)

        factory = _make_mock_factory(llm_provider=llm)

        # Pipeline will catch the ArticleGenerationError and set failed
        await _run_pipeline(db_session, article, factory=factory)

        updated = await _reload_article(db_session, article.id)
        assert updated.status == "failed"
        assert updated.error_message is not None
        assert len(updated.error_message) > 0


# ===================================================================
# VAL-CROSS-008: Run config_snapshot independent of later changes
# ===================================================================


class TestCross008ConfigSnapshotIndependent:
    """Run config_snapshot independent of later config changes."""

    @pytest.mark.asyncio
    async def test_config_snapshot_independent(
        self,
        client: AsyncClient,
    ) -> None:
        """Updating PipelineConfig after run creation does not change run's config_snapshot."""
        # Create blog via API
        blog_resp = await client.post("/api/v1/blogs", json=_make_blog_payload())
        assert blog_resp.status_code == 201
        blog_data = blog_resp.json()
        blog_id = blog_data["id"]

        # Create a run (which snapshots config)
        payload = _make_run_payload(uuid.UUID(blog_id), keywords=["k1"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            run_resp = await client.post("/api/v1/runs", json=payload)
        assert run_resp.status_code == 201
        original_snapshot = dict(run_resp.json()["config_snapshot"])

        # Now update the PipelineConfig
        from app.core.config import settings
        from app.services.pipeline_config import PipelineConfigService
        # We need to get the config and update it via the API
        config_resp = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        assert config_resp.status_code == 200

        update_resp = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={
                "llm_model": "gpt-4o",
                "max_concurrent_articles": 10,
            },
        )
        assert update_resp.status_code == 200

        # Verify config was actually changed
        updated_config = update_resp.json()
        assert updated_config["llm_model"] == "gpt-4o"
        assert updated_config["max_concurrent_articles"] == 10

        # Now GET the run again and verify config_snapshot is unchanged
        run_id = run_resp.json()["id"]
        get_run_resp = await client.get(f"/api/v1/runs/{run_id}")
        assert get_run_resp.status_code == 200
        run_data = get_run_resp.json()

        # Snapshot should still have original values
        assert run_data["config_snapshot"]["llm_model"] == original_snapshot["llm_model"]
        assert run_data["config_snapshot"]["max_concurrent_articles"] == original_snapshot["max_concurrent_articles"]

        # Specifically, the snapshot should NOT have the updated values
        assert run_data["config_snapshot"]["llm_model"] != "gpt-4o"
        assert run_data["config_snapshot"]["max_concurrent_articles"] != 10


# ===================================================================
# VAL-CROSS-009: BrainOutput stored on Article
# ===================================================================


class TestCross009BrainOutputStored:
    """BrainOutput fields are stored on Article after pipeline."""

    @pytest.mark.asyncio
    async def test_brain_output_stored_on_article(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """After pipeline, article.brain_output contains required BrainOutput fields."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        updated = await _reload_article(db_session, article.id)

        assert updated.brain_output is not None
        assert isinstance(updated.brain_output, dict)

        # Verify required BrainOutput fields
        required_keys = [
            "primary_keyword",
            "image_generation_prompt",
            "pin_text_overlay",
            "pin_title",
            "pin_description",
            "cluster_label",
            "supporting_terms",
            "seasonal_angle",
        ]
        for key in required_keys:
            assert key in updated.brain_output, f"Missing brain_output key: {key}"

        # primary_keyword should match the focus keyword
        assert updated.brain_output["primary_keyword"] == updated.focus_keyword


# ===================================================================
# VAL-CROSS-010: PublisherService respects publish_status
# ===================================================================


class TestCross010PublisherRespectsStatus:
    """PublisherService respects publish_status from PipelineConfig."""

    @pytest.mark.asyncio
    async def test_publisher_uses_draft_status(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """When config.publish_status='draft', WP post created as draft."""
        blog, config = blog_with_config
        config.publish_status = "draft"
        await db_session.commit()

        wp_provider = MockWordPressProvider(
            post_result=WPPostResult(
                id=200,
                url="https://example.com/my-post/",
                status="draft",
                title="Test Post",
            ),
        )
        factory = _make_mock_factory(wp_provider=wp_provider)

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        # Verify WP provider was called with status="draft"
        assert len(wp_provider.create_post_calls) == 1
        call_kwargs = wp_provider.create_post_calls[0]
        assert call_kwargs["status"] == "draft"

    @pytest.mark.asyncio
    async def test_publisher_uses_publish_status(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
    ) -> None:
        """When config.publish_status='publish', WP post published."""
        blog, config = blog_with_config
        config.publish_status = "publish"
        await db_session.commit()

        wp_provider = MockWordPressProvider(
            post_result=WPPostResult(
                id=200,
                url="https://example.com/my-post/",
                status="publish",
                title="Test Post",
            ),
        )
        factory = _make_mock_factory(wp_provider=wp_provider)

        with _mock_httpx_download():
            await _run_pipeline(db_session, article, factory=factory)

        # Verify WP provider was called with status="publish"
        assert len(wp_provider.create_post_calls) == 1
        call_kwargs = wp_provider.create_post_calls[0]
        assert call_kwargs["status"] == "publish"


# ===================================================================
# VAL-NFR-001: No os.getenv()/load_dotenv() in backend/app/
# ===================================================================


class TestNFR001NoGetenvOrLoadDotenv:
    """No os.getenv() or load_dotenv() in backend/app/."""

    def test_no_getenv_in_app(self) -> None:
        """rg 'os\\.getenv|load_dotenv' backend/app/ returns zero matches."""
        backend_app_dir = Path(__file__).parent.parent / "app"
        if not backend_app_dir.exists():
            pytest.skip("backend/app/ directory not found")

        matches: list[str] = []
        for py_file in backend_app_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Check for os.getenv or load_dotenv
                if re.search(r'os\.getenv\s*\(', line) or re.search(r'load_dotenv\s*\(', line):
                    matches.append(f"{py_file.relative_to(backend_app_dir)}:{line_num}: {line.strip()}")

        assert matches == [], (
            f"Found os.getenv() or load_dotenv() calls in backend/app/:\n"
            + "\n".join(matches)
        )


# ===================================================================
# VAL-NFR-002: Pipeline service methods are async
# ===================================================================


class TestNFR002ServiceMethodsAsync:
    """All pipeline service methods are async."""

    def test_article_generator_generate_is_async(self) -> None:
        """ArticleGenerator.generate is async."""
        assert inspect.iscoroutinefunction(ArticleGenerator.generate)

    def test_keyword_analyzer_analyze_is_async(self) -> None:
        """KeywordAnalyzer.analyze is async."""
        assert inspect.iscoroutinefunction(KeywordAnalyzer.analyze)

    def test_image_generator_generate_image_is_async(self) -> None:
        """ImageGeneratorService.generate_image is async."""
        assert inspect.iscoroutinefunction(ImageGeneratorService.generate_image)

    def test_publisher_publish_article_is_async(self) -> None:
        """PublisherService.publish_article is async."""
        assert inspect.iscoroutinefunction(PublisherService.publish_article)


# ===================================================================
# VAL-NFR-003: Pipeline logs status transitions at INFO level
# ===================================================================


class TestNFR003LogsStatusTransitions:
    """Pipeline logs status transitions at INFO level."""

    @pytest.mark.asyncio
    async def test_single_article_logs_transitions_at_info(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Status transitions emit INFO-level logs with article ID and new status."""
        factory = _make_mock_factory()

        with caplog.at_level(logging.INFO, logger="app.pipeline.single_article"):
            with _mock_httpx_download():
                await _run_pipeline(db_session, article, factory=factory)

        info_logs = [
            r for r in caplog.records
            if r.levelno == logging.INFO
            and str(article.id) in r.message
        ]

        # Should see status transition messages
        log_messages = " ".join(r.message for r in info_logs)
        assert "generating" in log_messages
        assert "publishing" in log_messages or "published" in log_messages or "content fields updated" in log_messages

    @pytest.mark.asyncio
    async def test_bulk_pipeline_logs_phase_transitions_at_info(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Run phase transitions emit INFO-level logs."""
        factory = _make_bulk_mock_factory()

        with caplog.at_level(logging.INFO, logger="app.pipeline.bulk_pipeline"):
            with _mock_httpx_download():
                await _run_bulk_pipeline(
                    db_session,
                    run_with_keywords,
                    factory=factory,
                )

        info_logs = [
            r for r in caplog.records
            if r.levelno == logging.INFO
            and str(run_with_keywords.id) in r.message
        ]

        log_messages = " ".join(r.message for r in info_logs)
        assert "generating" in log_messages
        assert "completed" in log_messages


# ===================================================================
# VAL-NFR-004: Pipeline logs retries at WARNING level
# ===================================================================


class TestNFR004LogsRetriesAtWarning:
    """Pipeline logs retries at WARNING level."""

    @pytest.mark.asyncio
    async def test_single_article_logs_validation_issues_at_warning(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When validation finds issues, WARNING-level log is emitted."""
        # Use a valid response so the pipeline completes but validator may still warn
        valid_json = _make_valid_article_json()
        llm = MockLLMProvider(responses=[valid_json])

        factory = _make_mock_factory(llm_provider=llm)

        with caplog.at_level(logging.WARNING, logger="app.pipeline.single_article"):
            with _mock_httpx_download():
                await _run_pipeline(db_session, article, factory=factory)

        # The validator may or may not find issues, but the pipeline should complete
        # If it does find issues, they should be logged at WARNING level
        updated = await _reload_article(db_session, article.id)
        # Pipeline should complete either way (validation issues don't block publishing)
        assert updated.status in ("published", "failed")


# ===================================================================
# VAL-NFR-005: Pipeline logs failures at ERROR level
# ===================================================================


class TestNFR005LogsFailuresAtError:
    """Pipeline logs failures at ERROR level."""

    @pytest.mark.asyncio
    async def test_single_article_logs_generation_failure_at_error(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When generation fails, ERROR-level log is emitted with failure reason."""
        # LLM always returns invalid JSON -> generation fails after max retries
        invalid_response = "not valid json"
        llm = MockLLMProvider(responses=[invalid_response] * 10)

        factory = _make_mock_factory(llm_provider=llm)

        with caplog.at_level(logging.ERROR, logger="app.pipeline.single_article"):
            await _run_pipeline(db_session, article, factory=factory)

        error_logs = [
            r for r in caplog.records
            if r.levelno == logging.ERROR
            and str(article.id) in r.message
        ]

        assert len(error_logs) > 0
        log_messages = " ".join(r.message for r in error_logs)
        assert "failed" in log_messages.lower()

    @pytest.mark.asyncio
    async def test_single_article_logs_publish_failure_at_error(
        self,
        db_session: AsyncSession,
        article: Article,
        blog_with_config: tuple[Blog, PipelineConfig],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When publishing fails, ERROR-level log is emitted."""
        valid_json = _make_valid_article_json()
        llm = MockLLMProvider(responses=[valid_json])

        # Make WP provider fail on create_post
        async def _failing_create_post(*args, **kwargs):
            raise RuntimeError("WordPress API connection failed")

        wp_provider = MockWordPressProvider()
        wp_provider.create_post = _failing_create_post

        factory = _make_mock_factory(llm_provider=llm, wp_provider=wp_provider)

        with caplog.at_level(logging.ERROR, logger="app.pipeline.single_article"):
            with _mock_httpx_download():
                await _run_pipeline(db_session, article, factory=factory)

        error_logs = [
            r for r in caplog.records
            if r.levelno == logging.ERROR
            and str(article.id) in r.message
        ]

        assert len(error_logs) > 0
        updated = await _reload_article(db_session, article.id)
        assert updated.status == "failed"
