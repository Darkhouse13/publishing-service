"""Tests for PipelineConfig CRUD and blog-creation auto-config.

Fulfils:
- VAL-PCFG-001: PipelineConfig model removes deprecated columns
- VAL-PCFG-002: PipelineConfig model adds new columns with correct defaults
- VAL-PCFG-003: PipelineConfig API GET returns new fields
- VAL-PCFG-004: PipelineConfig API PUT updates new fields
- VAL-PCFG-005: PipelineConfig API PUT partial update preserves defaults
- VAL-PCFG-006: PipelineConfig schema rejects invalid types
- VAL-PCFG-007: PipelineConfig schema response includes all new fields
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
        assert config.llm_provider == "deepseek"
        assert config.image_provider == "fal"
        assert config.llm_model == "deepseek-chat"
        assert config.image_model == "fal-ai/flux/dev"
        assert config.trends_region == "GLOBAL"
        assert config.trends_range == "12m"
        assert config.trends_top_n == 20
        assert config.pinclicks_max_records == 25
        assert config.winners_count == 5
        assert config.publish_status == "draft"
        assert config.csv_cadence_minutes == 240
        assert config.pin_template_mode == "center_strip"
        assert config.max_concurrent_articles == 3

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
        assert data["llm_provider"] == "deepseek"
        assert data["image_provider"] == "fal"
        assert data["llm_model"] == "deepseek-chat"
        assert data["trends_region"] == "GLOBAL"


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
            "llm_provider",
            "image_provider",
            "llm_model",
            "image_model",
            "trends_region",
            "trends_range",
            "trends_top_n",
            "pinclicks_max_records",
            "winners_count",
            "publish_status",
            "csv_cadence_minutes",
            "pin_template_mode",
            "max_concurrent_articles",
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
            json={"llm_model": "gpt-4o"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_llm_model(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"llm_model": "gpt-4o"},
        )
        data = response.json()
        assert data["llm_model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_update_image_model(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"image_model": "dall-e-3"},
        )
        data = response.json()
        assert data["image_model"] == "dall-e-3"

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
    async def test_update_trends_region(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_region": "US"},
        )
        data = response.json()
        assert data["trends_region"] == "US"

    @pytest.mark.asyncio
    async def test_update_trends_range(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_range": "3m"},
        )
        data = response.json()
        assert data["trends_range"] == "3m"

    @pytest.mark.asyncio
    async def test_update_trends_top_n(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_top_n": 50},
        )
        data = response.json()
        assert data["trends_top_n"] == 50

    @pytest.mark.asyncio
    async def test_update_pinclicks_max_records(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"pinclicks_max_records": 100},
        )
        data = response.json()
        assert data["pinclicks_max_records"] == 100

    @pytest.mark.asyncio
    async def test_update_winners_count(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"winners_count": 10},
        )
        data = response.json()
        assert data["winners_count"] == 10

    @pytest.mark.asyncio
    async def test_update_publish_status(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"publish_status": "publish"},
        )
        data = response.json()
        assert data["publish_status"] == "publish"

    @pytest.mark.asyncio
    async def test_update_csv_cadence_minutes(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"csv_cadence_minutes": 120},
        )
        data = response.json()
        assert data["csv_cadence_minutes"] == 120

    @pytest.mark.asyncio
    async def test_update_pin_template_mode(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"pin_template_mode": "full_bleed"},
        )
        data = response.json()
        assert data["pin_template_mode"] == "full_bleed"

    @pytest.mark.asyncio
    async def test_update_max_concurrent_articles(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"max_concurrent_articles": 5},
        )
        data = response.json()
        assert data["max_concurrent_articles"] == 5

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
                "llm_model": "gpt-4o",
                "max_concurrent_articles": 5,
                "trends_region": "US",
                "publish_status": "publish",
            },
        )
        data = response.json()
        assert data["llm_model"] == "gpt-4o"
        assert data["max_concurrent_articles"] == 5
        assert data["trends_region"] == "US"
        assert data["publish_status"] == "publish"

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
            json={"llm_model": "gpt-4o", "winners_count": 8},
        )

        result = await db_session.execute(
            select(PipelineConfig).where(PipelineConfig.blog_id == blog_id)
        )
        config = result.scalar_one()
        assert config.llm_model == "gpt-4o"
        assert config.winners_count == 8

    @pytest.mark.asyncio
    async def test_update_pipeline_config_nonexistent_blog_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.put(
            "/api/v1/blogs/00000000-0000-0000-0000-000000000000/pipeline-config",
            json={"llm_model": "gpt-4o"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_pipeline_config_invalid_trends_top_n_returns_422(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """trends_top_n must be an integer."""
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_top_n": "not_an_int"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_pipeline_config_invalid_trends_top_n_zero_returns_422(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        """trends_top_n must be >= 1."""
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_top_n": 0},
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
            json={"llm_model": "gpt-4o"},
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
            json={"trends_region": "US"},
        )

        # Verify other fields are unchanged
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()
        assert data["trends_region"] == "US"
        assert data["llm_provider"] == "deepseek"  # unchanged
        assert data["image_provider"] == "fal"  # unchanged
        assert data["llm_model"] == "deepseek-chat"  # unchanged
        assert data["image_model"] == "fal-ai/flux/dev"  # unchanged
        assert data["trends_range"] == "12m"  # unchanged
        assert data["trends_top_n"] == 20  # unchanged
        assert data["pinclicks_max_records"] == 25  # unchanged
        assert data["winners_count"] == 5  # unchanged
        assert data["publish_status"] == "draft"  # unchanged
        assert data["csv_cadence_minutes"] == 240  # unchanged
        assert data["pin_template_mode"] == "center_strip"  # unchanged
        assert data["max_concurrent_articles"] == 3  # unchanged


# ---------------------------------------------------------------------------
# VAL-PCFG-001: PipelineConfig model removes deprecated columns
# ---------------------------------------------------------------------------


class TestDeprecatedColumnsRemoved:
    """Verify that deprecated columns no longer exist on the model."""

    @pytest.mark.asyncio
    async def test_articles_per_week_column_removed(self) -> None:
        """articles_per_week should not exist on PipelineConfig."""
        assert "articles_per_week" not in PipelineConfig.__table__.columns

    @pytest.mark.asyncio
    async def test_content_tone_column_removed(self) -> None:
        """content_tone should not exist on PipelineConfig."""
        assert "content_tone" not in PipelineConfig.__table__.columns

    @pytest.mark.asyncio
    async def test_default_category_column_removed(self) -> None:
        """default_category should not exist on PipelineConfig."""
        assert "default_category" not in PipelineConfig.__table__.columns


# ---------------------------------------------------------------------------
# VAL-PCFG-002: PipelineConfig model adds new columns with correct defaults
# ---------------------------------------------------------------------------


class TestNewColumnsWithDefaults:
    """Verify all 11 new columns exist with correct types and defaults."""

    @pytest.mark.asyncio
    async def test_llm_model_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["llm_model"]
        assert col is not None
        assert col.default.arg == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_image_model_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["image_model"]
        assert col is not None
        assert col.default.arg == "fal-ai/flux/dev"

    @pytest.mark.asyncio
    async def test_trends_region_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["trends_region"]
        assert col is not None
        assert col.default.arg == "GLOBAL"

    @pytest.mark.asyncio
    async def test_trends_range_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["trends_range"]
        assert col is not None
        assert col.default.arg == "12m"

    @pytest.mark.asyncio
    async def test_trends_top_n_column_exists_with_default(self) -> None:
        from sqlalchemy import Integer as SaInteger

        col = PipelineConfig.__table__.columns["trends_top_n"]
        assert col is not None
        assert isinstance(col.type, SaInteger)
        assert col.default.arg == 20

    @pytest.mark.asyncio
    async def test_pinclicks_max_records_column_exists_with_default(self) -> None:
        from sqlalchemy import Integer as SaInteger

        col = PipelineConfig.__table__.columns["pinclicks_max_records"]
        assert col is not None
        assert isinstance(col.type, SaInteger)
        assert col.default.arg == 25

    @pytest.mark.asyncio
    async def test_winners_count_column_exists_with_default(self) -> None:
        from sqlalchemy import Integer as SaInteger

        col = PipelineConfig.__table__.columns["winners_count"]
        assert col is not None
        assert isinstance(col.type, SaInteger)
        assert col.default.arg == 5

    @pytest.mark.asyncio
    async def test_publish_status_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["publish_status"]
        assert col is not None
        assert col.default.arg == "draft"

    @pytest.mark.asyncio
    async def test_csv_cadence_minutes_column_exists_with_default(self) -> None:
        from sqlalchemy import Integer as SaInteger

        col = PipelineConfig.__table__.columns["csv_cadence_minutes"]
        assert col is not None
        assert isinstance(col.type, SaInteger)
        assert col.default.arg == 240

    @pytest.mark.asyncio
    async def test_pin_template_mode_column_exists_with_default(self) -> None:
        col = PipelineConfig.__table__.columns["pin_template_mode"]
        assert col is not None
        assert col.default.arg == "center_strip"

    @pytest.mark.asyncio
    async def test_max_concurrent_articles_column_exists_with_default(self) -> None:
        from sqlalchemy import Integer as SaInteger

        col = PipelineConfig.__table__.columns["max_concurrent_articles"]
        assert col is not None
        assert isinstance(col.type, SaInteger)
        assert col.default.arg == 3


# ---------------------------------------------------------------------------
# VAL-PCFG-003: PipelineConfig API GET returns new fields (with defaults)
# ---------------------------------------------------------------------------


class TestGetReturnsNewFields:
    """GET endpoint returns all 11 new fields with default values."""

    @pytest.mark.asyncio
    async def test_get_returns_all_new_fields_with_defaults(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()

        assert data["llm_model"] == "deepseek-chat"
        assert data["image_model"] == "fal-ai/flux/dev"
        assert data["trends_region"] == "GLOBAL"
        assert data["trends_range"] == "12m"
        assert data["trends_top_n"] == 20
        assert data["pinclicks_max_records"] == 25
        assert data["winners_count"] == 5
        assert data["publish_status"] == "draft"
        assert data["csv_cadence_minutes"] == 240
        assert data["pin_template_mode"] == "center_strip"
        assert data["max_concurrent_articles"] == 3


# ---------------------------------------------------------------------------
# VAL-PCFG-004: PipelineConfig API PUT updates new fields
# ---------------------------------------------------------------------------


class TestPutUpdatesNewFields:
    """PUT endpoint can update new fields."""

    @pytest.mark.asyncio
    async def test_put_updates_llm_model_and_max_concurrent(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"llm_model": "gpt-4o", "max_concurrent_articles": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["llm_model"] == "gpt-4o"
        assert data["max_concurrent_articles"] == 5
        # Other fields should remain at defaults
        assert data["trends_region"] == "GLOBAL"


# ---------------------------------------------------------------------------
# VAL-PCFG-005: PipelineConfig API PUT partial update preserves defaults
# ---------------------------------------------------------------------------


class TestPartialUpdatePreservesDefaults:
    """Updating only one field leaves all other new fields at defaults."""

    @pytest.mark.asyncio
    async def test_partial_update_preserves_defaults(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_region": "US"},
        )
        assert response.status_code == 200
        data = response.json()

        # Only trends_region changed
        assert data["trends_region"] == "US"
        # All other new fields should be at their defaults
        assert data["llm_model"] == "deepseek-chat"
        assert data["image_model"] == "fal-ai/flux/dev"
        assert data["trends_range"] == "12m"
        assert data["trends_top_n"] == 20
        assert data["pinclicks_max_records"] == 25
        assert data["winners_count"] == 5
        assert data["publish_status"] == "draft"
        assert data["csv_cadence_minutes"] == 240
        assert data["pin_template_mode"] == "center_strip"
        assert data["max_concurrent_articles"] == 3


# ---------------------------------------------------------------------------
# VAL-PCFG-006: PipelineConfig schema rejects invalid types
# ---------------------------------------------------------------------------


class TestSchemaRejectsInvalidTypes:
    """Schema rejects invalid types with 422."""

    @pytest.mark.asyncio
    async def test_reject_string_for_trends_top_n(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"trends_top_n": "not_an_int"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_string_for_winners_count(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"winners_count": "not_an_int"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_string_for_csv_cadence_minutes(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"csv_cadence_minutes": "not_an_int"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_string_for_max_concurrent_articles(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.put(
            f"/api/v1/blogs/{blog_id}/pipeline-config",
            json={"max_concurrent_articles": "not_an_int"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# VAL-PCFG-007: PipelineConfig schema response includes all new fields
# ---------------------------------------------------------------------------


class TestResponseIncludesAllFields:
    """PipelineConfigResponse serialises all new fields."""

    @pytest.mark.asyncio
    async def test_response_model_dump_contains_all_keys(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
    ) -> None:
        blog_id = existing_blog["id"]
        response = await client.get(f"/api/v1/blogs/{blog_id}/pipeline-config")
        data = response.json()

        new_fields = [
            "llm_model",
            "image_model",
            "trends_region",
            "trends_range",
            "trends_top_n",
            "pinclicks_max_records",
            "winners_count",
            "publish_status",
            "csv_cadence_minutes",
            "pin_template_mode",
            "max_concurrent_articles",
        ]
        for field in new_fields:
            assert field in data, f"Field '{field}' missing from response"
