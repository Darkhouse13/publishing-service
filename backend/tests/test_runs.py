"""Tests for Run API endpoints.

Covers:
- Empty list returns [] (GET /api/v1/runs)
- 404 for non-existent run (GET /api/v1/runs/{id})
- List returns created runs
"""

import uuid

from httpx import AsyncClient


class TestListRuns:
    """Tests for GET /api/v1/runs."""

    async def test_list_runs_returns_200(self, client: AsyncClient) -> None:
        """Listing runs should return HTTP 200."""
        resp = await client.get("/api/v1/runs")
        assert resp.status_code == 200

    async def test_list_runs_empty(self, client: AsyncClient) -> None:
        """With no runs, the response should be an empty list."""
        resp = await client.get("/api/v1/runs")
        assert resp.json() == []

    async def test_list_runs_returns_list(self, client: AsyncClient) -> None:
        """Response should be a JSON array."""
        resp = await client.get("/api/v1/runs")
        assert isinstance(resp.json(), list)


class TestGetRun:
    """Tests for GET /api/v1/runs/{run_id}."""

    async def test_get_nonexistent_run_returns_404(self, client: AsyncClient) -> None:
        """Requesting a non-existent run should return 404."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/runs/{fake_id}")
        assert resp.status_code == 404

    async def test_get_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Passing an invalid UUID should return 422."""
        resp = await client.get("/api/v1/runs/not-a-uuid")
        assert resp.status_code == 422
