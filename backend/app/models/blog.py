"""Blog ORM model.

Represents a WordPress blog with its connection credentials.
The ``wp_app_password`` is stored encrypted at rest using Fernet.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, event
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _slugify(name: str) -> str:
    """Convert a blog name to a URL-safe slug.

    Examples::

        >>> _slugify("My Fancy Blog!")
        'my-fancy-blog'
        >>> _slugify("Test Blog")
        'test-blog'
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


class Blog(Base):
    """SQLAlchemy ORM model for the ``blogs`` table."""

    __tablename__ = "blogs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    wp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    wp_app_password_encrypted: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


@event.listens_for(Blog, "before_insert")
def _set_slug_on_insert(mapper: object, connection: object, target: Blog) -> None:
    """Auto-generate slug from name on insert if not already set."""
    if not target.slug:
        target.slug = _slugify(target.name)


@event.listens_for(Blog, "before_update")
def _set_slug_on_update(mapper: object, connection: object, target: Blog) -> None:
    """Regenerate slug from name on update if name changed."""
    # Only regenerate if the name attribute was modified
    from sqlalchemy import inspect as sa_inspect

    state = sa_inspect(target)
    history = state.get_history("name", True)  # type: ignore[arg-type]
    if history.has_changes():
        target.slug = _slugify(target.name)
