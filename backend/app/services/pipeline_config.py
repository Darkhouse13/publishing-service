"""Service layer for PipelineConfig CRUD operations.

Encapsulates business logic for creating default configs and
updating pipeline settings per blog.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_config import PipelineConfig
from app.schemas.pipeline_config import (
    DEFAULT_ARTICLES_PER_WEEK,
    DEFAULT_CATEGORY,
    DEFAULT_CONTENT_TONE,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_LLM_PROVIDER,
    PipelineConfigUpdate,
)


class PipelineConfigService:
    """Handles all PipelineConfig-related business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Create (default)
    # ------------------------------------------------------------------

    async def create_default(self, blog_id: uuid.UUID) -> PipelineConfig:
        """Create a default pipeline config for a blog.

        Called automatically after blog creation.
        """
        config = PipelineConfig(
            blog_id=blog_id,
            articles_per_week=DEFAULT_ARTICLES_PER_WEEK,
            llm_provider=DEFAULT_LLM_PROVIDER,
            image_provider=DEFAULT_IMAGE_PROVIDER,
            content_tone=DEFAULT_CONTENT_TONE,
            default_category=DEFAULT_CATEGORY,
        )
        self._session.add(config)
        await self._session.flush()
        await self._session.refresh(config)
        return config

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_blog_id(self, blog_id: uuid.UUID) -> Optional[PipelineConfig]:
        """Return the pipeline config for the given blog, or ``None``."""
        result = await self._session.execute(
            select(PipelineConfig).where(PipelineConfig.blog_id == blog_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_by_blog_id(
        self,
        blog_id: uuid.UUID,
        data: PipelineConfigUpdate,
    ) -> Optional[PipelineConfig]:
        """Update the pipeline config for the given blog.

        Returns ``None`` if no config exists for the blog.
        """
        config = await self.get_by_blog_id(blog_id)
        if config is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

        config.updated_at = datetime.now(timezone.utc)

        await self._session.flush()
        await self._session.refresh(config)
        return config
