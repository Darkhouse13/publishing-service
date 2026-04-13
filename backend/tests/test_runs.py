"""Tests for Run model, schema, service, and API endpoints.

Fulfils:
- VAL-RUN-001: Run model adds run_code column
- VAL-RUN-002: Run model adds phase column with default
- VAL-RUN-003: Run model adds seed_keywords column
- VAL-RUN-004: Run model adds config_snapshot column
- VAL-RUN-005: Run model adds results_summary column
- VAL-RUN-006: Run model adds csv_path column
- VAL-RUN-007: Run run_code uniqueness is enforced
- VAL-RUN-008: Run API GET returns new fields
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import Blog
from app.models.run import Run
from app.crypto import encrypt


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


# ---------------------------------------------------------------------------
# Async fixtures
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
async def run_in_db(
    db_session: AsyncSession,
    blog_in_db: Blog,
) -> Run:
    """Create and persist a Run linked to ``blog_in_db``."""
    run = Run(blog_id=blog_in_db.id, run_code="TESTRUN001")
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    return run


@pytest_asyncio.fixture()
async def existing_blog_via_api(client: AsyncClient) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=_make_blog_payload())
    assert response.status_code == 201
    return dict(response.json())


# ===================================================================
# VAL-RUN-001: Run model adds run_code column
# ===================================================================


class TestRunRunCodeColumn:
    """Validate the run_code column definition."""

    async def test_run_code_column_exists(self) -> None:
        """run_code column should exist on the Run model."""
        assert "run_code" in Run.__table__.columns

    async def test_run_code_column_type(self) -> None:
        """run_code should be String(50)."""
        col = Run.__table__.columns["run_code"]
        assert str(col.type) == "VARCHAR(50)"

    async def test_run_code_not_nullable(self) -> None:
        """run_code should be NOT NULL."""
        col = Run.__table__.columns["run_code"]
        assert col.nullable is False

    async def test_run_code_unique(self) -> None:
        """run_code should be UNIQUE."""
        col = Run.__table__.columns["run_code"]
        assert col.unique is True

    async def test_run_code_stored_and_retrieved(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """run_code persists and reads back correctly."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_ABC123")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.run_code == "RUN_ABC123"


# ===================================================================
# VAL-RUN-002: Run model adds phase column with default
# ===================================================================


class TestRunPhaseColumn:
    """Validate the phase column definition and default."""

    async def test_phase_column_exists(self) -> None:
        """phase column should exist on the Run model."""
        assert "phase" in Run.__table__.columns

    async def test_phase_column_type(self) -> None:
        """phase should be String(30)."""
        col = Run.__table__.columns["phase"]
        assert str(col.type) == "VARCHAR(30)"

    async def test_phase_not_nullable(self) -> None:
        """phase should be NOT NULL."""
        col = Run.__table__.columns["phase"]
        assert col.nullable is False

    async def test_phase_defaults_to_pending(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """New Run instances should have phase='pending'."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_PHASE")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.phase == "pending"

    async def test_phase_can_be_updated(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """phase can be set to other values."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_PHASE2", phase="generating")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.phase == "generating"


# ===================================================================
# VAL-RUN-003: Run model adds seed_keywords column
# ===================================================================


class TestRunSeedKeywordsColumn:
    """Validate the seed_keywords column definition."""

    async def test_seed_keywords_column_exists(self) -> None:
        """seed_keywords column should exist on the Run model."""
        assert "seed_keywords" in Run.__table__.columns

    async def test_seed_keywords_column_type_is_json(self) -> None:
        """seed_keywords should be JSON type."""
        from sqlalchemy import JSON

        col = Run.__table__.columns["seed_keywords"]
        assert isinstance(col.type, JSON)

    async def test_seed_keywords_not_nullable(self) -> None:
        """seed_keywords should be NOT NULL."""
        col = Run.__table__.columns["seed_keywords"]
        assert col.nullable is False

    async def test_seed_keywords_default_empty_list(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default seed_keywords should be an empty list."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_KW_DEF")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.seed_keywords == []

    async def test_seed_keywords_stores_list_of_strings(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """seed_keywords stores and retrieves a list of strings."""
        run = Run(
            blog_id=blog_in_db.id,
            run_code="RUN_KW_STR",
            seed_keywords=["kw1", "kw2", "kw3"],
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.seed_keywords == ["kw1", "kw2", "kw3"]


# ===================================================================
# VAL-RUN-004: Run model adds config_snapshot column
# ===================================================================


class TestRunConfigSnapshotColumn:
    """Validate the config_snapshot column definition."""

    async def test_config_snapshot_column_exists(self) -> None:
        """config_snapshot column should exist on the Run model."""
        assert "config_snapshot" in Run.__table__.columns

    async def test_config_snapshot_column_type_is_json(self) -> None:
        """config_snapshot should be JSON type."""
        from sqlalchemy import JSON

        col = Run.__table__.columns["config_snapshot"]
        assert isinstance(col.type, JSON)

    async def test_config_snapshot_not_nullable(self) -> None:
        """config_snapshot should be NOT NULL."""
        col = Run.__table__.columns["config_snapshot"]
        assert col.nullable is False

    async def test_config_snapshot_default_empty_dict(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default config_snapshot should be an empty dict."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_CFG_DEF")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.config_snapshot == {}

    async def test_config_snapshot_stores_nested_dict(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """config_snapshot stores and retrieves a nested dict."""
        config = {
            "llm_model": "deepseek-chat",
            "image_model": "fal-ai/flux/dev",
            "nested": {"key": "value", "inner": [1, 2, 3]},
        }
        run = Run(
            blog_id=blog_in_db.id,
            run_code="RUN_CFG_STR",
            config_snapshot=config,
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.config_snapshot == config
        assert run.config_snapshot["nested"]["inner"] == [1, 2, 3]


# ===================================================================
# VAL-RUN-005: Run model adds results_summary column
# ===================================================================


class TestRunResultsSummaryColumn:
    """Validate the results_summary column definition."""

    async def test_results_summary_column_exists(self) -> None:
        """results_summary column should exist on the Run model."""
        assert "results_summary" in Run.__table__.columns

    async def test_results_summary_column_type_is_json(self) -> None:
        """results_summary should be JSON type."""
        from sqlalchemy import JSON

        col = Run.__table__.columns["results_summary"]
        assert isinstance(col.type, JSON)

    async def test_results_summary_not_nullable(self) -> None:
        """results_summary should be NOT NULL."""
        col = Run.__table__.columns["results_summary"]
        assert col.nullable is False

    async def test_results_summary_default_empty_dict(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default results_summary should be an empty dict."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_RES_DEF")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.results_summary == {}

    async def test_results_summary_stores_nested_dict(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """results_summary stores and retrieves a complex nested dict."""
        summary = {
            "total": 5,
            "completed": 3,
            "failed": 2,
            "keywords": [
                {"keyword": "k1", "status": "published"},
                {"keyword": "k2", "status": "failed", "error": "timeout"},
            ],
        }
        run = Run(
            blog_id=blog_in_db.id,
            run_code="RUN_RES_STR",
            results_summary=summary,
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.results_summary == summary
        assert run.results_summary["keywords"][1]["error"] == "timeout"


# ===================================================================
# VAL-RUN-006: Run model adds csv_path column
# ===================================================================


class TestRunCsvPathColumn:
    """Validate the csv_path column definition."""

    async def test_csv_path_column_exists(self) -> None:
        """csv_path column should exist on the Run model."""
        assert "csv_path" in Run.__table__.columns

    async def test_csv_path_column_type(self) -> None:
        """csv_path should be String(1000)."""
        col = Run.__table__.columns["csv_path"]
        assert str(col.type) == "VARCHAR(1000)"

    async def test_csv_path_nullable(self) -> None:
        """csv_path should be nullable."""
        col = Run.__table__.columns["csv_path"]
        assert col.nullable is True

    async def test_csv_path_defaults_to_none(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default csv_path should be None."""
        run = Run(blog_id=blog_in_db.id, run_code="RUN_CSV_DEF")
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.csv_path is None

    async def test_csv_path_stores_path(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """csv_path stores and retrieves a file path."""
        path = "/tmp/runs/output_20260413.csv"
        run = Run(
            blog_id=blog_in_db.id,
            run_code="RUN_CSV_STR",
            csv_path=path,
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.refresh(run)
        assert run.csv_path == path


# ===================================================================
# VAL-RUN-007: Run run_code uniqueness is enforced
# ===================================================================


class TestRunCodeUniqueness:
    """Validate that run_code uniqueness is enforced at DB level."""

    async def test_duplicate_run_code_raises_integrity_error(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Inserting two Runs with the same run_code raises IntegrityError."""
        run1 = Run(blog_id=blog_in_db.id, run_code="DUP_CODE")
        db_session.add(run1)
        await db_session.flush()

        run2 = Run(blog_id=blog_in_db.id, run_code="DUP_CODE")
        db_session.add(run2)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_different_run_codes_succeed(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Two runs with different run_codes should both persist."""
        run1 = Run(blog_id=blog_in_db.id, run_code="CODE_A")
        run2 = Run(blog_id=blog_in_db.id, run_code="CODE_B")
        db_session.add(run1)
        db_session.add(run2)
        await db_session.flush()
        assert run1.run_code == "CODE_A"
        assert run2.run_code == "CODE_B"


# ===================================================================
# VAL-RUN-008: Run API GET returns new fields
# ===================================================================


class TestRunAPIGetNewFields:
    """Validate GET /api/v1/runs/{id} returns all new fields."""

    async def test_get_run_returns_run_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes run_code."""
        run = Run(blog_id=blog_in_db.id, run_code="API_CODE_001")
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_code"] == "API_CODE_001"

    async def test_get_run_returns_phase(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes phase."""
        run = Run(blog_id=blog_in_db.id, run_code="API_PHASE", phase="generating")
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "generating"

    async def test_get_run_returns_seed_keywords(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes seed_keywords."""
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_KW",
            seed_keywords=["keyword1", "keyword2"],
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["seed_keywords"] == ["keyword1", "keyword2"]

    async def test_get_run_returns_config_snapshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes config_snapshot."""
        config = {"llm_model": "deepseek-chat", "max_retries": 3}
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_CFG",
            config_snapshot=config,
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_snapshot"] == config

    async def test_get_run_returns_results_summary(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes results_summary."""
        summary = {"total": 10, "completed": 8, "failed": 2}
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_RES",
            results_summary=summary,
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["results_summary"] == summary

    async def test_get_run_returns_csv_path(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes csv_path."""
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_CSV",
            csv_path="/tmp/output.csv",
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["csv_path"] == "/tmp/output.csv"

    async def test_get_run_returns_all_new_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response includes all new fields at once."""
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_ALL",
            phase="publishing",
            seed_keywords=["k1", "k2"],
            config_snapshot={"model": "gpt-4"},
            results_summary={"total": 2},
            csv_path="/tmp/all.csv",
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_code"] == "API_ALL"
        assert data["phase"] == "publishing"
        assert data["seed_keywords"] == ["k1", "k2"]
        assert data["config_snapshot"] == {"model": "gpt-4"}
        assert data["results_summary"] == {"total": 2}
        assert data["csv_path"] == "/tmp/all.csv"

    async def test_get_run_returns_defaults_when_not_set(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """GET run response shows defaults for fields not explicitly set."""
        run = Run(blog_id=blog_in_db.id, run_code="API_DEFAULTS")
        db_session.add(run)
        await db_session.flush()

        resp = await client.get(f"/api/v1/runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "pending"
        assert data["seed_keywords"] == []
        assert data["config_snapshot"] == {}
        assert data["results_summary"] == {}
        assert data["csv_path"] is None

    async def test_list_runs_returns_new_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """List runs response includes all new fields."""
        run = Run(
            blog_id=blog_in_db.id,
            run_code="API_LIST",
            phase="completed",
            seed_keywords=["test"],
        )
        db_session.add(run)
        await db_session.flush()

        resp = await client.get("/api/v1/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        run_data = [r for r in data if r["run_code"] == "API_LIST"][0]
        assert run_data["phase"] == "completed"
        assert run_data["seed_keywords"] == ["test"]


# ===================================================================
# Existing tests (preserve)
# ===================================================================


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
