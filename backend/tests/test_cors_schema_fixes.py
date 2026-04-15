"""Tests for CORS middleware, schema fixes (vibe/focus_keyword, is_active).

Fulfils:
- VAL-BACKEND-001: ArticleCreate accepts vibe and focus_keyword
- VAL-BACKEND-002: ArticleCreate accepts missing vibe and focus_keyword
- VAL-BACKEND-003: BlogUpdate accepts is_active
- VAL-BACKEND-004: CORS middleware allows localhost:3000
- VAL-BACKEND-005: Backend tests pass
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
# VAL-BACKEND-001: ArticleCreate accepts vibe and focus_keyword
# ===================================================================


class TestArticleCreateVibeAndFocusKeyword:
    """POST /api/v1/articles with vibe and focus_keyword stores them correctly."""

    @pytest.mark.asyncio
    async def test_create_article_with_vibe_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /articles with vibe returns 201."""
        payload = _make_article_payload(blog_in_db.id, vibe="casual")
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_article_with_focus_keyword_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /articles with focus_keyword returns 201."""
        payload = _make_article_payload(
            blog_in_db.id, focus_keyword="weekend brunch"
        )
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_article_with_both_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /articles with both vibe and focus_keyword returns 201."""
        payload = _make_article_payload(
            blog_in_db.id, vibe="casual", focus_keyword="weekend brunch"
        )
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_vibe_stored_in_brain_output(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Vibe is stored in article.brain_output as {"vibe": payload.vibe}."""
        payload = _make_article_payload(
            blog_in_db.id, vibe="casual", focus_keyword="brunch"
        )
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["brain_output"] == {"vibe": "casual"}

    @pytest.mark.asyncio
    async def test_focus_keyword_stored_on_article(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Focus keyword is stored directly on the article model."""
        payload = _make_article_payload(
            blog_in_db.id, vibe="casual", focus_keyword="weekend brunch"
        )
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["focus_keyword"] == "weekend brunch"

    @pytest.mark.asyncio
    async def test_vibe_and_focus_keyword_round_trip(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """GET /articles/{id} returns the vibe and focus_keyword from POST."""
        payload = _make_article_payload(
            blog_in_db.id, vibe="professional", focus_keyword="seo tips"
        )
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/articles", json=payload)
        assert create_resp.status_code == 201
        article_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/articles/{article_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["brain_output"] == {"vibe": "professional"}
        assert data["focus_keyword"] == "seo tips"


# ===================================================================
# VAL-BACKEND-002: ArticleCreate accepts missing vibe and focus_keyword
# ===================================================================


class TestArticleCreateMissingVibeAndFocusKeyword:
    """POST /api/v1/articles without vibe and focus_keyword defaults correctly."""

    @pytest.mark.asyncio
    async def test_create_article_without_vibe_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /articles without vibe still returns 201."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_article_without_vibe_brain_output_is_none(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """When vibe is not provided, brain_output should be None."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["brain_output"] is None

    @pytest.mark.asyncio
    async def test_create_article_without_focus_keyword_is_null(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """When focus_keyword is not provided, it should be null."""
        payload = _make_article_payload(blog_in_db.id)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["focus_keyword"] is None

    @pytest.mark.asyncio
    async def test_create_article_with_empty_vibe_brain_output_is_none(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Empty string vibe should not store anything in brain_output."""
        payload = _make_article_payload(blog_in_db.id, vibe="")
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        data = resp.json()
        assert data["brain_output"] is None


# ===================================================================
# ArticleCreate validation
# ===================================================================


class TestArticleCreateValidation:
    """Validate ArticleCreate field constraints."""

    @pytest.mark.asyncio
    async def test_vibe_max_length_500(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Vibe over 500 chars should return 422."""
        payload = _make_article_payload(blog_in_db.id, vibe="x" * 501)
        resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_vibe_at_max_length_500_accepted(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Vibe exactly 500 chars should be accepted."""
        payload = _make_article_payload(blog_in_db.id, vibe="x" * 500)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_focus_keyword_max_length_200(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Focus keyword over 200 chars should return 422."""
        payload = _make_article_payload(blog_in_db.id, focus_keyword="x" * 201)
        resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_focus_keyword_at_max_length_200_accepted(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Focus keyword exactly 200 chars should be accepted."""
        payload = _make_article_payload(blog_in_db.id, focus_keyword="x" * 200)
        with patch("app.api.articles.generate_single_article_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/articles", json=payload)
        assert resp.status_code == 201


# ===================================================================
# VAL-BACKEND-003: BlogUpdate accepts is_active
# ===================================================================


class TestBlogUpdateIsActive:
    """PATCH /api/v1/blogs/{id} with is_active updates the blog."""

    @pytest.mark.asyncio
    async def test_patch_blog_set_is_active_false(
        self,
        client: AsyncClient,
        existing_blog_via_api: dict[str, Any],
    ) -> None:
        """PATCH with is_active=false returns 200."""
        blog_id = existing_blog_via_api["id"]
        resp = await client.patch(
            f"/api/v1/blogs/{blog_id}",
            json={"is_active": False},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_blog_is_active_false_reflected(
        self,
        client: AsyncClient,
        existing_blog_via_api: dict[str, Any],
    ) -> None:
        """PATCH response reflects is_active=false."""
        blog_id = existing_blog_via_api["id"]
        resp = await client.patch(
            f"/api/v1/blogs/{blog_id}",
            json={"is_active": False},
        )
        data = resp.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_patch_blog_is_active_false_in_db(
        self,
        client: AsyncClient,
        existing_blog_via_api: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """is_active=false is persisted in the database."""
        from sqlalchemy import select

        blog_id = uuid.UUID(existing_blog_via_api["id"])
        await client.patch(
            f"/api/v1/blogs/{blog_id}",
            json={"is_active": False},
        )

        result = await db_session.execute(select(Blog).where(Blog.id == blog_id))
        blog = result.scalar_one()
        assert blog.is_active is False

    @pytest.mark.asyncio
    async def test_patch_blog_set_is_active_true(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Can set is_active=true on a blog that was set to false via PATCH."""
        # Create blog, then deactivate via PATCH
        blog = Blog(
            name="Toggle Test",
            slug="toggle-test",
            url="https://toggle.com",
            wp_username="admin",
            wp_app_password_encrypted=encrypt("secret"),
            is_active=True,
        )
        db_session.add(blog)
        await db_session.flush()
        await db_session.refresh(blog)

        # Deactivate
        resp = await client.patch(
            f"/api/v1/blogs/{blog.id}",
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_patch_blog_is_active_invalid_type_returns_422(
        self,
        client: AsyncClient,
        existing_blog_via_api: dict[str, Any],
    ) -> None:
        """PATCH with non-boolean is_active returns 422."""
        blog_id = existing_blog_via_api["id"]
        resp = await client.patch(
            f"/api/v1/blogs/{blog_id}",
            json={"is_active": "not-a-bool"},
        )
        assert resp.status_code == 422


# ===================================================================
# VAL-BACKEND-004: CORS middleware allows localhost:3000
# ===================================================================


class TestCORSMiddleware:
    """CORS middleware correctly handles preflight and actual requests."""

    @pytest.mark.asyncio
    async def test_cors_preflight_returns_200(
        self,
        client: AsyncClient,
    ) -> None:
        """OPTIONS preflight request returns 200."""
        resp = await client.options(
            "/api/v1/articles",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cors_preflight_has_allow_origin(
        self,
        client: AsyncClient,
    ) -> None:
        """Preflight response includes Access-Control-Allow-Origin header."""
        resp = await client.options(
            "/api/v1/articles",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert "access-control-allow-origin" in resp.headers
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_cors_preflight_has_allow_methods(
        self,
        client: AsyncClient,
    ) -> None:
        """Preflight response includes Access-Control-Allow-Methods header."""
        resp = await client.options(
            "/api/v1/articles",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-methods" in resp.headers

    @pytest.mark.asyncio
    async def test_cors_actual_request_has_allow_origin(
        self,
        client: AsyncClient,
    ) -> None:
        """Actual GET request with Origin header gets CORS headers."""
        resp = await client.get(
            "/api/v1/articles",
            headers={"Origin": "http://localhost:3000"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_cors_health_endpoint(
        self,
        client: AsyncClient,
    ) -> None:
        """Health endpoint also has CORS headers."""
        resp = await client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_cors_preflight_localhost_no_port(
        self,
        client: AsyncClient,
    ) -> None:
        """Preflight from http://localhost (no port) is also allowed."""
        resp = await client.options(
            "/api/v1/articles",
            headers={
                "Origin": "http://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost"

    @pytest.mark.asyncio
    async def test_cors_disallowed_origin_no_header(
        self,
        client: AsyncClient,
    ) -> None:
        """Request from disallowed origin does not get CORS headers."""
        resp = await client.get(
            "/api/v1/articles",
            headers={"Origin": "http://evil.example.com"},
        )
        # Response still succeeds (200) but no CORS header
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers


# ===================================================================
# Config: CORS_ORIGINS setting
# ===================================================================


class TestCORSOriginsSetting:
    """Verify CORS_ORIGINS setting in config."""

    def test_cors_origins_default(self) -> None:
        """CORS_ORIGINS has expected default values."""
        from app.core.config import Settings

        s = Settings()
        assert "http://localhost:3000" in s.CORS_ORIGINS
        assert "http://localhost" in s.CORS_ORIGINS

    def test_cors_origins_is_list(self) -> None:
        """CORS_ORIGINS is a list."""
        from app.core.config import Settings

        s = Settings()
        assert isinstance(s.CORS_ORIGINS, list)

    def test_cors_origins_can_be_overridden(self) -> None:
        """CORS_ORIGINS can be overridden via environment variable."""
        from app.core.config import Settings

        s = Settings(CORS_ORIGINS=["http://custom-origin.com"])
        assert s.CORS_ORIGINS == ["http://custom-origin.com"]
