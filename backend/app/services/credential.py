"""Service layer for Credential CRUD operations.

Encapsulates business logic, encryption of credential values, and
upsert semantics.  Routers should delegate to this layer rather
than accessing the database directly.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt, encrypt
from app.models.credential import Credential
from app.schemas.credential import CredentialCreate


class CredentialService:
    """Handles all Credential-related business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Upsert (Create or Update)
    # ------------------------------------------------------------------

    async def upsert(self, data: CredentialCreate) -> tuple[Credential, bool]:
        """Create or update a credential for the given (provider, key_name).

        Returns:
            A tuple of (credential, created) where ``created`` is ``True``
            if a new record was inserted and ``False`` if an existing
            record was updated.
        """
        result = await self._session.execute(
            select(Credential).where(
                Credential.provider == data.provider,
                Credential.key_name == data.key_name,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Update existing record
            existing.value_encrypted = encrypt(data.value)
            existing.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            await self._session.refresh(existing)
            return existing, False

        # Create new record
        credential = Credential(
            provider=data.provider,
            key_name=data.key_name,
            value_encrypted=encrypt(data.value),
        )
        self._session.add(credential)
        await self._session.flush()
        await self._session.refresh(credential)
        return credential, True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_all(self) -> list[Credential]:
        """Return all credentials, ordered by creation date."""
        result = await self._session.execute(
            select(Credential).order_by(Credential.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, credential_id: uuid.UUID) -> Optional[Credential]:
        """Return a single credential by ID, or ``None``."""
        result = await self._session.execute(
            select(Credential).where(Credential.id == credential_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Decrypt helper (for internal use by providers)
    # ------------------------------------------------------------------

    @staticmethod
    def decrypt_value(credential: Credential) -> str:
        """Decrypt and return the plaintext value of a credential.

        This method is intended for internal use by the provider layer.
        It must never be called from API response handlers.
        """
        return decrypt(credential.value_encrypted)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, credential_id: uuid.UUID) -> bool:
        """Hard-delete a credential.

        Returns:
            ``True`` if the credential was found and deleted,
            ``False`` if it was not found.
        """
        credential = await self.get_by_id(credential_id)
        if credential is None:
            return False

        await self._session.delete(credential)
        await self._session.flush()
        return True
