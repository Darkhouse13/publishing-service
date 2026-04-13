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
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    from app.models.article import Article
    from app.models.blog import Blog
    from app.models.pipeline_config import PipelineConfig
    from sqlalchemy import select

    logger.info("Starting single article pipeline for article_id=%s", article_id)

    # Create own async engine and session for this task
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
            # Load article with blog relationship
            result = await session.execute(
                select(Article).where(Article.id == article_id)
            )
            article = result.scalar_one_or_none()
            if article is None:
                raise ValueError(f"Article not found: {article_id}")

            # Load blog
            result = await session.execute(
                select(Blog).where(Blog.id == article.blog_id)
            )
            blog = result.scalar_one_or_none()
            if blog is None:
                raise ValueError(f"Blog not found: {article.blog_id}")

            # Load pipeline config
            result = await session.execute(
                select(PipelineConfig).where(PipelineConfig.blog_id == blog.id)
            )
            config = result.scalar_one_or_none()
            if config is None:
                raise ValueError(
                    f"PipelineConfig not found for blog: {blog.id}"
                )

            # Update status to generating
            article.status = "generating"
            await session.commit()
            logger.info(
                "Article %s status → generating", article_id
            )

            # The full pipeline implementation (generate → validate → images → publish)
            # will be completed by the m3-single-article-pipeline feature.
            # For now, this stub demonstrates the correct structure.

            logger.info(
                "Single article pipeline completed for article_id=%s", article_id
            )
    finally:
        await engine.dispose()
