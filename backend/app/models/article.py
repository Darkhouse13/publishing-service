"""Article ORM model.

Represents a generated article produced during a pipeline run.  Each
article belongs to a blog and optionally to a run, and tracks its own
generation status.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Article(Base):
    """SQLAlchemy ORM model for the ``articles`` table."""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    blog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
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

    # --- Content fields ---
    seo_title: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
    )
    meta_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    focus_keyword: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    content_markdown: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    content_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    # --- Image fields ---
    hero_image_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    hero_image_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )
    detail_image_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    detail_image_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )

    # --- Pinterest fields ---
    pin_title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    pin_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    pin_text_overlay: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    pin_image_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )

    # --- Metadata fields ---
    category_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    generation_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    validation_errors: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    brain_output: Mapped[Optional[Any]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )

    # Relationship back to Blog
    blog: Mapped["Blog"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Blog",
        back_populates="articles",
        lazy="selectin",
    )

    # Relationship back to Run
    run: Mapped[Optional["Run"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Run",
        back_populates="articles",
        lazy="selectin",
    )
