"""Article ORM model.

Represents a generated article produced during a pipeline run.  Each
article belongs to a run and tracks its own generation status.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Article(Base):
    """SQLAlchemy ORM model for the ``articles`` table."""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
    )
    slug: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )
    wp_post_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    wp_permalink: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationship back to Run
    run: Mapped["Run"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Run",
        backref="articles",
        lazy="selectin",
    )
