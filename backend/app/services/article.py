"""Service layer for Article CRUD operations."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article


class ArticleService:
    """Handles all Article-related business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Article]:
        """Return all articles, ordered by creation date descending."""
        result = await self._session.execute(
            select(Article).order_by(Article.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, article_id: uuid.UUID) -> Optional[Article]:
        """Return a single article by ID, or ``None``."""
        result = await self._session.execute(
            select(Article).where(Article.id == article_id)
        )
        return result.scalar_one_or_none()
