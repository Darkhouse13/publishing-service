"""Pydantic schemas for PipelineConfig CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

DEFAULT_LLM_PROVIDER: str = "deepseek"
DEFAULT_IMAGE_PROVIDER: str = "fal"
DEFAULT_LLM_MODEL: str = "deepseek-chat"
DEFAULT_IMAGE_MODEL: str = "fal-ai/flux/dev"
DEFAULT_TRENDS_REGION: str = "GLOBAL"
DEFAULT_TRENDS_RANGE: str = "12m"
DEFAULT_TRENDS_TOP_N: int = 20
DEFAULT_PINCLICKS_MAX_RECORDS: int = 25
DEFAULT_WINNERS_COUNT: int = 5
DEFAULT_PUBLISH_STATUS: str = "draft"
DEFAULT_CSV_CADENCE_MINUTES: int = 240
DEFAULT_PIN_TEMPLATE_MODE: str = "center_strip"
DEFAULT_MAX_CONCURRENT_ARTICLES: int = 3


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class PipelineConfigUpdate(BaseModel):
    """Schema for updating pipeline configuration.

    All fields are optional — only provided fields will be updated.
    """

    llm_provider: Optional[str] = Field(None, min_length=1, max_length=255)
    image_provider: Optional[str] = Field(None, min_length=1, max_length=255)
    llm_model: Optional[str] = Field(None, min_length=1, max_length=255)
    image_model: Optional[str] = Field(None, min_length=1, max_length=255)
    trends_region: Optional[str] = Field(None, min_length=1, max_length=255)
    trends_range: Optional[str] = Field(None, min_length=1, max_length=255)
    trends_top_n: Optional[int] = Field(None, ge=1)
    pinclicks_max_records: Optional[int] = Field(None, ge=1)
    winners_count: Optional[int] = Field(None, ge=1)
    publish_status: Optional[str] = Field(None, min_length=1, max_length=255)
    csv_cadence_minutes: Optional[int] = Field(None, ge=1)
    pin_template_mode: Optional[str] = Field(None, min_length=1, max_length=255)
    max_concurrent_articles: Optional[int] = Field(None, ge=1)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PipelineConfigResponse(BaseModel):
    """Schema returned for pipeline config responses."""

    id: uuid.UUID
    blog_id: uuid.UUID
    llm_provider: str
    image_provider: str
    llm_model: str
    image_model: str
    trends_region: str
    trends_range: str
    trends_top_n: int
    pinclicks_max_records: int
    winners_count: int
    publish_status: str
    csv_cadence_minutes: int
    pin_template_mode: str
    max_concurrent_articles: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
