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
    DEFAULT_CSV_CADENCE_MINUTES,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_MAX_CONCURRENT_ARTICLES,
    DEFAULT_PIN_TEMPLATE_MODE,
    DEFAULT_PINCLICKS_MAX_RECORDS,
    DEFAULT_PUBLISH_STATUS,
    DEFAULT_TRENDS_RANGE,
    DEFAULT_TRENDS_REGION,
    DEFAULT_TRENDS_TOP_N,
    DEFAULT_WINNERS_COUNT,
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
            llm_provider=DEFAULT_LLM_PROVIDER,
            image_provider=DEFAULT_IMAGE_PROVIDER,
            llm_model=DEFAULT_LLM_MODEL,
            image_model=DEFAULT_IMAGE_MODEL,
            trends_region=DEFAULT_TRENDS_REGION,
            trends_range=DEFAULT_TRENDS_RANGE,
            trends_top_n=DEFAULT_TRENDS_TOP_N,
            pinclicks_max_records=DEFAULT_PINCLICKS_MAX_RECORDS,
            winners_count=DEFAULT_WINNERS_COUNT,
            publish_status=DEFAULT_PUBLISH_STATUS,
            csv_cadence_minutes=DEFAULT_CSV_CADENCE_MINUTES,
            pin_template_mode=DEFAULT_PIN_TEMPLATE_MODE,
            max_concurrent_articles=DEFAULT_MAX_CONCURRENT_ARTICLES,
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
