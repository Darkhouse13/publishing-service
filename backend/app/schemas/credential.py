"""Pydantic schemas for Credential CRUD operations.

Schemas handle request validation and response serialisation.
Sensitive fields (``value``) are **never** returned in response schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CredentialCreate(BaseModel):
    """Schema for creating or upserting a credential.

    If a credential with the same (provider, key_name) already exists,
    it will be updated (upsert semantics).
    """

    provider: str = Field(..., min_length=1, max_length=255)
    key_name: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=2048)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CredentialResponse(BaseModel):
    """Schema returned for single-credential and list responses.

    The ``value`` field is intentionally excluded — it must never
    appear in API responses.
    """

    id: uuid.UUID
    provider: str
    key_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
