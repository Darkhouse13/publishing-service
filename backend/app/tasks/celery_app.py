"""Celery application factory for background task processing.

This module provides a Celery app instance configured with broker and result
backend URLs sourced from :class:`app.core.config.Settings`.  The module is
designed to be importable **without** a running Redis instance so that tests
and configuration checks can proceed offline.

When ``settings.REDIS_URL`` is ``None`` (the default for local development),
the Celery app is configured with ``task_always_eager=True`` and
``task_eager_propagates=True`` so that all tasks execute synchronously in
the calling process without requiring a Redis broker.
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

    When ``settings.REDIS_URL`` is ``None``, eager mode is enabled so tasks
    execute synchronously without a running broker.

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

    conf_update: dict[str, object] = {
        # Serialization -------------------------------------------------------
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        # Timezone ------------------------------------------------------------
        "timezone": "UTC",
        "enable_utc": True,
        # Task tracking -------------------------------------------------------
        "task_track_started": True,
        # Autodiscovery (tasks live in app/tasks/*.py) ------------------------
        "task_routes": {
            "app.tasks.pipeline.*": {"queue": "pipeline"},
        },
    }

    # When REDIS_URL is not configured, enable eager mode so tasks execute
    # synchronously in the calling process without a real broker.
    if settings.REDIS_URL is None:
        conf_update["task_always_eager"] = True
        conf_update["task_eager_propagates"] = True

    app.conf.update(**conf_update)

    return app


# ---------------------------------------------------------------------------
# Module-level singleton – this is what ``celery -A app.tasks.celery_app`` picks up.
# ---------------------------------------------------------------------------

celery = create_celery_app()
