"""FastAPI router for Run endpoints.

Routes:
    POST   /api/v1/runs         → Create a new run (triggers bulk pipeline)
    GET    /api/v1/runs         → List all runs
    GET    /api/v1/runs/{id}    → Get run details (with articles & progress)
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.blog import Blog
from app.models.run import Run
from app.schemas.run import RunCreate, RunResponse
from app.services.pipeline_config import PipelineConfigService
from app.services.run import RunService
from app.tasks.pipeline import run_bulk_pipeline_task

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Create a new run and dispatch the bulk pipeline task.

    Validates the blog exists and is active, loads PipelineConfig,
    snapshots config and seed_keywords, generates a timestamp run_code,
    and dispatches the bulk pipeline Celery task.

    Fulfils VAL-API-001 through VAL-API-005.
    """

    # Validate blog exists and is active
    result = await db.execute(
        select(Blog).where(Blog.id == payload.blog_id, Blog.is_active == True)  # noqa: E712
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(
            status_code=422,
            detail=f"Blog with id '{payload.blog_id}' not found or inactive.",
        )

    # Load PipelineConfig
    config_service = PipelineConfigService(db)
    config = await config_service.get_by_blog_id(payload.blog_id)
    if config is None:
        raise HTTPException(
            status_code=422,
            detail="Blog has no pipeline configuration.",
        )

    # Snapshot config as a dict
    config_snapshot: dict[str, Any] = {
        "llm_provider": config.llm_provider,
        "image_provider": config.image_provider,
        "llm_model": config.llm_model,
        "image_model": config.image_model,
        "trends_region": config.trends_region,
        "trends_range": config.trends_range,
        "trends_top_n": config.trends_top_n,
        "pinclicks_max_records": config.pinclicks_max_records,
        "winners_count": config.winners_count,
        "publish_status": config.publish_status,
        "csv_cadence_minutes": config.csv_cadence_minutes,
        "pin_template_mode": config.pin_template_mode,
        "max_concurrent_articles": config.max_concurrent_articles,
    }

    # Generate timestamp run_code (YYYYMMDD_HHMMSS)
    now = datetime.now(timezone.utc)
    run_code = now.strftime("%Y%m%d_%H%M%S")

    # Create the Run
    run = Run(
        blog_id=payload.blog_id,
        status="pending",
        phase="pending",
        run_code=run_code,
        seed_keywords=payload.keywords,
        config_snapshot=config_snapshot,
        results_summary={},
        articles_total=len(payload.keywords),
        articles_completed=0,
        articles_failed=0,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    # Dispatch the bulk pipeline task
    run_bulk_pipeline_task.delay(str(run.id))

    await db.commit()
    await db.refresh(run)
    return RunResponse.model_validate(run)


@router.get("", response_model=list[RunResponse])
async def list_runs(
    db: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    """List all runs."""
    service = RunService(db)
    runs = await service.list_all()
    return [RunResponse.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Get a single run by ID, including articles list and progress counts.

    Fulfils VAL-API-010, VAL-API-011, VAL-API-012.
    """
    service = RunService(db)
    run = await service.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.model_validate(run)
