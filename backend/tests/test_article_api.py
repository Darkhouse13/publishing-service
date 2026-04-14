"""Tests for POST /api/v1/articles and related endpoints.

Fulfils:
- VAL-API-006: POST /articles creates Article in pending state
- VAL-API-007: POST /articles validates blog exists
- VAL-API-008: POST /articles dispatches single article task
- VAL-API-009: POST /articles sets blog_id and nullable run_id
- VAL-API-014: POST /articles returns 422 for missing fields
"""

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt
from app.models.blog import Blog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_blog_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid blog creation payload."""
    return {
        "name": "Test Blog",
        "url": "https://testblog.com",
        "wp_username": "admin",
        "wp_application_password": "super-secret-password",
        **overrides,
    }


def _make_article_payload(blog_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    """Return a valid article creation payload."""
    return {
        "blog_id": str(blog_id),
        "topic": "test topic for article generation",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def blog_in_db(db_session: AsyncSession) -> Blog:
    """Create and persist a Blog, returning the ORM instance."""
    blog = Blog(
        name="Test Blog",
        slug="test-blog",
        url="https://testblog.com",
        wp_username="admin",
        wp_app_password_encrypted=encrypt("super-secret-password"),
    )
    db_session.add(blog)
    await db_session.flush()
    await db_session.refresh(blog)
    return blog


@pytest_asyncio.fixture()
async def existing_blog_via_api(client: AsyncClient) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=_make_blog_payload())
    assert response.status_code == 201
    return dict(response.json())


# ===================================================================
# VAL-API-006: POST /articles creates Article in pending state
# ===================================================================


class TestCreateArticle:
    """Tests for POST /api/v1/articles."""

    @pytest.mark.asyncio
    async def test_create_article_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /articles with valid data returns 201."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_article_status_pending(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created article has status='pending'."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_article_returns_id(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created article returns a valid UUID id."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert "id" in data
        uuid.UUID(data["id"])  # Should not raise

    @pytest.mark.asyncio
    async def test_create_article_keyword_is_topic(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Article keyword field is set from the topic parameter."""
        payload = _make_article_payload(blog_in_db.id, topic="outdoor living tips")
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["keyword"] == "outdoor living tips"


# ===================================================================
# VAL-API-007: POST /articles validates blog exists
# ===================================================================


class TestCreateArticleBlogValidation:
    """Validate blog existence check on article creation."""

    @pytest.mark.asyncio
    async def test_create_article_nonexistent_blog_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /articles with non-existent blog_id returns 422."""
        fake_id = str(uuid.uuid4())
        payload = _make_article_payload(uuid.UUID(fake_id))
        resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_article_nonexistent_blog_error_detail(
        self,
        client: AsyncClient,
    ) -> None:
        """Error detail mentions blog not found."""
        fake_id = str(uuid.uuid4())
        payload = _make_article_payload(uuid.UUID(fake_id))
        resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert "not found" in str(data["detail"]).lower() or "inactive" in str(data["detail"]).lower()


# ===================================================================
# VAL-API-008: POST /articles dispatches single article task
# ===================================================================


class TestCreateArticleDispatchesTask:
    """Validate that single article task is dispatched."""

    @pytest.mark.asyncio
    async def test_create_article_dispatches_single_article_task(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """generate_single_article_task.delay is called with article_id."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201
        mock_task.delay.assert_called_once()

        # Verify the task was called with the article's ID
        call_args = mock_task.delay.call_args[0]
        assert len(call_args) == 1
        article_id = call_args[0]
        assert article_id == str(resp.json()["id"])


# ===================================================================
# VAL-API-009: POST /articles sets blog_id and nullable run_id
# ===================================================================


class TestCreateArticleFields:
    """Validate article field values on creation."""

    @pytest.mark.asyncio
    async def test_create_article_sets_blog_id(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created article has blog_id set to the provided value."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["blog_id"] == str(blog_in_db.id)

    @pytest.mark.asyncio
    async def test_create_article_run_id_is_null(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created article has run_id set to None (standalone article)."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["run_id"] is None

    @pytest.mark.asyncio
    async def test_create_article_default_fields(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """New article has expected default field values."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["title"] is None
        assert data["status"] == "pending"
        assert data["wp_post_id"] is None
        assert data["error_message"] is None
        assert data["generation_attempts"] == 0
        assert data["validation_errors"] == []


# ===================================================================
# VAL-API-014: POST /articles returns 422 for missing fields
# ===================================================================


class TestCreateArticleMissingFields:
    """Validate missing required fields return 422."""

    @pytest.mark.asyncio
    async def test_create_article_missing_blog_id(self, client: AsyncClient) -> None:
        """Missing blog_id returns 422."""
        resp = await client.post("/api/v1/articles", json={"topic": "test"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_article_missing_topic(self, client: AsyncClient) -> None:
        """Missing topic returns 422."""
        resp = await client.post(
            "/api/v1/articles", json={"blog_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_article_empty_topic(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Empty topic string returns 422."""
        payload = _make_article_payload(blog_in_db.id, topic="")
        resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_article_empty_body(self, client: AsyncClient) -> None:
        """Empty body returns 422."""
        resp = await client.post("/api/v1/articles", json={})
        assert resp.status_code == 422


# ===================================================================
# POST /articles → GET /articles/{id} round-trip
# ===================================================================


class TestArticleRoundTrip:
    """POST /articles then GET /articles/{id} consistency."""

    @pytest.mark.asyncio
    async def test_post_get_round_trip(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """All fields from POST are present and correct in GET response."""
        payload = _make_article_payload(blog_in_db.id, topic="round trip topic")
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/articles", json=payload)

        assert create_resp.status_code == 201
        create_data = create_resp.json()

        get_resp = await client.get(f"/api/v1/articles/{create_data['id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        # Fields should match between POST and GET
        assert get_data["id"] == create_data["id"]
        assert get_data["blog_id"] == create_data["blog_id"]
        assert get_data["keyword"] == create_data["keyword"]
        assert get_data["status"] == create_data["status"]
        assert get_data["run_id"] == create_data["run_id"]
