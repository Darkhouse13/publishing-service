"""Integration tests for the bulk pipeline.

Tests cover:
- VAL-BULK-001: Creates Article for each keyword
- VAL-BULK-002: Concurrent processing with asyncio.Semaphore
- VAL-BULK-003: One failure doesn't block others
- VAL-BULK-004: Run phase transitions: pending → generating → publishing → completed
- VAL-BULK-005: Final counts correct
- VAL-BULK-006: Results_summary populated
- VAL-BULK-007: CSV generated for successful articles
- VAL-BULK-008: Handles zero keywords gracefully
"""

from __future__ import annotations

import csv
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.article import Article
from app.models.blog import Blog
from app.models.pipeline_config import PipelineConfig
from app.models.run import Run
from app.pipeline.bulk_pipeline import _run_bulk_pipeline
from app.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
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
# Helpers
# ---------------------------------------------------------------------------


class _KeywordAwareLLMProvider(LLMProvider):
    """A mock LLM that generates valid article JSON for whatever keyword is in the prompt.

    Inspects the prompt to extract the keyword and produces a response
    with that keyword embedded throughout the content, ensuring all
    hard validations pass (word count, keyword count, first paragraph, etc.).
    """

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

        # Try to extract the keyword from the prompt
        # The prompt contains: Use the EXACT focus keyword "keyword" between
        import re
        keyword = "outdoor patio"  # default
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


def _make_mock_factory(
    llm_provider: LLMProvider | None = None,
    image_provider: ImageProvider | None = None,
    wp_provider: WordPressProvider | None = None,
    num_articles: int = 3,
) -> MagicMock:
    """Create a mock ProviderFactory that returns the given providers.

    By default, each call to ``get_llm_provider`` returns a fresh
    MockLLMProvider that generates responses with the keyword from
    the prompt text, ensuring validation passes for any keyword.
    """
    factory = MagicMock()
    if llm_provider is not None:
        factory.get_llm_provider = AsyncMock(return_value=llm_provider)
    else:
        # Return a new MockLLMProvider each time (one per article)
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
    """Return a context manager that patches httpx.AsyncClient in image_generator."""
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


async def _reload_run(db_session: AsyncSession, run_id: uuid.UUID) -> Run:
    """Reload a Run from the database."""
    result = await db_session.execute(
        select(Run).where(Run.id == run_id)
    )
    return result.scalar_one()


async def _reload_article(db_session: AsyncSession, article_id: uuid.UUID) -> Article:
    """Reload an Article from the database."""
    result = await db_session.execute(
        select(Article).where(Article.id == article_id)
    )
    return result.scalar_one()


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
        max_concurrent_articles=2,
        csv_cadence_minutes=60,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    return blog, config


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
            "max_concurrent_articles": 2,
            "csv_cadence_minutes": 60,
        },
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest_asyncio.fixture()
async def empty_run(
    db_session: AsyncSession,
    blog_with_config: tuple[Blog, PipelineConfig],
) -> Run:
    """Create a Run with zero seed keywords."""
    blog, config = blog_with_config
    run = Run(
        blog_id=blog.id,
        status="pending",
        phase="pending",
        run_code=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        seed_keywords=[],
        config_snapshot={
            "llm_provider": "deepseek",
            "image_provider": "fal",
        },
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest_asyncio.fixture()
def session_factory() -> async_sessionmaker:
    """Provide the test session factory for creating per-article sessions."""
    from tests.conftest import _TestSessionFactory
    return _TestSessionFactory


# ---------------------------------------------------------------------------
# VAL-BULK-001: Creates Article for each keyword
# ---------------------------------------------------------------------------


class TestArticleCreation:
    """Verify that the bulk pipeline creates Article records for each keyword."""

    @pytest.mark.asyncio
    async def test_creates_article_for_each_keyword(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Running bulk pipeline with 3 keywords creates exactly 3 Article records."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        # Load articles for this run
        result = await db_session.execute(
            select(Article).where(Article.run_id == run.id)
        )
        articles = list(result.scalars().all())

        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_articles_have_correct_keywords(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Each article's keyword matches one of the seed_keywords."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        result = await db_session.execute(
            select(Article).where(Article.run_id == run_with_keywords.id)
        )
        articles = list(result.scalars().all())

        article_keywords = {a.keyword for a in articles}
        expected_keywords = {"outdoor patio", "garden design", "deck ideas"}
        assert article_keywords == expected_keywords

    @pytest.mark.asyncio
    async def test_articles_have_correct_blog_id(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Each article's blog_id matches the run's blog_id."""
        blog, _config = blog_with_config
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        result = await db_session.execute(
            select(Article).where(Article.run_id == run_with_keywords.id)
        )
        articles = list(result.scalars().all())

        for article in articles:
            assert article.blog_id == blog.id


# ---------------------------------------------------------------------------
# VAL-BULK-002: Concurrent processing with asyncio.Semaphore
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Verify concurrent processing with asyncio.Semaphore."""

    @pytest.mark.asyncio
    async def test_max_concurrent_respected(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """At no point do more than max_concurrent_articles tasks run simultaneously."""
        blog, config = blog_with_config
        max_concurrent = config.max_concurrent_articles  # 2

        import asyncio

        active_count = 0
        max_active_count = 0
        lock = asyncio.Lock()

        # Create a mock image provider that tracks concurrency
        original_generate = MockImageProvider(
            result=ImageResult(
                url="https://example.com/generated_image.jpg",
                alt_text="A test image",
                width=1024,
                height=1024,
            )
        )
        original_generate_method = original_generate.generate

        async def tracking_generate(*args, **kwargs):
            nonlocal active_count, max_active_count
            async with lock:
                active_count += 1
                if active_count > max_active_count:
                    max_active_count = active_count
            # Simulate some work to increase chance of concurrent execution
            await asyncio.sleep(0.05)
            result = await original_generate_method(*args, **kwargs)
            async with lock:
                active_count -= 1
            return result

        original_generate.generate = tracking_generate

        factory = _make_mock_factory(image_provider=original_generate)

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        # Max concurrent should not exceed config.max_concurrent_articles
        assert max_active_count <= max_concurrent


# ---------------------------------------------------------------------------
# VAL-BULK-003: One failure doesn't block others
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Verify that one failing article doesn't block others."""

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_block_others(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """When one keyword fails, the remaining keywords continue processing."""
        # Make LLM fail for the second keyword by running out of responses
        # First keyword gets valid JSON, second gets invalid, third gets valid
        responses = [
            _make_valid_article_json("outdoor patio"),
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
        ]
        llm = MockLLMProvider(responses=responses)
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        # At least one should complete and at least one should fail
        result = await db_session.execute(
            select(Article).where(Article.run_id == run.id)
        )
        articles = list(result.scalars().all())

        statuses = {a.status for a in articles}
        assert "failed" in statuses
        assert "published" in statuses

    @pytest.mark.asyncio
    async def test_failed_article_has_error_message(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Failed articles have error_message populated."""
        responses = [
            _make_valid_article_json("outdoor patio"),
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
        ]
        llm = MockLLMProvider(responses=responses)
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        result = await db_session.execute(
            select(Article).where(
                Article.run_id == run_with_keywords.id,
                Article.status == "failed",
            )
        )
        failed_articles = list(result.scalars().all())

        assert len(failed_articles) >= 1
        for article in failed_articles:
            assert article.error_message is not None
            assert len(article.error_message) > 0


# ---------------------------------------------------------------------------
# VAL-BULK-004: Run phase transitions
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    """Verify Run phase transitions: pending → generating → publishing → completed."""

    @pytest.mark.asyncio
    async def test_run_phase_completed_after_pipeline(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Run phase is 'completed' after pipeline finishes."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)
        assert run.phase == "completed"

    @pytest.mark.asyncio
    async def test_phase_transitions_observed(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """All phase transitions are observed during execution."""
        factory = _make_mock_factory()
        phases_seen = []

        original_commit = db_session.commit

        async def tracking_commit():
            phases_seen.append(run_with_keywords.phase)
            await original_commit()

        db_session.commit = tracking_commit

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        assert "generating" in phases_seen
        assert "publishing" in phases_seen
        assert "completed" in phases_seen


# ---------------------------------------------------------------------------
# VAL-BULK-005: Final counts correct
# ---------------------------------------------------------------------------


class TestFinalCounts:
    """Verify final counts: articles_total, articles_completed, articles_failed."""

    @pytest.mark.asyncio
    async def test_all_succeed_counts(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """When all articles succeed, articles_completed equals total."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert run.articles_total == 3
        assert run.articles_completed == 3
        assert run.articles_failed == 0
        assert run.articles_completed + run.articles_failed == run.articles_total

    @pytest.mark.asyncio
    async def test_mixed_success_failure_counts(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """When some articles fail, counts reflect mixed results."""
        responses = [
            _make_valid_article_json("outdoor patio"),
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
            _make_valid_article_json("deck ideas"),
        ]
        llm = MockLLMProvider(responses=responses)
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert run.articles_total == 3
        assert run.articles_completed + run.articles_failed == 3
        assert run.articles_failed >= 1
        assert run.articles_completed >= 1


# ---------------------------------------------------------------------------
# VAL-BULK-006: Results_summary populated
# ---------------------------------------------------------------------------


class TestResultsSummary:
    """Verify results_summary is populated with per-keyword results."""

    @pytest.mark.asyncio
    async def test_results_summary_has_total(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """results_summary contains 'total' key matching keyword count."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert "total" in run.results_summary
        assert run.results_summary["total"] == 3

    @pytest.mark.asyncio
    async def test_results_summary_has_completed_and_failed(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """results_summary contains completed and failed counts."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert "completed" in run.results_summary
        assert "failed" in run.results_summary
        assert run.results_summary["completed"] == 3
        assert run.results_summary["failed"] == 0

    @pytest.mark.asyncio
    async def test_results_summary_has_per_keyword_results(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """results_summary contains per-keyword results."""
        factory = _make_mock_factory()

        with _mock_httpx_download():
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        # Should have per-keyword entries
        assert "keywords" in run.results_summary
        keywords_data = run.results_summary["keywords"]
        assert isinstance(keywords_data, list)
        assert len(keywords_data) == 3

        for kw_entry in keywords_data:
            assert "keyword" in kw_entry
            assert "status" in kw_entry


# ---------------------------------------------------------------------------
# VAL-BULK-007: CSV generated for successful articles
# ---------------------------------------------------------------------------


class TestCSVGeneration:
    """Verify CSV is generated for successful articles."""

    @pytest.mark.asyncio
    async def test_csv_path_set_after_completion(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
        tmp_path: Path,
    ):
        """After pipeline, csv_path is set on the Run."""
        factory = _make_mock_factory()

        # Patch ARTIFACTS_DIR to use tmp_path
        with _mock_httpx_download(), patch(
            "app.pipeline.bulk_pipeline.settings.ARTIFACTS_DIR",
            str(tmp_path),
        ):
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert run.csv_path is not None

    @pytest.mark.asyncio
    async def test_csv_contains_only_successful_articles(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
        tmp_path: Path,
    ):
        """CSV row count equals articles_completed."""
        factory = _make_mock_factory()

        with _mock_httpx_download(), patch(
            "app.pipeline.bulk_pipeline.settings.ARTIFACTS_DIR",
            str(tmp_path),
        ):
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        run = await _reload_run(db_session, run_with_keywords.id)

        assert run.csv_path is not None
        csv_path = Path(run.csv_path)
        assert csv_path.exists()

        with csv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        # Should have as many rows as completed articles
        assert len(rows) == run.articles_completed


# ---------------------------------------------------------------------------
# VAL-BULK-008: Handles zero keywords gracefully
# ---------------------------------------------------------------------------


class TestZeroKeywords:
    """Verify bulk pipeline handles empty keyword list gracefully."""

    @pytest.mark.asyncio
    async def test_zero_keywords_completes_immediately(
        self,
        db_session: AsyncSession,
        empty_run: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Empty keywords list results in immediate completion."""
        factory = _make_mock_factory()

        await _run_bulk_pipeline(
            db_session, empty_run,
            factory=factory,
            session_factory=session_factory,
        )

        run = await _reload_run(db_session, empty_run.id)

        assert run.phase == "completed"

    @pytest.mark.asyncio
    async def test_zero_keywords_all_counts_zero(
        self,
        db_session: AsyncSession,
        empty_run: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Empty keywords list results in all counts being 0."""
        factory = _make_mock_factory()

        await _run_bulk_pipeline(
            db_session, empty_run,
            factory=factory,
            session_factory=session_factory,
        )

        run = await _reload_run(db_session, empty_run.id)

        assert run.articles_total == 0
        assert run.articles_completed == 0
        assert run.articles_failed == 0

    @pytest.mark.asyncio
    async def test_zero_keywords_no_csv(
        self,
        db_session: AsyncSession,
        empty_run: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Empty keywords list results in no CSV generated."""
        factory = _make_mock_factory()

        await _run_bulk_pipeline(
            db_session, empty_run,
            factory=factory,
            session_factory=session_factory,
        )

        run = await _reload_run(db_session, empty_run.id)

        assert run.csv_path is None

    @pytest.mark.asyncio
    async def test_zero_keywords_no_articles_created(
        self,
        db_session: AsyncSession,
        empty_run: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
    ):
        """Empty keywords list creates no Article records."""
        factory = _make_mock_factory()

        await _run_bulk_pipeline(
            db_session, empty_run,
            factory=factory,
            session_factory=session_factory,
        )

        result = await db_session.execute(
            select(Article).where(Article.run_id == empty_run.id)
        )
        articles = list(result.scalars().all())

        assert len(articles) == 0


# ---------------------------------------------------------------------------
# NFR: Logging tests
# ---------------------------------------------------------------------------


class TestBulkPipelineLogging:
    """Verify logging at correct levels during bulk pipeline execution."""

    @pytest.mark.asyncio
    async def test_logs_info_on_phase_transitions(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
        caplog,
    ):
        """INFO logs emitted for phase transitions."""
        factory = _make_mock_factory()

        with _mock_httpx_download(), caplog.at_level(
            "INFO", logger="app.pipeline.bulk_pipeline"
        ):
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        log_messages = [r.message for r in caplog.records]
        assert any("generating" in msg.lower() for msg in log_messages)
        assert any("publishing" in msg.lower() for msg in log_messages)
        assert any("completed" in msg.lower() for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_error_on_article_failure(
        self,
        db_session: AsyncSession,
        run_with_keywords: Run,
        blog_with_config: tuple[Blog, PipelineConfig],
        session_factory: async_sessionmaker,
        caplog,
    ):
        """ERROR log emitted when an article fails."""
        responses = [
            _make_valid_article_json("outdoor patio"),
            _make_valid_article_json("outdoor patio"),
            _make_valid_article_json("outdoor patio"),
            _make_valid_article_json("outdoor patio"),
            _make_valid_article_json("outdoor patio"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            _make_valid_article_json("garden design"),
            "invalid json",  # deck ideas fails
            "invalid json",
            "invalid json",
            "invalid json",
            "invalid json",
        ]
        llm = MockLLMProvider(responses=responses)
        factory = _make_mock_factory(llm_provider=llm)

        with _mock_httpx_download(), caplog.at_level(
            "ERROR", logger="app.pipeline.bulk_pipeline"
        ):
            await _run_bulk_pipeline(
                db_session, run_with_keywords,
                factory=factory,
                session_factory=session_factory,
            )

        error_messages = [
            r.message for r in caplog.records if r.levelno >= 40
        ]
        assert len(error_messages) > 0
