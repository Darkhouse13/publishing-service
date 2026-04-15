"""Application configuration loaded from environment variables via Pydantic Settings."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the publishing service backend.

    Values are loaded from environment variables or a `.env` file located in
    the ``backend/`` directory.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application -----------------------------------------------------------
    DEBUG: bool = False

    # Database --------------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # Encryption ------------------------------------------------------------
    ENCRYPTION_KEY: str = ""

    # Redis / Celery --------------------------------------------------------
    REDIS_URL: Optional[str] = None

    # CORS ------------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost"]

    # Runtime directories ----------------------------------------------------
    # backend/app/core/config.py -> backend/
    _BACKEND_ROOT: str = str(Path(__file__).resolve().parent.parent.parent)
    ARTIFACTS_DIR: str = str(Path(_BACKEND_ROOT) / "artifacts")


settings = Settings()
