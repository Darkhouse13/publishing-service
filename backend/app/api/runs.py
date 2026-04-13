"""FastAPI router for Run endpoints.

Routes:
    GET    /api/v1/runs         → List all runs
    GET    /api/v1/runs/{id}    → Get run details
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.run import RunResponse
from app.services.run import RunService

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


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
    """Get a single run by ID."""
    service = RunService(db)
    run = await service.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.model_validate(run)
