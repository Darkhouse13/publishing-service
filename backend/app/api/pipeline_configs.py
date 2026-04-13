"""FastAPI router for PipelineConfig endpoints.

Routes:
    GET /api/v1/blogs/{blog_id}/pipeline-config  → Get blog's config
    PUT /api/v1/blogs/{blog_id}/pipeline-config  → Update blog's config
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.pipeline_config import PipelineConfigResponse, PipelineConfigUpdate
from app.services.blog import BlogService
from app.services.pipeline_config import PipelineConfigService

router = APIRouter(
    prefix="/api/v1/blogs/{blog_id}/pipeline-config",
    tags=["pipeline-configs"],
)


@router.get("", response_model=PipelineConfigResponse)
async def get_pipeline_config(
    blog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineConfigResponse:
    """Get the pipeline configuration for a blog.

    Fulfils VAL-PIPE-002.
    """
    # Verify blog exists
    blog_service = BlogService(db)
    blog = await blog_service.get_by_id(blog_id)
    if blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")

    config_service = PipelineConfigService(db)
    config = await config_service.get_by_blog_id(blog_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Pipeline config not found")
    return PipelineConfigResponse.model_validate(config)


@router.put("", response_model=PipelineConfigResponse)
async def update_pipeline_config(
    blog_id: uuid.UUID,
    payload: PipelineConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> PipelineConfigResponse:
    """Update the pipeline configuration for a blog.

    Fulfils VAL-PIPE-003.
    """
    # Verify blog exists
    blog_service = BlogService(db)
    blog = await blog_service.get_by_id(blog_id)
    if blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")

    config_service = PipelineConfigService(db)
    config = await config_service.update_by_blog_id(blog_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="Pipeline config not found")
    await db.commit()
    return PipelineConfigResponse.model_validate(config)
