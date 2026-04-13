"""Celery tasks for pipeline operations.

This module defines Celery tasks for the two core pipeline operations:

- ``run_bulk_pipeline_task`` – orchestrates the full bulk content generation run.
- ``generate_single_article_task`` – generates a single article.

Each task is a **synchronous** entry point that creates its own event loop
via :func:`asyncio.run` and its own database session.  The actual pipeline
logic lives in the async functions under :mod:`app.pipeline`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(  # type: ignore[untyped-decorator]
    name="app.tasks.pipeline.run_bulk_pipeline",
    bind=True,
)
def run_bulk_pipeline_task(
    self: object,  # noqa: ARG001
    run_id: str,
) -> None:
    """Execute the full bulk pipeline for a run.

    This is a synchronous Celery task entry point.  It wraps the async
    :func:`app.pipeline.bulk_pipeline.run_bulk_pipeline` in
    :func:`asyncio.run` so that it can be executed by Celery workers.

    The task creates its own event loop and database session, ensuring
    isolation from the caller's async context.

    Args:
        self: Celery ``self`` reference when ``bind=True``.
        run_id: The UUID string of the run to process.
    """
    from app.pipeline.bulk_pipeline import run_bulk_pipeline

    run_uuid = uuid.UUID(run_id)
    logger.info("Celery task run_bulk_pipeline_task started for run_id=%s", run_id)
    asyncio.run(run_bulk_pipeline(run_uuid))
    logger.info("Celery task run_bulk_pipeline_task completed for run_id=%s", run_id)


@celery.task(  # type: ignore[untyped-decorator]
    name="app.tasks.pipeline.generate_single_article",
    bind=True,
)
def generate_single_article_task(
    self: object,  # noqa: ARG001
    article_id: str,
) -> None:
    """Generate a single article.

    This is a synchronous Celery task entry point.  It wraps the async
    :func:`app.pipeline.single_article.generate_single_article` in
    :func:`asyncio.run` so that it can be executed by Celery workers.

    The task creates its own event loop and database session, ensuring
    isolation from the caller's async context.

    Args:
        self: Celery ``self`` reference when ``bind=True``.
        article_id: The UUID string of the article to process.
    """
    from app.pipeline.single_article import generate_single_article

    article_uuid = uuid.UUID(article_id)
    logger.info(
        "Celery task generate_single_article_task started for article_id=%s",
        article_id,
    )
    asyncio.run(generate_single_article(article_uuid))
    logger.info(
        "Celery task generate_single_article_task completed for article_id=%s",
        article_id,
    )
