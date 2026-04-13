"""Service layer for Run CRUD operations."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run


class RunService:
    """Handles all Run-related business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Run]:
        """Return all runs, ordered by creation date descending."""
        result = await self._session.execute(
            select(Run).order_by(Run.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, run_id: uuid.UUID) -> Optional[Run]:
        """Return a single run by ID, or ``None``."""
        result = await self._session.execute(
            select(Run).where(Run.id == run_id)
        )
        return result.scalar_one_or_none()
