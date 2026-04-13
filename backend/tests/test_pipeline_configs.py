"""Tests for PipelineConfig CRUD and blog-creation auto-config.

Fulfils:
- VAL-PIPE-001: Blog creation triggers default pipeline_config insertion
- VAL-PIPE-002: GET /api/v1/blogs/{id}/pipeline-config returns blog's config
- VAL-PIPE-003: PUT /api/v1/blogs/{id}/pipeline-config updates settings
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_config import PipelineConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def blog_payload() -> dict[str, Any]:
    """Minimal valid blog creation payload."""
    return {
        "name": "Test Blog",
        "url": "https://testblog.com",
        "wp_username": "admin",
        "wp_application_password": "super-secret-password",
    }


@pytest_asyncio.fixture()
async def existing_blog(client: AsyncClient, blog_payload: dict[str, Any]) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=blog_payload)
    assert response.status_code == 201
    return dict(response.json())


# ---------------------------------------------------------------------------
# VAL-PIPE-001: Blog creation triggers default pipeline_config insertion
# ---------------------------------------------------------------------------


class TestAutoCreatePipelineConfig:
    """Creating a blog should automatically create a default pipeline config."""

    @pytest.mark.asyncio
    async def test_blog_creation_creates_pipeline_config(
        self,
        client: AsyncClient,
        blog_payload: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """After creating a blog, a PipelineConfig row should exist in the DB."""
        response = await client.post("/api/v1/blogs", json=blog_payload)
        assert response.status_code == 201
        blog_id = uuid.UUID(response.json()["id"])

        result = await db_session.execute(
            select(PipelineConfig).where(PipelineConfig.blog_id == blog_id)
        )
        config = result.scalar_one_or_none()
        assert config is not None

    @pytest.mark.asyncio
    async def test_default_pipeline_config_has_defaults(
        self,
        client: AsyncClient,
        blog_payload: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """The auto-created config should have sensible default values."""
        response = await client.post("/api/v1/blogs", json=blog_payload)
        blog_id = uuid.UUID(response.json()["id"])

        result = await db_session.execute(
            select(PipelineConfig).where(PipelineConfig.blog_id == blog_id)
        )
        config = result.scalar_one()
        assert config.articles_per_week == 5
        assert config.llm_provider == "deepseek"
        assert config.image_provider == "fal"
        assert config.content_tone == "informative"
        assert config.default_category == ""

    @pytest.mark.asyncio
    async def test_default_config_via_get_endpoint(
        self,
        client: AsyncClient,
        blog_payload: dict[str, Any],
    ) -> None:
        """GET /api/v1/blogs/{id}/pipeline-config should return the auto-created config."""
        response = await client.post("/api/v1/blogs", json=blog_payload)
        blog_id = response.json()["id"]

        config_response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        assert config_response.status_code == 200
        data = config_response.json()
        assert data["articles_per_week"] == 5
        assert data["llm_provider"] == "deepseek"
        assert data["image_provider"] == "fal"
        assert data["content_tone"] == "informative"


# ---------------------------------------------------------------------------
# VAL-PIPE-002: GET /api/v1/blogs/{id}/pipeline-config returns blog's config
# ---------------------------------------------------------------------------


class TestGetPipelineConfig:
    """GET /api/v1/blogs/{id}/pipeline-config returns the blog's pipeline config."""

    @pytest.mark.asyncio
    async def test_get_pipeline_config_returns_200(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pipeline_config_contains_blog_id(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()
        assert data["blog_id"] == blog_id

    @pytest.mark.asyncio
    async def test_get_pipeline_config_contains_all_fields(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()
        expected_fields = {
            "id",
            "blog_id",
            "articles_per_week",
            "llm_provider",
            "image_provider",
            "content_tone",
            "default_category",
            "created_at",
            "updated_at",
        }
        assert expected_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_get_pipeline_config_nonexistent_blog_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get(
            "/api/v1/blogs/00000000-0000-0000-0000-000000000000/pipeline-config"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# VAL-PIPE-003: PUT /api/v1/blogs/{id}/pipeline-config updates settings
# ---------------------------------------------------------------------------


class TestUpdatePipelineConfig:
    """PUT /api/v1/blogs/{id}/pipeline-config updates pipeline settings."""

    @pytest.mark.asyncio
    async def test_update_pipeline_config_returns_200(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 10},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_articles_per_week(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 10},
        )
        data = response.json()
        assert data["articles_per_week"] == 10

    @pytest.mark.asyncio
    async def test_update_llm_provider(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"llm_provider": "openai"},
        )
        data = response.json()
        assert data["llm_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_update_image_provider(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"image_provider": "openai"},
        )
        data = response.json()
        assert data["image_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_update_content_tone(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"content_tone": "casual"},
        )
        data = response.json()
        assert data["content_tone"] == "casual"

    @pytest.mark.asyncio
    async def test_update_default_category(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"default_category": "home-decor"},
        )
        data = response.json()
        assert data["default_category"] == "home-decor"

    @pytest.mark.asyncio
    async def test_update_multiple_fields_at_once(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={
                "articles_per_week": 3,
                "llm_provider": "openai",
                "content_tone": "professional",
                "default_category": "diy",
            },
        )
        data = response.json()
        assert data["articles_per_week"] == 3
        assert data["llm_provider"] == "openai"
        assert data["content_tone"] == "professional"
        assert data["default_category"] == "diy"

    @pytest.mark.asyncio
    async def test_update_persists_in_db(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """Updated values should be persisted in the database."""
        blog_id = uuid.UUID(existing_blog["id"])
        await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 7, "content_tone": "witty"},
        )

        result = await db_session.execute(
            select(PipelineConfig).where(PipelineConfig.blog_id == blog_id)
        )
        config = result.scalar_one()
        assert config.articles_per_week == 7
        assert config.content_tone == "witty"

    @pytest.mark.asyncio
    async def test_update_pipeline_config_nonexistent_blog_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.put(
            "/api/v1/blogs/00000000-0000-0000-0000-000000000000/pipeline-config",
            json={"articles_per_week": 10},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_pipeline_config_invalid_articles_per_week_returns_422(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """articles_per_week must be >= 1."""
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 0},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_pipeline_config_empty_provider_returns_422(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """llm_provider must not be empty."""
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"llm_provider": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_pipeline_config_updates_timestamp(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """updated_at should change after an update."""
        import asyncio

        blog_id = existing_blog["id"]

        get_response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        original_updated_at = get_response.json()["updated_at"]

        await asyncio.sleep(0.05)

        update_response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 7},
        )
        data = update_response.json()
        assert data["updated_at"] != original_updated_at

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """Updating one field should not change other fields."""
        blog_id = existing_blog["id"]

        # Update just one field
        await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"articles_per_week": 3},
        )

        # Verify other fields are unchanged
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()
        assert data["articles_per_week"] == 3
        assert data["llm_provider"] == "deepseek"  # unchanged
        assert data["image_provider"] == "fal"  # unchanged
        assert data["content_tone"] == "informative"  # unchanged
