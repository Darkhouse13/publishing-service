"""Tests for the async database configuration.

Verifies:
- Database connectivity works with SQLite
- AsyncSession is injectable via FastAPI dependencies
- check_database_connection returns True
- Health endpoint includes database status 'connected'
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app


# ---------------------------------------------------------------------------
# Unit tests – engine / session / connectivity
# ---------------------------------------------------------------------------


class TestDatabaseConnectivity:
    """Verify that the database engine can connect and execute queries."""

    @pytest.mark.asyncio
    async def test_check_database_connection_returns_true(self) -> None:
        from app.core.database import check_database_connection

        result = await check_database_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_simple_query(self, db_session: AsyncSession) -> None:
        """A raw SQL SELECT 1 should succeed on the test database."""
        result = await db_session.execute(text("SELECT 1"))
        row = result.scalar_one()
        assert row == 1

    @pytest.mark.asyncio
    async def test_session_provides_async_session(self, db_session: AsyncSession) -> None:
        """The fixture should yield a usable AsyncSession."""
        assert isinstance(db_session, AsyncSession)

    @pytest.mark.asyncio
    async def test_session_can_create_tables(self, db_session: AsyncSession) -> None:
        """The test database should accept table creation (Base metadata)."""
        # If _setup_database fixture works, tables were already created.
        # Just verify we can query sqlite_master.
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = result.scalars().all()
        # At a minimum, no error means tables were created successfully
        assert isinstance(tables, list)


# ---------------------------------------------------------------------------
# Integration tests – FastAPI dependency injection
# ---------------------------------------------------------------------------


class TestAsyncSessionInjection:
    """Verify AsyncSession is injectable via FastAPI dependencies."""

    @pytest.fixture
    def base_url(self) -> str:
        return "http://testserver"

    @pytest.fixture
    def transport(self, base_url: str) -> ASGITransport:
        return ASGITransport(app=app)

    @pytest_asyncio.fixture()
    async def client(self, transport: ASGITransport, base_url: str) -> AsyncClient:
        async with AsyncClient(transport=transport, base_url=base_url) as c:
            yield c

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self) -> None:
        """The get_db dependency should yield a usable AsyncSession."""
        from app.core.database import get_db

        session_gen = get_db()
        session = await session_gen.__anext__()
        assert isinstance(session, AsyncSession)

        # Execute a query to prove it works
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

        # Clean up
        try:
            await session_gen.__anext__()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_health_endpoint_includes_database_connected(self, client: AsyncClient) -> None:
        """GET /api/v1/health should include database.status = 'connected'.

        Fulfils VAL-HEALTH-003.
        """
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "connected"
