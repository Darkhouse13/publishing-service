"""Pydantic schemas for PipelineConfig CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

DEFAULT_ARTICLES_PER_WEEK: int = 5
DEFAULT_LLM_PROVIDER: str = "deepseek"
DEFAULT_IMAGE_PROVIDER: str = "fal"
DEFAULT_CONTENT_TONE: str = "informative"
DEFAULT_CATEGORY: str = ""


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class PipelineConfigUpdate(BaseModel):
    """Schema for updating pipeline configuration.

    All fields are optional — only provided fields will be updated.
    """

    articles_per_week: Optional[int] = Field(None, ge=1, le=100)
    llm_provider: Optional[str] = Field(None, min_length=1, max_length=255)
    image_provider: Optional[str] = Field(None, min_length=1, max_length=255)
    content_tone: Optional[str] = Field(None, min_length=1, max_length=255)
    default_category: Optional[str] = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PipelineConfigResponse(BaseModel):
    """Schema returned for pipeline config responses."""

    id: uuid.UUID
    blog_id: uuid.UUID
    articles_per_week: int
    llm_provider: str
    image_provider: str
    content_tone: str
    default_category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
