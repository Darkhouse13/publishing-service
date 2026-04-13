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


class BlogUpdate(BaseModel):
    """Schema for partially updating a blog.

    All fields are optional — only provided fields will be updated.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    wp_username: Optional[str] = Field(None, min_length=1, max_length=255)
    wp_application_password: Optional[str] = Field(None, min_length=1, max_length=1024)


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

    model_config = {"from_attributes": True}
