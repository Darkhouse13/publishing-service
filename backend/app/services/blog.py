"""Service layer for Blog CRUD operations.

Encapsulates business logic, encryption of WordPress application passwords,
and soft-delete semantics.  Routers should delegate to this layer rather
than accessing the database directly.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt
from app.models.blog import Blog, _slugify
from app.schemas.blog import BlogCreate, BlogUpdate


class BlogService:
    """Handles all Blog-related business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, data: BlogCreate) -> Blog:
        """Create a new blog with encrypted credentials.

        Also creates a default PipelineConfig for the blog.

        Raises:
            ValueError: If a blog with the same slug already exists.
        """
        slug = _slugify(data.name)

        # Check for duplicate slug
        existing = await self._session.execute(
            select(Blog).where(Blog.slug == slug, Blog.is_active == True)  # noqa: E712
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Blog with slug '{slug}' already exists.")

        blog = Blog(
            name=data.name,
            slug=slug,
            url=data.url,
            wp_username=data.wp_username,
            wp_app_password_encrypted=encrypt(data.wp_application_password),
            profile_prompt=data.profile_prompt,
            fallback_category=data.fallback_category,
            deprioritized_category=data.deprioritized_category,
            category_keywords=data.category_keywords,
            pinterest_board_map=data.pinterest_board_map,
            seed_keywords=data.seed_keywords,
        )
        self._session.add(blog)
        await self._session.flush()
        await self._session.refresh(blog)

        # Auto-create default pipeline config
        from app.services.pipeline_config import PipelineConfigService

        config_service = PipelineConfigService(self._session)
        await config_service.create_default(blog.id)

        return blog

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_all(self) -> list[Blog]:
        """Return all active blogs, ordered by creation date."""
        result = await self._session.execute(
            select(Blog)
            .where(Blog.is_active == True)  # noqa: E712
            .order_by(Blog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, blog_id: uuid.UUID) -> Optional[Blog]:
        """Return a single active blog by ID, or ``None``."""
        result = await self._session.execute(
            select(Blog).where(Blog.id == blog_id, Blog.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(self, blog_id: uuid.UUID, data: BlogUpdate) -> Optional[Blog]:
        """Update an active blog.  Returns ``None`` if blog not found."""
        blog = await self.get_by_id(blog_id)
        if blog is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Handle password encryption separately
        new_password = update_data.pop("wp_application_password", None)
        if new_password is not None:
            blog.wp_app_password_encrypted = encrypt(new_password)

        # Handle name change (slug regeneration is done by ORM event)
        for field, value in update_data.items():
            setattr(blog, field, value)

        # Ensure updated_at is refreshed
        blog.updated_at = datetime.now(timezone.utc)

        await self._session.flush()
        await self._session.refresh(blog)
        return blog

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    async def soft_delete(self, blog_id: uuid.UUID) -> bool:
        """Soft-delete a blog (set ``is_active=False``).

        Returns:
            ``True`` if the blog was found and deactivated,
            ``False`` if it was not found.
        """
        blog = await self.get_by_id(blog_id)
        if blog is None:
            return False

        blog.is_active = False
        blog.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True
