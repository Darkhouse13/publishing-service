"""Pydantic schemas for Article CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArticleResponse(BaseModel):
    """Schema returned for single-article and list responses."""

    id: uuid.UUID
    run_id: uuid.UUID
    keyword: str
    title: Optional[str] = None
    slug: Optional[str] = None
    status: str
    wp_post_id: Optional[int] = None
    wp_permalink: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
