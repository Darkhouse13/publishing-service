"""Pydantic schemas for Article CRUD operations."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ArticleCreate(BaseModel):
    """Schema for creating a new article.

    Requires a valid ``blog_id`` and a ``topic`` string.
    """

    blog_id: uuid.UUID
    topic: str = Field(..., min_length=1)


class ArticleResponse(BaseModel):
    """Schema returned for single-article and list responses."""

    id: uuid.UUID
    blog_id: uuid.UUID
    run_id: Optional[uuid.UUID] = None
    keyword: str
    title: Optional[str] = None
    slug: Optional[str] = None
    status: str
    wp_post_id: Optional[int] = None
    wp_permalink: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    # Content fields
    seo_title: Optional[str] = None
    meta_description: Optional[str] = None
    focus_keyword: Optional[str] = None
    content_markdown: Optional[str] = None
    content_html: Optional[str] = None

    # Image fields
    hero_image_prompt: Optional[str] = None
    hero_image_url: Optional[str] = None
    detail_image_prompt: Optional[str] = None
    detail_image_url: Optional[str] = None

    # Pinterest fields
    pin_title: Optional[str] = None
    pin_description: Optional[str] = None
    pin_text_overlay: Optional[str] = None
    pin_image_url: Optional[str] = None

    # Metadata fields
    category_name: Optional[str] = None
    generation_attempts: int = 0
    validation_errors: list[str] = []
    brain_output: Optional[Any] = None

    model_config = {"from_attributes": True}
