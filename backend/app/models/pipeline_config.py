"""PipelineConfig ORM model.

Represents per-blog pipeline configuration with sensible defaults.
Each blog has exactly one PipelineConfig (one-to-one relationship).
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.blog import Blog


class PipelineConfig(Base):
    """SQLAlchemy ORM model for the ``pipeline_configs`` table."""

    __tablename__ = "pipeline_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    blog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blogs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    llm_provider: Mapped[str] = mapped_column(
        String(255),
        default="deepseek",
        nullable=False,
    )
    image_provider: Mapped[str] = mapped_column(
        String(255),
        default="fal",
        nullable=False,
    )
    llm_model: Mapped[str] = mapped_column(
        String(255),
        default="deepseek-chat",
        nullable=False,
    )
    image_model: Mapped[str] = mapped_column(
        String(255),
        default="fal-ai/flux/dev",
        nullable=False,
    )
    trends_region: Mapped[str] = mapped_column(
        String(255),
        default="GLOBAL",
        nullable=False,
    )
    trends_range: Mapped[str] = mapped_column(
        String(255),
        default="12m",
        nullable=False,
    )
    trends_top_n: Mapped[int] = mapped_column(
        Integer,
        default=20,
        nullable=False,
    )
    pinclicks_max_records: Mapped[int] = mapped_column(
        Integer,
        default=25,
        nullable=False,
    )
    winners_count: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    publish_status: Mapped[str] = mapped_column(
        String(255),
        default="draft",
        nullable=False,
    )
    csv_cadence_minutes: Mapped[int] = mapped_column(
        Integer,
        default=240,
        nullable=False,
    )
    pin_template_mode: Mapped[str] = mapped_column(
        String(255),
        default="center_strip",
        nullable=False,
    )
    max_concurrent_articles: Mapped[int] = mapped_column(
        Integer,
        default=3,
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

    # Relationship back to Blog
    blog: Mapped["Blog"] = relationship(
        "Blog",
        backref="pipeline_config",
        lazy="selectin",
    )
