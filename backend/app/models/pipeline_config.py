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
    articles_per_week: Mapped[int] = mapped_column(
        Integer,
        default=5,
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
    content_tone: Mapped[str] = mapped_column(
        String(255),
        default="informative",
        nullable=False,
    )
    default_category: Mapped[str] = mapped_column(
        String(255),
        default="",
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
