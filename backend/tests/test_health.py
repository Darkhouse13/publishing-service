"""Tests for the /api/v1/health endpoint.

Fulfils VAL-HEALTH-001 (accessibility), VAL-HEALTH-002 (status JSON),
and VAL-HEALTH-005 (workspace directories).
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def base_url() -> str:
    return "http://testserver"


@pytest.fixture
def transport(base_url: str) -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport, base_url: str) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        yield c


class TestHealthEndpoint:
    """GET /api/v1/health returns correct structure."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_json(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_health_status_ok(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_contains_infrastructure_checks(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "checks" in data
        assert "infrastructure" in data["checks"]

    @pytest.mark.asyncio
    async def test_health_artifacts_dir_available(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        infra = data["checks"]["infrastructure"]
        assert "artifacts_dir" in infra
        assert infra["artifacts_dir"]["available"] is True

    @pytest.mark.asyncio
    async def test_health_artifacts_dir_writable(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        infra = data["checks"]["infrastructure"]
        assert infra["artifacts_dir"]["writable"] is True
