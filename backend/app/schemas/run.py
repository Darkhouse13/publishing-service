"""Pydantic schemas for Run CRUD operations."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class RunCreate(BaseModel):
    """Schema for creating a new run.

    Requires a valid ``blog_id`` and a non-empty ``keywords`` list.
    """

    blog_id: uuid.UUID
    keywords: list[str] = Field(..., min_length=1)

    @field_validator("keywords")
    @classmethod
    def keywords_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("keywords must not be empty")
        return v


class RunResponse(BaseModel):
    """Schema returned for single-run and list responses."""

    id: uuid.UUID
    blog_id: uuid.UUID
    status: str
    run_code: str
    phase: str = "pending"
    seed_keywords: list = []
    config_snapshot: dict[str, Any] = {}
    results_summary: dict[str, Any] = {}
    csv_path: Optional[str] = None
    articles_total: int
    articles_completed: int
    articles_failed: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
