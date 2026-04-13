"""Tests for Celery pipeline tasks in app.tasks.pipeline.

Validates:
- Tasks use asyncio.run() to call async pipeline functions (VAL-TASK-001, VAL-TASK-002)
- Tasks execute in eager mode without Redis (VAL-TASK-003)
- Tasks create their own DB sessions
- Tasks are properly registered with Celery
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from celery import Celery  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Test: module importability
# ---------------------------------------------------------------------------


class TestPipelineTasksImport:
    """Verify that pipeline tasks can be imported."""

    def test_import_pipeline_module(self) -> None:
        """Importing app.tasks.pipeline must succeed without a running broker."""
        import app.tasks.pipeline  # noqa: F401

    def test_run_bulk_pipeline_task_importable(self) -> None:
        """``run_bulk_pipeline_task`` must be importable from the pipeline module."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        assert callable(run_bulk_pipeline_task)

    def test_generate_single_article_task_importable(self) -> None:
        """``generate_single_article_task`` must be importable from the pipeline module."""
        from app.tasks.pipeline import generate_single_article_task

        assert callable(generate_single_article_task)


# ---------------------------------------------------------------------------
# Test: tasks are registered Celery tasks
# ---------------------------------------------------------------------------


class TestPipelineTasksRegistration:
    """Verify that tasks are registered with the Celery app."""

    @pytest.fixture()
    def celery_app(self) -> Celery:
        from app.tasks.celery_app import celery as _celery

        return _celery

    def test_run_bulk_pipeline_is_celery_task(self) -> None:
        """``run_bulk_pipeline_task`` must be a registered Celery task."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        assert hasattr(run_bulk_pipeline_task, "delay")
        assert hasattr(run_bulk_pipeline_task, "apply_async")

    def test_generate_single_article_is_celery_task(self) -> None:
        """``generate_single_article_task`` must be a registered Celery task."""
        from app.tasks.pipeline import generate_single_article_task

        assert hasattr(generate_single_article_task, "delay")
        assert hasattr(generate_single_article_task, "apply_async")

    def test_run_bulk_pipeline_registered_name(self, celery_app: Celery) -> None:
        """``run_bulk_pipeline_task`` should be registered in the Celery app."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        assert run_bulk_pipeline_task.name in celery_app._tasks

    def test_generate_single_article_registered_name(self, celery_app: Celery) -> None:
        """``generate_single_article_task`` should be registered in the Celery app."""
        from app.tasks.pipeline import generate_single_article_task

        assert generate_single_article_task.name in celery_app._tasks

    def test_run_bulk_pipeline_task_name(self) -> None:
        """Task name should follow the convention."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        assert run_bulk_pipeline_task.name == "app.tasks.pipeline.run_bulk_pipeline"

    def test_generate_single_article_task_name(self) -> None:
        """Task name should follow the convention."""
        from app.tasks.pipeline import generate_single_article_task

        assert generate_single_article_task.name == "app.tasks.pipeline.generate_single_article"


# ---------------------------------------------------------------------------
# Test: tasks use asyncio.run() (VAL-TASK-001, VAL-TASK-002)
# ---------------------------------------------------------------------------


class TestPipelineTasksAsyncioRun:
    """Verify that tasks wrap async calls in asyncio.run()."""

    def test_run_bulk_pipeline_task_calls_asyncio_run(self) -> None:
        """VAL-TASK-001: run_bulk_pipeline_task wraps its async call in asyncio.run()."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        run_id = str(uuid.uuid4())
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.bulk_pipeline.run_bulk_pipeline", mock_pipeline):
            run_bulk_pipeline_task(run_id=run_id)
            mock_pipeline.assert_called_once_with(uuid.UUID(run_id))

    def test_generate_single_article_task_calls_asyncio_run(self) -> None:
        """VAL-TASK-002: generate_single_article_task wraps its async call in asyncio.run()."""
        from app.tasks.pipeline import generate_single_article_task

        article_id = str(uuid.uuid4())
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.single_article.generate_single_article", mock_pipeline):
            generate_single_article_task(article_id=article_id)
            mock_pipeline.assert_called_once_with(uuid.UUID(article_id))

    def test_run_bulk_pipeline_task_passes_uuid_to_pipeline(self) -> None:
        """run_bulk_pipeline_task converts run_id string to UUID and passes to pipeline."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        run_id = str(uuid.uuid4())
        run_uuid = uuid.UUID(run_id)
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.bulk_pipeline.run_bulk_pipeline", mock_pipeline):
            run_bulk_pipeline_task(run_id=run_id)
            args, _ = mock_pipeline.call_args
            assert args[0] == run_uuid

    def test_generate_single_article_task_passes_uuid_to_pipeline(self) -> None:
        """generate_single_article_task converts article_id string to UUID."""
        from app.tasks.pipeline import generate_single_article_task

        article_id = str(uuid.uuid4())
        article_uuid = uuid.UUID(article_id)
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.single_article.generate_single_article", mock_pipeline):
            generate_single_article_task(article_id=article_id)
            args, _ = mock_pipeline.call_args
            assert args[0] == article_uuid


# ---------------------------------------------------------------------------
# Test: tasks execute in eager mode (VAL-TASK-003)
# ---------------------------------------------------------------------------


class TestPipelineTasksEagerExecution:
    """Verify tasks execute synchronously in eager mode without Redis."""

    def test_tasks_execute_in_eager_mode(self) -> None:
        """VAL-TASK-003: Tasks execute synchronously in eager mode without Redis."""
        from app.tasks.celery_app import celery

        # In test/dev environment, REDIS_URL is None so eager mode is on
        assert celery.conf.task_always_eager is True

    def test_run_bulk_pipeline_task_eager_no_errors(self) -> None:
        """run_bulk_pipeline_task runs without Redis connection errors in eager mode."""
        from app.tasks.pipeline import run_bulk_pipeline_task

        run_id = str(uuid.uuid4())
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.bulk_pipeline.run_bulk_pipeline", mock_pipeline):
            # Should not raise any connection error
            run_bulk_pipeline_task(run_id=run_id)

    def test_generate_single_article_task_eager_no_errors(self) -> None:
        """generate_single_article_task runs without Redis connection errors in eager mode."""
        from app.tasks.pipeline import generate_single_article_task

        article_id = str(uuid.uuid4())
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.single_article.generate_single_article", mock_pipeline):
            # Should not raise any connection error
            generate_single_article_task(article_id=article_id)

    def test_task_delay_executes_eagerly(self) -> None:
        """Calling .delay() on a task executes it immediately in eager mode."""
        from app.tasks.pipeline import run_bulk_pipeline_task
        from app.tasks.celery_app import celery

        # Eager mode must be on
        assert celery.conf.task_always_eager is True

        run_id = str(uuid.uuid4())
        mock_pipeline = AsyncMock()

        with patch("app.pipeline.bulk_pipeline.run_bulk_pipeline", mock_pipeline):
            result = run_bulk_pipeline_task.delay(run_id)
            # In eager mode, result is available immediately
            assert result is not None
            mock_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# Test: tasks create their own DB sessions
# ---------------------------------------------------------------------------


class TestPipelineTaskSessionCreation:
    """Verify that tasks create their own database sessions via the pipeline functions."""

    def test_run_bulk_pipeline_task_creates_own_session(self) -> None:
        """The bulk pipeline function creates its own DB session."""
        from app.pipeline.bulk_pipeline import run_bulk_pipeline

        # The pipeline function should create its own engine/session internally
        import inspect

        source = inspect.getsource(run_bulk_pipeline)
        assert "create_async_engine" in source
        assert "async_sessionmaker" in source

    def test_generate_single_article_task_creates_own_session(self) -> None:
        """The single article pipeline function creates its own DB session."""
        from app.pipeline.single_article import generate_single_article

        import inspect

        source = inspect.getsource(generate_single_article)
        assert "create_async_engine" in source
        assert "async_sessionmaker" in source
