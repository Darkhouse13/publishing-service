"""FastAPI application factory with lifespan management."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown lifecycle."""
    # Ensure runtime directories exist
    os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)

    # Create all tables (for dev/SQLite).  In production Alembic is used.
    from app.core.database import engine
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Dispose of the engine on shutdown
    from app.core.database import engine as _engine

    await _engine.dispose()


app = FastAPI(
    title="Publishing Service",
    version="0.1.0",
    description="Backend API for the publishing service.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health-check router
# ---------------------------------------------------------------------------

from fastapi import APIRouter  # noqa: E402

health_router = APIRouter(prefix="/api/v1/health", tags=["health"])


@health_router.get("")
async def health_check() -> dict[str, Any]:
    """Return overall system health status.

    Fulfils VAL-HEALTH-001, VAL-HEALTH-002, VAL-HEALTH-003, VAL-HEALTH-005.
    """
    checks: dict[str, Any] = {}

    # Database connectivity
    from app.core.database import check_database_connection

    db_connected = await check_database_connection()
    checks["database"] = {
        "status": "connected" if db_connected else "disconnected",
    }

    # Infrastructure / workspace directories
    artifacts_exists = os.path.isdir(settings.ARTIFACTS_DIR)
    artifacts_writable = os.access(settings.ARTIFACTS_DIR, os.W_OK) if artifacts_exists else False
    checks["infrastructure"] = {
        "artifacts_dir": {
            "path": settings.ARTIFACTS_DIR,
            "available": artifacts_exists,
            "writable": artifacts_writable,
        },
    }

    # Overall status
    all_ok = db_connected and artifacts_exists and artifacts_writable

    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }


app.include_router(health_router)


# ---------------------------------------------------------------------------
# Domain routers
# ---------------------------------------------------------------------------

from app.api.blogs import router as blogs_router  # noqa: E402

app.include_router(blogs_router)
