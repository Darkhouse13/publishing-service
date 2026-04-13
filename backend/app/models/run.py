"""Run ORM model.

Represents a pipeline execution run for a specific blog.  Each run
captures configuration at launch time and tracks overall progress.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Run(Base):
    """SQLAlchemy ORM model for the ``runs`` table."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    blog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )
    run_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )
    phase: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )
    seed_keywords: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    config_snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    results_summary: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    csv_path: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        default=None,
    )
    articles_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    articles_completed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    articles_failed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String(4096),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationship back to Blog
    blog: Mapped["Blog"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Blog",
        backref="runs",
        lazy="selectin",
    )

    # Relationship to articles
    articles: Mapped[list["Article"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Article",
        back_populates="run",
        lazy="selectin",
    )
