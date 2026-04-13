"""Tests for pipeline task stubs in app.tasks.pipeline."""

from __future__ import annotations

import pytest
from celery import Celery  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Test: module importability
# ---------------------------------------------------------------------------


class TestPipelineTasksImport:
    """Verify that pipeline task stubs can be imported."""

    def test_import_pipeline_module(self) -> None:
        """Importing app.tasks.pipeline must succeed without a running broker."""
        import app.tasks.pipeline  # noqa: F401

    def test_run_bulk_pipeline_importable(self) -> None:
        """``run_bulk_pipeline`` must be importable from the pipeline module."""
        from app.tasks.pipeline import run_bulk_pipeline

        assert callable(run_bulk_pipeline)

    def test_generate_single_article_importable(self) -> None:
        """``generate_single_article`` must be importable from the pipeline module."""
        from app.tasks.pipeline import generate_single_article

        assert callable(generate_single_article)


# ---------------------------------------------------------------------------
# Test: tasks are registered Celery tasks
# ---------------------------------------------------------------------------


class TestPipelineTasksRegistration:
    """Verify that task stubs are registered with the Celery app."""

    @pytest.fixture()
    def celery_app(self) -> Celery:
        from app.tasks.celery_app import celery as _celery

        return _celery

    def test_run_bulk_pipeline_is_celery_task(self) -> None:
        """``run_bulk_pipeline`` must be a registered Celery task."""
        from app.tasks.pipeline import run_bulk_pipeline

        assert hasattr(run_bulk_pipeline, "delay")
        assert hasattr(run_bulk_pipeline, "apply_async")

    def test_generate_single_article_is_celery_task(self) -> None:
        """``generate_single_article`` must be a registered Celery task."""
        from app.tasks.pipeline import generate_single_article

        assert hasattr(generate_single_article, "delay")
        assert hasattr(generate_single_article, "apply_async")

    def test_run_bulk_pipeline_registered_name(self, celery_app: Celery) -> None:
        """``run_bulk_pipeline`` should be registered in the Celery app."""
        from app.tasks.pipeline import run_bulk_pipeline

        assert run_bulk_pipeline.name in celery_app._tasks

    def test_generate_single_article_registered_name(self, celery_app: Celery) -> None:
        """``generate_single_article`` should be registered in the Celery app."""
        from app.tasks.pipeline import generate_single_article

        assert generate_single_article.name in celery_app._tasks


# ---------------------------------------------------------------------------
# Test: tasks raise NotImplementedError (placeholder behavior)
# ---------------------------------------------------------------------------


class TestPipelineTasksRaiseNotImplemented:
    """Verify that task stubs raise ``NotImplementedError`` when called."""

    def test_run_bulk_pipeline_raises_not_implemented(self) -> None:
        """Calling ``run_bulk_pipeline`` directly must raise ``NotImplementedError``."""
        from app.tasks.pipeline import run_bulk_pipeline

        with pytest.raises(NotImplementedError, match="run_bulk"):
            run_bulk_pipeline()

    def test_generate_single_article_raises_not_implemented(self) -> None:
        """Calling ``generate_single_article`` directly must raise ``NotImplementedError``."""
        from app.tasks.pipeline import generate_single_article

        with pytest.raises(NotImplementedError, match="generate_single_article"):
            generate_single_article()

    def test_run_bulk_pipeline_raises_with_args(self) -> None:
        """Calling ``run_bulk_pipeline`` with arguments must still raise ``NotImplementedError``."""
        from app.tasks.pipeline import run_bulk_pipeline

        with pytest.raises(NotImplementedError):
            run_bulk_pipeline(blog_id="test-id")

    def test_generate_single_article_raises_with_args(self) -> None:
        """Calling ``generate_single_article`` with arguments must still raise ``NotImplementedError``."""
        from app.tasks.pipeline import generate_single_article

        with pytest.raises(NotImplementedError):
            generate_single_article(blog_id="test-id", keyword="test keyword")
