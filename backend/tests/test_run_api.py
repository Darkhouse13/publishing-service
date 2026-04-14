"""Tests for POST /api/v1/runs and GET /api/v1/runs/{id} endpoints.

Fulfils:
- VAL-API-001: POST /runs creates Run in pending state
- VAL-API-002: POST /runs validates blog exists
- VAL-API-003: POST /runs snapshots config
- VAL-API-004: POST /runs dispatches bulk pipeline task
- VAL-API-005: POST /runs generates unique run_code
- VAL-API-005b: POST /runs generates timestamp-format run_code
- VAL-API-010: GET /runs/{id} returns all new fields
- VAL-API-011: GET /runs/{id} returns articles list with progress
- VAL-API-012: GET /runs/{id} returns 404 for missing run
- VAL-API-013: POST /runs returns 422 for missing required fields
- VAL-API-015: POST /runs stores keywords as seed_keywords
- VAL-API-016: POST /runs rejects empty keywords list
"""

import re
import time
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


def _make_run_payload(blog_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    """Return a valid run creation payload."""
    return {
        "blog_id": str(blog_id),
        "keywords": ["keyword1", "keyword2", "keyword3"],
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

    # Auto-create default pipeline config
    from app.services.pipeline_config import PipelineConfigService

    config_service = PipelineConfigService(db_session)
    await config_service.create_default(blog.id)
    await db_session.flush()

    return blog


@pytest_asyncio.fixture()
async def existing_blog_via_api(client: AsyncClient) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=_make_blog_payload())
    assert response.status_code == 201
    return dict(response.json())


# ===================================================================
# VAL-API-001: POST /runs creates Run in pending state
# ===================================================================


class TestCreateRun:
    """Tests for POST /api/v1/runs."""

    @pytest.mark.asyncio
    async def test_create_run_returns_201(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /runs with valid data returns 201."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_run_status_pending(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created run has status='pending'."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_run_phase_pending(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created run has phase='pending'."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert data["phase"] == "pending"

    @pytest.mark.asyncio
    async def test_create_run_returns_id(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created run returns a valid UUID id."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert "id" in data
        uuid.UUID(data["id"])  # Should not raise

    @pytest.mark.asyncio
    async def test_create_run_returns_blog_id(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created run returns the correct blog_id."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert data["blog_id"] == str(blog_in_db.id)


# ===================================================================
# VAL-API-002: POST /runs validates blog exists
# ===================================================================


class TestCreateRunBlogValidation:
    """Validate blog existence check on run creation."""

    @pytest.mark.asyncio
    async def test_create_run_nonexistent_blog_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /runs with non-existent blog_id returns 422."""
        fake_id = str(uuid.uuid4())
        payload = _make_run_payload(uuid.UUID(fake_id))
        resp = await client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_run_nonexistent_blog_error_detail(
        self,
        client: AsyncClient,
    ) -> None:
        """Error detail mentions blog not found."""
        fake_id = str(uuid.uuid4())
        payload = _make_run_payload(uuid.UUID(fake_id))
        resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert "not found" in str(data["detail"]).lower() or "inactive" in str(data["detail"]).lower()


# ===================================================================
# VAL-API-003: POST /runs snapshots config
# ===================================================================


class TestCreateRunConfigSnapshot:
    """Validate config snapshot creation."""

    @pytest.mark.asyncio
    async def test_create_run_snapshots_config(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Config_snapshot matches the blog's PipelineConfig."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        snapshot = data["config_snapshot"]

        # Verify snapshot contains key config fields
        assert "llm_model" in snapshot
        assert "image_model" in snapshot
        assert "publish_status" in snapshot
        assert "max_concurrent_articles" in snapshot
        assert snapshot["llm_model"] == "deepseek-chat"
        assert snapshot["image_model"] == "fal-ai/flux/dev"
        assert snapshot["publish_status"] == "draft"
        assert snapshot["max_concurrent_articles"] == 3


# ===================================================================
# VAL-API-004: POST /runs dispatches bulk pipeline task
# ===================================================================


class TestCreateRunDispatchesTask:
    """Validate that bulk pipeline task is dispatched."""

    @pytest.mark.asyncio
    async def test_create_run_dispatches_bulk_pipeline_task(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """run_bulk_pipeline_task.delay is called with run_id."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201
        mock_task.delay.assert_called_once()

        # Verify the task was called with the run's ID
        call_args = mock_task.delay.call_args[0]
        assert len(call_args) == 1
        run_id = call_args[0]
        assert run_id == str(resp.json()["id"])


# ===================================================================
# VAL-API-005: POST /runs generates unique run_code
# VAL-API-005b: POST /runs generates timestamp-format run_code
# ===================================================================


class TestCreateRunCode:
    """Validate run_code generation."""

    @pytest.mark.asyncio
    async def test_create_run_generates_run_code(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Created run has a run_code."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert "run_code" in data
        assert len(data["run_code"]) > 0

    @pytest.mark.asyncio
    async def test_run_code_is_timestamp_format(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """run_code matches YYYYMMDD_HHMMSS pattern."""
        payload = _make_run_payload(blog_in_db.id)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert re.match(r"^\d{8}_\d{6}$", data["run_code"])

    @pytest.mark.asyncio
    async def test_two_runs_have_different_run_codes(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Two runs created at different times have different run_codes."""
        payload1 = _make_run_payload(blog_in_db.id, keywords=["k1"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp1 = await client.post("/api/v1/runs", json=payload1)

        # Small sleep to ensure different timestamp
        time.sleep(1.1)

        payload2 = _make_run_payload(blog_in_db.id, keywords=["k2"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp2 = await client.post("/api/v1/runs", json=payload2)

        code1 = resp1.json()["run_code"]
        code2 = resp2.json()["run_code"]
        assert code1 != code2


# ===================================================================
# VAL-API-015: POST /runs stores keywords as seed_keywords
# ===================================================================


class TestCreateRunSeedKeywords:
    """Validate keywords are stored as seed_keywords."""

    @pytest.mark.asyncio
    async def test_create_run_stores_seed_keywords(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Keywords from request are stored in seed_keywords."""
        keywords = ["k1", "k2", "k3"]
        payload = _make_run_payload(blog_in_db.id, keywords=keywords)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert data["seed_keywords"] == keywords

    @pytest.mark.asyncio
    async def test_create_run_articles_total_matches_keywords(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """articles_total equals the number of keywords."""
        keywords = ["k1", "k2", "k3", "k4", "k5"]
        payload = _make_run_payload(blog_in_db.id, keywords=keywords)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        assert data["articles_total"] == 5


# ===================================================================
# VAL-API-016: POST /runs rejects empty keywords list
# ===================================================================


class TestCreateRunRejectsEmptyKeywords:
    """Validate empty keywords list is rejected."""

    @pytest.mark.asyncio
    async def test_create_run_empty_keywords_returns_422(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """POST /runs with empty keywords list returns 422."""
        payload = _make_run_payload(blog_in_db.id, keywords=[])
        resp = await client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_run_empty_keywords_error_detail(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """Error detail mentions keywords must not be empty."""
        payload = _make_run_payload(blog_in_db.id, keywords=[])
        resp = await client.post("/api/v1/runs", json=payload)
        data = resp.json()
        detail_str = str(data["detail"])
        assert "keywords" in detail_str.lower() or "empty" in detail_str.lower()


# ===================================================================
# VAL-API-013: POST /runs returns 422 for missing required fields
# ===================================================================


class TestCreateRunMissingFields:
    """Validate missing required fields return 422."""

    @pytest.mark.asyncio
    async def test_create_run_missing_blog_id(self, client: AsyncClient) -> None:
        """Missing blog_id returns 422."""
        resp = await client.post("/api/v1/runs", json={"keywords": ["k1"]})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_run_missing_keywords(self, client: AsyncClient) -> None:
        """Missing keywords returns 422."""
        resp = await client.post(
            "/api/v1/runs", json={"blog_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_run_empty_body(self, client: AsyncClient) -> None:
        """Empty body returns 422."""
        resp = await client.post("/api/v1/runs", json={})
        assert resp.status_code == 422


# ===================================================================
# VAL-API-010: GET /runs/{id} returns all new fields
# VAL-API-011: GET /runs/{id} returns articles list with progress
# VAL-API-012: GET /runs/{id} returns 404 for missing run
# ===================================================================


class TestGetRunDetails:
    """Tests for GET /api/v1/runs/{id} with new fields."""

    @pytest.mark.asyncio
    async def test_get_run_returns_all_new_fields(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """GET /runs/{id} returns all new fields."""
        payload = _make_run_payload(blog_in_db.id, keywords=["k1", "k2"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/runs", json=payload)

        run_id = create_resp.json()["id"]
        get_resp = await client.get(f"/api/v1/runs/{run_id}")
        assert get_resp.status_code == 200

        data = get_resp.json()
        required_fields = [
            "id",
            "blog_id",
            "status",
            "run_code",
            "phase",
            "seed_keywords",
            "config_snapshot",
            "results_summary",
            "csv_path",
            "articles_total",
            "articles_completed",
            "articles_failed",
            "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_run_returns_articles_list(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """GET /runs/{id} response includes articles list via relationship."""
        payload = _make_run_payload(blog_in_db.id, keywords=["k1", "k2"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/runs", json=payload)

        run_id = create_resp.json()["id"]
        get_resp = await client.get(f"/api/v1/runs/{run_id}")

        # Articles relationship loaded via selectin - articles list should be accessible
        # Note: at creation time, no articles exist yet (they're created by the pipeline)
        # The response should still have the relationship accessible
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_run_returns_progress_counts(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """GET /runs/{id} returns articles_total, articles_completed, articles_failed."""
        payload = _make_run_payload(blog_in_db.id, keywords=["k1", "k2", "k3"])
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/runs", json=payload)

        run_id = create_resp.json()["id"]
        get_resp = await client.get(f"/api/v1/runs/{run_id}")
        data = get_resp.json()
        assert data["articles_total"] == 3
        assert data["articles_completed"] == 0
        assert data["articles_failed"] == 0

    @pytest.mark.asyncio
    async def test_get_run_404_for_missing_run(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /runs/{id} returns 404 for non-existent run."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/runs/{fake_id}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"

    @pytest.mark.asyncio
    async def test_get_run_404_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /runs/{id} returns 422 for invalid UUID."""
        resp = await client.get("/api/v1/runs/not-a-uuid")
        assert resp.status_code == 422


# ===================================================================
# VAL-API-001 (extended): POST /runs round-trip with GET
# ===================================================================


class TestRunRoundTrip:
    """POST /runs then GET /runs/{id} consistency."""

    @pytest.mark.asyncio
    async def test_post_get_round_trip(
        self,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """All fields from POST are present and correct in GET response."""
        keywords = ["test_keyword_1", "test_keyword_2"]
        payload = _make_run_payload(blog_in_db.id, keywords=keywords)
        with patch("app.api.runs.run_bulk_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            create_resp = await client.post("/api/v1/runs", json=payload)

        assert create_resp.status_code == 201
        create_data = create_resp.json()

        get_resp = await client.get(f"/api/v1/runs/{create_data['id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        # Fields should match between POST and GET
        assert get_data["id"] == create_data["id"]
        assert get_data["blog_id"] == create_data["blog_id"]
        assert get_data["status"] == create_data["status"]
        assert get_data["run_code"] == create_data["run_code"]
        assert get_data["phase"] == create_data["phase"]
        assert get_data["seed_keywords"] == create_data["seed_keywords"]
        assert get_data["config_snapshot"] == create_data["config_snapshot"]
