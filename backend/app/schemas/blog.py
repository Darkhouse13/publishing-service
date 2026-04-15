"""Pydantic schemas for Blog CRUD operations.

Schemas handle request validation and response serialisation.
Sensitive fields (``wp_application_password``) are **masked** in all
response schemas — the plaintext value is never returned by the API.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Mask constant
# ---------------------------------------------------------------------------

MASK = "********"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class BlogCreate(BaseModel):
    """Schema for creating a new blog."""

    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=2048)
    wp_username: str = Field(..., min_length=1, max_length=255)
    wp_application_password: str = Field(..., min_length=1, max_length=1024)

    # New pipeline configuration fields (all optional with defaults)
    profile_prompt: str = Field(default="", max_length=65535)
    fallback_category: str = Field(default="", max_length=255)
    deprioritized_category: str = Field(default="", max_length=255)
    category_keywords: dict = Field(default_factory=dict)
    pinterest_board_map: dict = Field(default_factory=dict)
    seed_keywords: list = Field(default_factory=list)


class BlogUpdate(BaseModel):
    """Schema for partially updating a blog.

    All fields are optional — only provided fields will be updated.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    wp_username: Optional[str] = Field(None, min_length=1, max_length=255)
    wp_application_password: Optional[str] = Field(None, min_length=1, max_length=1024)
    is_active: Optional[bool] = None

    # New pipeline configuration fields (all optional for partial updates)
    profile_prompt: Optional[str] = Field(None, max_length=65535)
    fallback_category: Optional[str] = Field(None, max_length=255)
    deprioritized_category: Optional[str] = Field(None, max_length=255)
    category_keywords: Optional[dict] = Field(None)
    pinterest_board_map: Optional[dict] = Field(None)
    seed_keywords: Optional[list] = Field(None)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class BlogResponse(BaseModel):
    """Schema returned for single-blog and list responses.

    The ``wp_application_password`` is always masked.
    """

    id: uuid.UUID
    name: str
    slug: str
    url: str
    wp_username: str
    wp_application_password: str = MASK
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # New pipeline configuration fields
    profile_prompt: str = ""
    fallback_category: str = ""
    deprioritized_category: str = ""
    category_keywords: dict = {}
    pinterest_board_map: dict = {}
    seed_keywords: list = []

    model_config = {"from_attributes": True}
