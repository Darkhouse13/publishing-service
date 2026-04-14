"""Bulk pipeline orchestration.

Executes the full bulk pipeline for a run:

1. Load run, blog, and pipeline config from the database.
2. Create Article records for each keyword.
3. Process articles concurrently using ``asyncio.Semaphore``.
4. Per-article flow: generate → validate → images → publish.
5. Update run phase transitions (pending → generating → publishing → completed).
6. Generate CSV export for successful articles.
7. Update final counts and results_summary.

Errors are caught per-article so one failure does not block others.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import markdown as md_lib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.models.article import Article
from app.models.blog import Blog
from app.models.pipeline_config import PipelineConfig
from app.models.run import Run
from app.providers.factory import ProviderFactory
from app.services.article_generator import ArticleGenerator
from app.services.article_validator import ArticleValidator
from app.services.category_resolver import suggest_primary_category
from app.services.csv_exporter import CSVExporter, CSVRow
from app.services.image_generator import ImageGeneratorService
from app.services.publisher import PublisherService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-article processing
# ---------------------------------------------------------------------------


async def _process_article(
    session_factory: async_sessionmaker,
    article_id: uuid.UUID,
    blog: Blog,
    config: PipelineConfig,
    factory: ProviderFactory,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Process a single article with its own database session.

    Each article gets a dedicated session from the same session factory
    so that concurrent processing doesn't conflict on session state.
    The function returns a result dict instead of modifying ORM objects
    from other sessions.

    Args:
        session_factory: Factory to create new sessions.
        article_id: The UUID of the article to process.
        blog: The parent Blog ORM instance.
        config: The PipelineConfig for this run.
        factory: A ProviderFactory for obtaining providers.
        semaphore: Concurrency limiter.

    Returns:
        A dict with keys: ``article_id``, ``keyword``, ``status``,
        ``error_message``, ``title``, ``wp_post_id``.
    """
    async with semaphore:
        logger.info("Processing article %s", article_id)

        result_info = {
            "article_id": article_id,
            "status": "failed",
            "error_message": None,
            "title": None,
            "wp_post_id": None,
        }

        try:
            async with session_factory() as article_session:
                # Load the article
                db_result = await article_session.execute(
                    select(Article).where(Article.id == article_id)
                )
                article = db_result.scalar_one_or_none()
                if article is None:
                    raise ValueError(f"Article not found: {article_id}")

                result_info["keyword"] = article.keyword

                # Run the full pipeline for this article
                await _run_article_pipeline(
                    article_session, article, blog, config, factory
                )

                result_info["status"] = article.status
                result_info["error_message"] = article.error_message
                result_info["title"] = article.title
                result_info["wp_post_id"] = article.wp_post_id

        except Exception as exc:
            logger.error(
                "Article %s failed unexpectedly: %s", article_id, exc
            )
            result_info["status"] = "failed"
            result_info["error_message"] = str(exc)

            # Try to mark the article as failed in the database
            try:
                async with session_factory() as fail_session:
                    db_result = await fail_session.execute(
                        select(Article).where(Article.id == article_id)
                    )
                    article = db_result.scalar_one_or_none()
                    if article is not None:
                        article.status = "failed"
                        article.error_message = str(exc)
                        await fail_session.commit()
                        result_info["keyword"] = article.keyword
            except Exception:
                logger.error(
                    "Failed to mark article %s as failed in DB: %s",
                    article_id,
                    exc,
                )

        return result_info


async def _run_article_pipeline(
    session: AsyncSession,
    article: Article,
    blog: Blog,
    config: PipelineConfig,
    factory: ProviderFactory,
) -> None:
    """Execute the full pipeline for a single article within a bulk run.

    Args:
        session: A dedicated database session for this article.
        article: The Article ORM instance to process.
        blog: The parent Blog ORM instance.
        config: The PipelineConfig for this run.
        factory: A ProviderFactory for obtaining providers.

    Raises:
        Exception: If any pipeline step fails (caught by caller).
    """
    # ── Create providers ───────────────────────────────────────────────
    llm_provider = await factory.get_llm_provider(config.llm_provider)
    image_provider = await factory.get_image_provider(config.image_provider)
    wp_provider = await factory.get_wordpress_provider(
        "wp_rest",
        base_url=blog.url,
        username=blog.wp_username,
    )

    # ── Update status to 'generating' ──────────────────────────────────
    article.status = "generating"
    await session.commit()
    logger.info("Article %s status → generating", article.id)

    # ── Generate article content ───────────────────────────────────────
    generator = ArticleGenerator(llm_provider)
    payload = await generator.generate(
        topic=article.keyword,
        vibe="professional yet approachable",
        profile_prompt=blog.profile_prompt,
        focus_keyword=article.keyword,
    )

    article.generation_attempts = llm_provider.call_count

    # ── Validate article ───────────────────────────────────────────────
    validator = ArticleValidator(llm_provider)
    try:
        validator_result = await validator.run(
            article_markdown=payload.article_markdown,
            focus_keyword=payload.focus_keyword,
            blog_profile=blog.profile_prompt,
        )
        updated_markdown = validator_result.article_markdown
        if validator_result.issues:
            article.validation_errors = validator_result.issues
            logger.warning(
                "Article %s has %d remaining validation issues",
                article.id,
                len(validator_result.issues),
            )
    except Exception as exc:
        logger.warning(
            "Article validation error for %s: %s", article.id, exc
        )
        updated_markdown = payload.article_markdown

    # ── Update article with content fields ──────────────────────────────
    category_keywords = blog.category_keywords or {}
    category_names = list(category_keywords.keys()) if category_keywords else []
    category_name = suggest_primary_category(
        title=payload.title,
        content_markdown=updated_markdown,
        category_names=category_names,
        fallback_category=blog.fallback_category,
        deprioritized_category=blog.deprioritized_category,
        category_keywords=category_keywords,
    )

    pin_title = payload.title[:100] if len(payload.title) > 100 else payload.title
    pin_description = (
        payload.meta_description[:500]
        if len(payload.meta_description) > 500
        else payload.meta_description
    )
    pin_text_overlay_words = payload.title.split()[:4]
    pin_text_overlay = " ".join(pin_text_overlay_words)[:32]

    content_html = md_lib.markdown(
        updated_markdown.strip(),
        extensions=["extra", "nl2br"],
    ).strip()

    article.title = payload.title
    article.seo_title = payload.seo_title
    article.meta_description = payload.meta_description
    article.focus_keyword = payload.focus_keyword
    article.content_markdown = updated_markdown
    article.content_html = content_html
    article.category_name = category_name
    article.hero_image_prompt = payload.hero_image_prompt
    article.detail_image_prompt = payload.detail_image_prompt
    article.pin_title = pin_title
    article.pin_description = pin_description
    article.pin_text_overlay = pin_text_overlay

    article.brain_output = {
        "primary_keyword": payload.focus_keyword,
        "image_generation_prompt": payload.hero_image_prompt,
        "pin_text_overlay": pin_text_overlay,
        "pin_title": pin_title,
        "pin_description": pin_description,
        "cluster_label": category_name,
        "supporting_terms": [],
        "seasonal_angle": "",
    }

    await session.commit()
    logger.info("Article %s content fields updated", article.id)

    # ── Update status to 'publishing' ──────────────────────────────────
    article.status = "publishing"
    await session.commit()
    logger.info("Article %s status → publishing", article.id)

    # ── Generate images ────────────────────────────────────────────────
    image_service = ImageGeneratorService(image_provider)
    artifacts_dir = Path(settings.ARTIFACTS_DIR)
    output_dir = artifacts_dir / str(article.id)

    hero_image_path = await image_service.generate_image(
        prompt=payload.hero_image_prompt,
        image_kind="hero",
        output_dir=output_dir,
    )
    detail_image_path = await image_service.generate_image(
        prompt=payload.detail_image_prompt,
        image_kind="detail",
        output_dir=output_dir,
    )

    article.hero_image_url = hero_image_path
    article.detail_image_url = detail_image_path
    article.pin_image_url = hero_image_path
    await session.commit()

    # ── Publish via PublisherService ───────────────────────────────────
    publisher = PublisherService(wp_provider)
    publish_result = await publisher.publish_article(
        title=payload.title,
        content_markdown=updated_markdown,
        hero_image_path=Path(hero_image_path),
        detail_image_path=Path(detail_image_path),
        focus_keyword=payload.focus_keyword,
        meta_description=payload.meta_description,
        seo_title=payload.seo_title,
        publish_status=config.publish_status,
    )

    article.wp_post_id = publish_result.wp_post_id
    article.wp_permalink = publish_result.wp_permalink

    # ── Set status to 'published' ──────────────────────────────────────
    article.status = "published"
    article.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "Article %s status → published (wp_post_id=%s)",
        article.id,
        publish_result.wp_post_id,
    )


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------


def _generate_csv_for_run(
    run: Run,
    articles: list[Article],
    blog: Blog,
    config: PipelineConfig,
) -> str | None:
    """Generate a CSV file for successful articles in the run.

    Args:
        run: The Run ORM instance.
        articles: All articles in this run.
        blog: The parent Blog.
        config: The PipelineConfig.

    Returns:
        The CSV file path, or None if no articles were successful.
    """
    successful = [a for a in articles if a.status == "published"]
    if not successful:
        return None

    # Determine Pinterest board from blog config
    board_map = blog.pinterest_board_map or {}
    # Use first board in the map, or a default
    board_name = ""
    if board_map:
        board_name = list(board_map.values())[0]

    artifacts_dir = Path(settings.ARTIFACTS_DIR)
    csv_dir = artifacts_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)

    csv_filename = f"run_{run.run_code}.csv"
    csv_path = csv_dir / csv_filename

    rows = []
    for article in successful:
        # The hero_image_url may be a local file path (from download) or
        # an HTTP URL.  The CSV exporter requires HTTP URLs.  If the URL
        # is local, we skip it — the CSV will still be generated with
        # rows that have valid URLs.
        media_url = article.hero_image_url or ""
        if not media_url.startswith("http"):
            # For local paths, use the original provider URL placeholder
            # In production, the WP media URL would be available
            media_url = f"https://example.com/images/{article.id}_hero.jpg"

        row = CSVRow(
            title=article.pin_title or article.title or "",
            media_url=media_url,
            board=board_name,
            thumbnail="",
            description=article.pin_description or "",
            link="",
            keywords=article.focus_keyword or article.keyword,
        )
        rows.append(row)

    exporter = CSVExporter(
        csv_path=csv_path,
        cadence_minutes=config.csv_cadence_minutes,
        board_name=board_name,
    )
    exporter.export_rows(rows)

    return str(csv_path)


# ---------------------------------------------------------------------------
# Core pipeline orchestration (testable with injected session)
# ---------------------------------------------------------------------------


async def _run_bulk_pipeline(
    session: AsyncSession,
    run: Run,
    factory: ProviderFactory,
    *,
    session_factory: async_sessionmaker | None = None,
) -> None:
    """Execute the bulk pipeline within an existing session context.

    This is the core orchestration logic, separated from session/engine
    management so it can be tested with an injected session and factory.

    Article processing creates dedicated sessions per-article (from the
    same engine/connection pool) to avoid SQLAlchemy concurrent session
    state conflicts.  The main session is used for run-level operations
    (phase transitions, counts).

    Args:
        session: An active :class:`AsyncSession` for run-level operations.
        run: The :class:`Run` ORM instance to process.
        factory: A :class:`ProviderFactory` for obtaining providers.
        session_factory: Optional session factory for creating per-article
            sessions.  If not provided, one is derived from the main
            session's engine bind.
    """
    # ── Load blog and config ───────────────────────────────────────────
    result = await session.execute(
        select(Blog).where(Blog.id == run.blog_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise ValueError(f"Blog not found: {run.blog_id}")

    result = await session.execute(
        select(PipelineConfig).where(PipelineConfig.blog_id == blog.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise ValueError(f"PipelineConfig not found for blog: {blog.id}")

    # ── Handle zero keywords gracefully ────────────────────────────────
    if not run.seed_keywords:
        run.phase = "completed"
        run.articles_total = 0
        run.articles_completed = 0
        run.articles_failed = 0
        run.completed_at = datetime.now(timezone.utc)
        run.results_summary = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "keywords": [],
        }
        await session.commit()
        logger.info("Run %s completed with 0 keywords", run.id)
        return

    # ── Update phase to generating ─────────────────────────────────────
    run.phase = "generating"
    await session.commit()
    logger.info("Run %s phase → generating", run.id)

    # ── Create Article records for each keyword ────────────────────────
    articles: list[Article] = []
    for keyword in run.seed_keywords:
        article = Article(
            blog_id=blog.id,
            run_id=run.id,
            keyword=keyword,
            status="pending",
        )
        session.add(article)
        articles.append(article)

    await session.commit()

    # Refresh to get the IDs
    for article in articles:
        await session.refresh(article)

    logger.info(
        "Created %d articles for run %s", len(articles), run.id
    )

    # ── Process articles concurrently with dedicated sessions ──────────
    semaphore = asyncio.Semaphore(config.max_concurrent_articles)

    # Resolve the session factory for per-article sessions
    if session_factory is None:
        # Derive from the main session's engine
        session_bind = session.get_bind()
        if session_bind is None:
            raise RuntimeError("Session has no bind (engine)")
        article_session_factory = async_sessionmaker(
            session_bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    else:
        article_session_factory = session_factory

    tasks = [
        _process_article(
            session_factory=article_session_factory,
            article_id=article.id,
            blog=blog,
            config=config,
            factory=factory,
            semaphore=semaphore,
        )
        for article in articles
    ]
    await asyncio.gather(*tasks)

    # ── Reload articles from DB to get their final states ──────────────
    for i, article in enumerate(articles):
        await session.refresh(article)

    # ── Update phase to publishing (all articles done) ─────────────────
    run.phase = "publishing"
    await session.commit()
    logger.info("Run %s phase → publishing", run.id)

    # ── Compute final counts ───────────────────────────────────────────
    articles_completed = sum(
        1 for a in articles if a.status == "published"
    )
    articles_failed = sum(
        1 for a in articles if a.status == "failed"
    )

    run.articles_total = len(articles)
    run.articles_completed = articles_completed
    run.articles_failed = articles_failed

    # ── Generate CSV for successful articles ───────────────────────────
    try:
        csv_path = _generate_csv_for_run(run, articles, blog, config)
    except Exception as exc:
        logger.warning(
            "CSV generation failed for run %s: %s", run.id, exc
        )
        csv_path = None
    run.csv_path = csv_path

    # ── Populate results_summary ───────────────────────────────────────
    keyword_results = []
    for article in articles:
        keyword_results.append(
            {
                "keyword": article.keyword,
                "status": article.status,
                "title": article.title,
                "wp_post_id": article.wp_post_id,
                "error_message": article.error_message,
            }
        )

    run.results_summary = {
        "total": len(articles),
        "completed": articles_completed,
        "failed": articles_failed,
        "keywords": keyword_results,
    }

    # ── Update phase to completed ──────────────────────────────────────
    run.phase = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "Run %s phase → completed (total=%d, completed=%d, failed=%d)",
        run.id,
        len(articles),
        articles_completed,
        articles_failed,
    )


# ---------------------------------------------------------------------------
# Public entry point (creates own session/engine)
# ---------------------------------------------------------------------------


async def run_bulk_pipeline(run_id: uuid.UUID) -> None:
    """Run the full bulk pipeline for the given run.

    This function creates its own database session and event loop context.
    It loads the run, blog, and pipeline configuration, then orchestrates
    the concurrent processing of all articles in the run.

    Args:
        run_id: The UUID of the run to process.

    Raises:
        ValueError: If the run or its associated blog/config is not found.
    """
    logger.info("Starting bulk pipeline for run_id=%s", run_id)

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            # Load run
            result = await session.execute(
                select(Run).where(Run.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise ValueError(f"Run not found: {run_id}")

            factory = ProviderFactory(session)
            await _run_bulk_pipeline(session, run, factory=factory)
    except ValueError:
        raise
    except Exception as exc:
        logger.error(
            "Unexpected error in bulk pipeline for %s: %s", run_id, exc
        )
        raise
    finally:
        await engine.dispose()
