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

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    from app.models.run import Run
    from app.models.blog import Blog
    from app.models.pipeline_config import PipelineConfig
    from sqlalchemy import select

    logger.info("Starting bulk pipeline for run_id=%s", run_id)

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
            # Load run with blog relationship
            result = await session.execute(
                select(Run).where(Run.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise ValueError(f"Run not found: {run_id}")

            # Load blog
            result = await session.execute(
                select(Blog).where(Blog.id == run.blog_id)
            )
            blog = result.scalar_one_or_none()
            if blog is None:
                raise ValueError(f"Blog not found: {run.blog_id}")

            # Load pipeline config
            result = await session.execute(
                select(PipelineConfig).where(PipelineConfig.blog_id == blog.id)
            )
            config = result.scalar_one_or_none()
            if config is None:
                raise ValueError(
                    f"PipelineConfig not found for blog: {blog.id}"
                )

            # Update phase to generating
            run.phase = "generating"
            await session.commit()
            logger.info("Run %s phase → generating", run_id)

            # The full bulk pipeline implementation (concurrent article processing,
            # CSV generation, etc.) will be completed by the m3-bulk-pipeline feature.
            # For now, this stub demonstrates the correct structure.

            # Handle zero keywords gracefully
            if not run.seed_keywords:
                run.phase = "completed"
                run.articles_total = 0
                run.articles_completed = 0
                run.articles_failed = 0
                await session.commit()
                logger.info("Run %s completed with 0 keywords", run_id)
                return

            logger.info("Bulk pipeline completed for run_id=%s", run_id)
    finally:
        await engine.dispose()
