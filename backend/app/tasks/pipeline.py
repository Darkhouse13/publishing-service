"""Placeholder task stubs for pipeline operations.

This module defines Celery task stubs for the two core pipeline operations:

- ``run_bulk_pipeline`` – orchestrates the full bulk content generation run.
- ``generate_single_article`` – generates a single article for a given keyword.

Both tasks currently raise :exc:`NotImplementedError` so they can be
registered and discovered by Celery while the actual pipeline logic is
being developed in a later milestone.
"""

from __future__ import annotations

from app.tasks.celery_app import celery


@celery.task(  # type: ignore[untyped-decorator]
    name="app.tasks.pipeline.run_bulk_pipeline",
    bind=True,
)
def run_bulk_pipeline(self: object, **kwargs: object) -> None:  # noqa: ARG001
    """Execute the full bulk pipeline for a blog.

    This is a placeholder task stub.  It will be replaced with the actual
    orchestration logic that drives scraping, keyword selection, article
    generation, image creation, and WordPress publishing.

    Parameters
    ----------
    self:
        Celery ``self`` reference when ``bind=True``.
    **kwargs:
        Reserved for future arguments (e.g. ``blog_id``, run options).

    Raises
    ------
    NotImplementedError
        Always raised until the real implementation is provided.
    """
    raise NotImplementedError("run_bulk_pipeline is not yet implemented")


@celery.task(  # type: ignore[untyped-decorator]
    name="app.tasks.pipeline.generate_single_article",
    bind=True,
)
def generate_single_article(self: object, **kwargs: object) -> None:  # noqa: ARG001
    """Generate a single article for a specific keyword and blog.

    This is a placeholder task stub.  It will be replaced with the actual
    logic that generates an article via the configured LLM provider.

    Parameters
    ----------
    self:
        Celery ``self`` reference when ``bind=True``.
    **kwargs:
        Reserved for future arguments (e.g. ``blog_id``, ``keyword``).

    Raises
    ------
    NotImplementedError
        Always raised until the real implementation is provided.
    """
    raise NotImplementedError("generate_single_article is not yet implemented")
