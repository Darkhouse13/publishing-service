"""FastAPI router for Credential CRUD endpoints.

Routes:
    POST   /api/v1/credentials         → Create or upsert credential
    GET    /api/v1/credentials         → List credentials (no secret values)
    DELETE /api/v1/credentials/{id}    → Delete credential
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.credential import CredentialCreate, CredentialResponse
from app.services.credential import CredentialService

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])


@router.post("", response_model=CredentialResponse)
async def upsert_credential(
    payload: CredentialCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> CredentialResponse:
    """Create or update a credential with encrypted value.

    If a credential with the same (provider, key_name) already exists,
    the value is updated (upsert semantics).

    Returns 201 on create, 200 on update.
    Fulfils VAL-CRED-001, VAL-CRED-002.
    """
    service = CredentialService(db)
    credential, created = await service.upsert(payload)
    await db.commit()

    response.status_code = 201 if created else 200
    return CredentialResponse.model_validate(credential)


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
) -> list[CredentialResponse]:
    """List all credentials. Secret values are never returned.

    Fulfils VAL-CRED-003.
    """
    service = CredentialService(db)
    credentials = await service.list_all()
    return [CredentialResponse.model_validate(c) for c in credentials]


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a credential by ID.

    Fulfils VAL-CRED-004.
    """
    service = CredentialService(db)
    deleted = await service.delete(credential_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    await db.commit()
