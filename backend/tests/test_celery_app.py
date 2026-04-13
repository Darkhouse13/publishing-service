"""Tests for Celery app configuration.

Validates:
- Eager mode is enabled when REDIS_URL is None (VAL-TASK-004)
- Eager mode is disabled when REDIS_URL is set
- Celery app serialisation and timezone configuration
"""

from __future__ import annotations

import pytest
from celery import Celery  # type: ignore[import-untyped]


class TestCeleryEagerMode:
    """Verify Celery eager mode configuration based on REDIS_URL."""

    def test_eager_mode_on_when_redis_url_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When REDIS_URL is None, task_always_eager must be True.

        VAL-TASK-004: Celery app sets task_always_eager when REDIS_URL is not configured.
        """
        from app.core.config import Settings

        monkeypatch.delenv("REDIS_URL", raising=False)
        settings = Settings()
        assert settings.REDIS_URL is None

        app = Celery("test-eager-none")
        from app.tasks.celery_app import create_celery_app

        # Patch settings temporarily
        monkeypatch.setattr("app.tasks.celery_app.settings", settings)
        app = create_celery_app()

        assert app.conf.task_always_eager is True
        assert app.conf.task_eager_propagates is True

    def test_eager_mode_off_when_redis_url_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When REDIS_URL is set, task_always_eager should not be forced True."""
        from app.core.config import Settings

        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        settings = Settings()
        assert settings.REDIS_URL == "redis://localhost:6379/0"

        monkeypatch.setattr("app.tasks.celery_app.settings", settings)
        from app.tasks.celery_app import create_celery_app

        app = create_celery_app()

        assert app.conf.task_always_eager is False
        assert app.conf.task_eager_propagates is False

    def test_default_settings_have_redis_url_none(self) -> None:
        """Default settings should have REDIS_URL as None (no Redis configured)."""
        from app.core.config import settings

        assert settings.REDIS_URL is None

    def test_module_level_celery_has_eager_mode(self) -> None:
        """The module-level celery singleton has eager mode enabled (REDIS_URL=None)."""
        from app.tasks.celery_app import celery

        # In the default test environment, REDIS_URL is None
        assert celery.conf.task_always_eager is True
        assert celery.conf.task_eager_propagates is True

    def test_celery_app_is_singleton(self) -> None:
        """The module-level celery object should be a Celery instance."""
        from app.tasks.celery_app import celery

        assert isinstance(celery, Celery)

    def test_celery_app_name(self) -> None:
        """The Celery app should be named 'publishing-service'."""
        from app.tasks.celery_app import celery

        assert celery.main == "publishing-service"

    def test_celery_json_serialization(self) -> None:
        """Celery should use JSON serialization."""
        from app.tasks.celery_app import celery

        assert celery.conf.task_serializer == "json"
        assert celery.conf.result_serializer == "json"
        assert "json" in celery.conf.accept_content

    def test_celery_utc_timezone(self) -> None:
        """Celery should be configured with UTC timezone."""
        from app.tasks.celery_app import celery

        assert celery.conf.timezone == "UTC"
        assert celery.conf.enable_utc is True

    def test_celery_task_routes(self) -> None:
        """Pipeline tasks should be routed to the 'pipeline' queue."""
        from app.tasks.celery_app import celery

        routes = celery.conf.task_routes
        assert routes is not None
        assert "app.tasks.pipeline.*" in routes
        assert routes["app.tasks.pipeline.*"]["queue"] == "pipeline"
