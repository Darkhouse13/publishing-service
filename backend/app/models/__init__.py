"""ORM models package.

Import ``Base`` here so that Alembic's ``target_metadata`` can pick up
all models via a single import chain.
"""

from app.models.base import Base

__all__ = ["Base"]
