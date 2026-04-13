"""Celery application factory for background task processing.

This module provides a Celery app instance configured with broker and result
backend URLs sourced from :class:`app.core.config.Settings`.  The module is
designed to be importable **without** a running Redis instance so that tests
and configuration checks can proceed offline.
"""

from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import settings

# ---------------------------------------------------------------------------
# Default URLs (used when REDIS_URL is not configured)
# ---------------------------------------------------------------------------

_DEFAULT_BROKER_URL = "redis://localhost:6379/0"
_DEFAULT_RESULT_BACKEND = "redis://localhost:6379/0"


def create_celery_app() -> Celery:
    """Create and return a configured :class:`Celery` application.

    The broker and result-backend URLs are resolved in this order:

    1. ``settings.REDIS_URL`` if it is set (via env var or ``.env`` file).
    2. The ``_DEFAULT_BROKER_URL`` / ``_DEFAULT_RESULT_BACKEND`` fallback.

    Configuration defaults follow the project's conventions (JSON
    serialization, UTC timezone).
    """
    broker_url = settings.REDIS_URL or _DEFAULT_BROKER_URL
    result_backend = settings.REDIS_URL or _DEFAULT_RESULT_BACKEND

    app = Celery(
        "publishing-service",
        broker=broker_url,
        backend=result_backend,
    )

    app.conf.update(
        # Serialization -------------------------------------------------------
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Timezone ------------------------------------------------------------
        timezone="UTC",
        enable_utc=True,
        # Task tracking -------------------------------------------------------
        task_track_started=True,
        # Autodiscovery (tasks live in app/tasks/*.py) ------------------------
        task_routes={
            "app.tasks.pipeline.*": {"queue": "pipeline"},
        },
    )

    return app


# ---------------------------------------------------------------------------
# Module-level singleton – this is what ``celery -A app.tasks.celery_app`` picks up.
# ---------------------------------------------------------------------------

celery = create_celery_app()
