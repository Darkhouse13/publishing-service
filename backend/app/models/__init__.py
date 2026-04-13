"""ORM models package.

Import ``Base`` here so that Alembic's ``target_metadata`` can pick up
all models via a single import chain.
"""

from app.models.base import Base
from app.models.blog import Blog  # noqa: F401 – ensure model is registered
from app.models.credential import Credential  # noqa: F401 – ensure model is registered

__all__ = ["Base", "Blog", "Credential"]
