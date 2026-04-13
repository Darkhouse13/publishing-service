"""Credential ORM model.

Represents an encrypted credential for a provider/key_name pair.
The ``value`` is stored encrypted at rest using Fernet in the
``value_encrypted`` column.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Credential(Base):
    """SQLAlchemy ORM model for the ``credentials`` table."""

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("provider", "key_name", name="uq_credentials_provider_key_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    key_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value_encrypted: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
