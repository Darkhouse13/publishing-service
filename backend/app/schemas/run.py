"""Pydantic schemas for Run CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RunResponse(BaseModel):
    """Schema returned for single-run and list responses."""

    id: uuid.UUID
    blog_id: uuid.UUID
    status: str
    articles_total: int
    articles_completed: int
    articles_failed: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
