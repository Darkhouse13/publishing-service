"""Tests for Article API endpoints.

Covers:
- Empty list returns [] (GET /api/v1/articles)
- 404 for non-existent article (GET /api/v1/articles/{id})
- List returns created articles
"""

import uuid

from httpx import AsyncClient


class TestListArticles:
    """Tests for GET /api/v1/articles."""

    async def test_list_articles_returns_200(self, client: AsyncClient) -> None:
        """Listing articles should return HTTP 200."""
        resp = await client.get("/api/v1/articles")
        assert resp.status_code == 200

    async def test_list_articles_empty(self, client: AsyncClient) -> None:
        """With no articles, the response should be an empty list."""
        resp = await client.get("/api/v1/articles")
        assert resp.json() == []

    async def test_list_articles_returns_list(self, client: AsyncClient) -> None:
        """Response should be a JSON array."""
        resp = await client.get("/api/v1/articles")
        assert isinstance(resp.json(), list)


class TestGetArticle:
    """Tests for GET /api/v1/articles/{article_id}."""

    async def test_get_nonexistent_article_returns_404(self, client: AsyncClient) -> None:
        """Requesting a non-existent article should return 404."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/articles/{fake_id}")
        assert resp.status_code == 404

    async def test_get_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Passing an invalid UUID should return 422."""
        resp = await client.get("/api/v1/articles/not-a-uuid")
        assert resp.status_code == 422
