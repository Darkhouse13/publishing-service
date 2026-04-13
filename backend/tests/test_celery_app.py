"""Tests for the Celery app factory."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from celery import Celery  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Test: module importability without a running Redis instance
# ---------------------------------------------------------------------------


class TestCeleryAppImport:
    """Verify that the Celery app can be imported without a running broker."""

    def test_import_celery_app_module(self) -> None:
        """Importing app.tasks.celery_app must succeed without Redis."""
        import app.tasks.celery_app  # noqa: F401

    def test_celery_instance_exists(self) -> None:
        """The module must export a ``celery`` attribute that is a Celery instance."""
        from app.tasks.celery_app import celery

        assert isinstance(celery, Celery)

    def test_celery_has_broker(self) -> None:
        """The Celery app must have a broker URL configured."""
        from app.tasks.celery_app import celery

        assert celery.conf.broker_url is not None
        assert celery.conf.broker_url != ""

    def test_celery_has_backend(self) -> None:
        """The Celery app must have a result backend URL configured."""
        from app.tasks.celery_app import celery

        assert celery.conf.result_backend is not None
        assert celery.conf.result_backend != ""


# ---------------------------------------------------------------------------
# Test: factory function produces correctly configured app
# ---------------------------------------------------------------------------


class TestCeleryAppFactory:
    """Test the ``create_celery_app`` factory function."""

    def test_factory_returns_celery_instance(self) -> None:
        from app.tasks.celery_app import create_celery_app

        app = create_celery_app()
        assert isinstance(app, Celery)

    def test_factory_broker_from_settings(self) -> None:
        """Factory should use REDIS_URL from Settings as the broker."""
        from app.tasks.celery_app import create_celery_app

        app = create_celery_app()
        # Default broker should be Redis-based when REDIS_URL is set,
        # or a sensible default when it's not.
        assert "redis" in app.conf.broker_url or "memory" in app.conf.broker_url

    def test_factory_backend_from_settings(self) -> None:
        """Factory should use REDIS_URL from Settings as the result backend."""
        from app.tasks.celery_app import create_celery_app

        app = create_celery_app()
        assert "redis" in app.conf.result_backend or "rpc" in app.conf.result_backend or "cache" in app.conf.result_backend

    def test_factory_with_explicit_redis_url(self) -> None:
        """Factory should use an explicitly provided REDIS_URL."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://custom-host:6379/2"}):
            # Force Settings to re-read from env
            import app.core.config as config_mod

            importlib.reload(config_mod)
            try:
                # Reload celery_app so it picks up the new settings
                import app.tasks.celery_app as celery_mod

                importlib.reload(celery_mod)
                app = celery_mod.create_celery_app()
                assert app.conf.broker_url == "redis://custom-host:6379/2"
                assert app.conf.result_backend == "redis://custom-host:6379/2"
            finally:
                # Reload again to restore original Settings and celery app
                importlib.reload(config_mod)
                importlib.reload(celery_mod)

    def test_factory_default_broker_when_no_redis(self) -> None:
        """When REDIS_URL is not set, factory should use a sensible default."""
        from app.tasks.celery_app import create_celery_app

        # Save and remove REDIS_URL if present
        saved = os.environ.pop("REDIS_URL", None)
        try:
            import app.core.config as config_mod

            importlib.reload(config_mod)
            app = create_celery_app()
            # Should still produce a valid broker URL (memory or default redis)
            assert app.conf.broker_url is not None
        finally:
            if saved is not None:
                os.environ["REDIS_URL"] = saved
            importlib.reload(config_mod)


# ---------------------------------------------------------------------------
# Test: Celery configuration values
# ---------------------------------------------------------------------------


class TestCeleryConfiguration:
    """Verify important Celery configuration defaults."""

    @pytest.fixture()
    def celery_app(self) -> Celery:
        from app.tasks.celery_app import celery

        return celery

    def test_serializer_is_json(self, celery_app: Celery) -> None:
        """Task serializer should be JSON for interoperability."""
        assert celery_app.conf.task_serializer == "json"

    def test_result_serializer_is_json(self, celery_app: Celery) -> None:
        """Result serializer should be JSON."""
        assert celery_app.conf.result_serializer == "json"

    def test_accept_content_includes_json(self, celery_app: Celery) -> None:
        """Accept content should include JSON."""
        assert "json" in celery_app.conf.accept_content

    def test_timezone_is_utc(self, celery_app: Celery) -> None:
        """Celery timezone should be UTC."""
        assert celery_app.conf.timezone == "UTC"

    def test_enable_utc(self, celery_app: Celery) -> None:
        """UTC support should be enabled."""
        assert celery_app.conf.enable_utc is True

    def test_task_track_started(self, celery_app: Celery) -> None:
        """Track started flag should be enabled for task monitoring."""
        assert celery_app.conf.task_track_started is True


# ---------------------------------------------------------------------------
# Test: module-level celery instance is same as factory output
# ---------------------------------------------------------------------------


class TestModuleLevelInstance:
    """The module-level ``celery`` should be the default app instance."""

    def test_module_celery_is_from_factory(self) -> None:
        from app.tasks.celery_app import celery, create_celery_app

        fresh = create_celery_app()
        # Both should have the same broker/backend configuration
        assert celery.conf.broker_url == fresh.conf.broker_url
        assert celery.conf.result_backend == fresh.conf.result_backend
