"""Single article pipeline orchestration.

Executes the full single-article flow:

1. Load blog and pipeline config from the database.
2. Create providers via :class:`ProviderFactory`.
3. Update article status to ``"generating"``.
4. Generate article content via :class:`ArticleGenerator`.
5. Validate article via :class:`ArticleValidator`.
6. Update article with content fields.
7. Update status to ``"publishing"``.
8. Generate images via :class:`ImageGeneratorService`.
9. Publish via :class:`PublisherService`.
10. Update article with WordPress post details and image URLs.
11. Set status to ``"published"``.

On failure at any step, the article status is set to ``"failed"`` with an
``error_message``.
"""

from __future__ import annotations

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
from app.providers.factory import ProviderFactory
from app.services.article_generator import ArticleGenerator
from app.services.article_validator import ArticleValidator
from app.services.category_resolver import suggest_primary_category
from app.services.image_generator import ImageGeneratorService
from app.services.publisher import PublisherService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def _set_failed(
    session: AsyncSession,
    article: Article,
    error_message: str,
) -> None:
    """Mark an article as failed and persist the error message.

    Args:
        session: The active database session.
        article: The Article ORM instance to update.
        error_message: Description of the failure.
    """
    article.status = "failed"
    article.error_message = error_message
    await session.commit()
    logger.error(
        "Article %s → failed: %s", article.id, error_message
    )


async def _run_pipeline(
    session: AsyncSession,
    article: Article,
    *,
    factory: ProviderFactory,
) -> None:
    """Execute the single-article pipeline steps within a session.

    This is the core orchestration logic, separated from session/engine
    management so it can be tested with an injected session and factory.

    Args:
        session: An active :class:`AsyncSession`.
        article: The :class:`Article` ORM instance to process.
        factory: A :class:`ProviderFactory` for obtaining providers.
    """
    # ── Load blog and config ──────────────────────────────────────────
    result = await session.execute(
        select(Blog).where(Blog.id == article.blog_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise ValueError(f"Blog not found: {article.blog_id}")

    result = await session.execute(
        select(PipelineConfig).where(PipelineConfig.blog_id == blog.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise ValueError(f"PipelineConfig not found for blog: {blog.id}")

    # ── Create providers via ProviderFactory ──────────────────────────
    llm_provider = await factory.get_llm_provider(config.llm_provider)
    image_provider = await factory.get_image_provider(config.image_provider)
    wp_provider = await factory.get_wordpress_provider(
        "wp_rest",
        base_url=blog.url,
        username=blog.wp_username,
    )

    # ── 3. Update status to 'generating' ──────────────────────────────
    article.status = "generating"
    await session.commit()
    logger.info("Article %s status → generating", article.id)

    # ── 4. Generate article content via ArticleGenerator ───────────────
    generator = ArticleGenerator(llm_provider)
    try:
        payload = await generator.generate(
            topic=article.keyword,
            vibe="professional yet approachable",
            profile_prompt=blog.profile_prompt,
            focus_keyword=article.keyword,
        )
    except Exception as exc:
        logger.error(
            "Article generation failed for %s: %s", article.id, exc
        )
        await _set_failed(session, article, str(exc))
        return

    # Track generation attempts from LLM call count
    article.generation_attempts = llm_provider.call_count

    # ── 5. Validate article via ArticleValidator ───────────────────────
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

    # ── 6. Update article with content fields ──────────────────────────
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

    # Derive Pinterest fields from generated content
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

    # ── 7. Update status to 'publishing' ──────────────────────────────
    article.status = "publishing"
    await session.commit()
    logger.info("Article %s status → publishing", article.id)

    # ── 8. Generate images via ImageGeneratorService ───────────────────
    image_service = ImageGeneratorService(image_provider)
    artifacts_dir = Path(settings.ARTIFACTS_DIR)
    output_dir = artifacts_dir / str(article.id)

    try:
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
    except Exception as exc:
        logger.error(
            "Image generation failed for %s: %s", article.id, exc
        )
        await _set_failed(
            session, article, f"Image generation failed: {exc}"
        )
        return

    article.hero_image_url = hero_image_path
    article.detail_image_url = detail_image_path
    article.pin_image_url = hero_image_path
    await session.commit()

    # ── 9. Publish via PublisherService ────────────────────────────────
    publisher = PublisherService(wp_provider)
    try:
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
    except Exception as exc:
        logger.error(
            "Publishing failed for %s: %s", article.id, exc
        )
        await _set_failed(
            session, article, f"Publishing failed: {exc}"
        )
        return

    # ── 10. Update article with WordPress post details ─────────────────
    article.wp_post_id = publish_result.wp_post_id
    article.wp_permalink = publish_result.wp_permalink

    # ── 11. Set status to 'published' ──────────────────────────────────
    article.status = "published"
    article.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "Article %s status → published (wp_post_id=%s)",
        article.id,
        publish_result.wp_post_id,
    )


async def generate_single_article(article_id: uuid.UUID) -> None:
    """Run the full single-article pipeline for the given article.

    This function creates its own database session and event loop context.
    It loads the article, blog, and pipeline configuration from the database,
    then orchestrates the generation, validation, image creation, and
    publishing flow.

    Args:
        article_id: The UUID of the article to process.

    Raises:
        ValueError: If the article or its associated blog/config is not found.
    """
    logger.info(
        "Starting single article pipeline for article_id=%s", article_id
    )

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
            # Load article
            result = await session.execute(
                select(Article).where(Article.id == article_id)
            )
            article = result.scalar_one_or_none()
            if article is None:
                raise ValueError(f"Article not found: {article_id}")

            factory = ProviderFactory(session)
            await _run_pipeline(session, article, factory=factory)
    except ValueError:
        raise
    except Exception as exc:
        logger.error(
            "Unexpected error in single article pipeline for %s: %s",
            article_id,
            exc,
        )
        raise
    finally:
        await engine.dispose()
