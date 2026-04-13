"""Shared pytest fixtures for the backend test suite."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.base import Base


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee an ``ENCRYPTION_KEY`` is set for every test.

    If the environment already provides one (e.g. via ``backend/.env``) we
    leave it untouched.  Otherwise we generate a fresh Fernet key so that
    crypto tests work in isolated CI environments.
    """
    if not os.getenv("ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        # Also patch the lazily-initialised module-level Fernet so it picks
        # up the new key on next access.
        import app.crypto as _crypto_mod

        _crypto_mod._fernet = None


# ---------------------------------------------------------------------------
# Database fixtures (in-memory SQLite for isolated tests)
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite://"

_test_engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_TestSessionFactory = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def _setup_database() -> AsyncGenerator[None, None]:
    """Create all tables before each test and drop them after.

    This ensures every test runs against a fresh, empty database.
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an ``AsyncSession`` backed by an in-memory SQLite database."""
    async with _TestSessionFactory() as session:
        yield session
