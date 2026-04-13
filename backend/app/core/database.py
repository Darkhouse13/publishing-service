"""Async SQLAlchemy engine and session factory.

Supports:
- SQLite (aiosqlite) for local development and testing
- PostgreSQL (asyncpg) for production

Provides ``get_db`` as a FastAPI dependency that yields an ``AsyncSession``.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {}
if _is_sqlite:
    # SQLite needs check_same_thread=False for multi-threaded usage (FastAPI)
    # StaticPool is useful for in-memory SQLite in tests
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.DATABASE_URL or settings.DATABASE_URL == "sqlite+aiosqlite://":
        _engine_kwargs["poolclass"] = StaticPool

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    **_engine_kwargs,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for use as a FastAPI dependency.

    The session is automatically closed when the request finishes.
    """
    async with async_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


async def check_database_connection() -> bool:
    """Verify that the database is reachable.

    Returns ``True`` on success, ``False`` on failure.
    """
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
