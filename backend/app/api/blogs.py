"""FastAPI router for Blog CRUD endpoints.

Routes:
    POST   /api/v1/blogs         → Create a blog
    GET    /api/v1/blogs         → List active blogs
    GET    /api/v1/blogs/{id}    → Get blog details
    PATCH  /api/v1/blogs/{id}    → Update blog metadata
    DELETE /api/v1/blogs/{id}    → Soft-delete blog
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.blog import BlogCreate, BlogResponse, BlogUpdate
from app.services.blog import BlogService

router = APIRouter(prefix="/api/v1/blogs", tags=["blogs"])


def _blog_service(session: AsyncSession = Depends(get_db)) -> BlogService:
    """Factory dependency that constructs a ``BlogService``."""
    return BlogService(session)


@router.post("", response_model=BlogResponse, status_code=201)
async def create_blog(
    payload: BlogCreate,
    db: AsyncSession = Depends(get_db),
) -> BlogResponse:
    """Create a new blog with encrypted WordPress credentials.

    Fulfils VAL-BLOG-001.
    """
    service = BlogService(db)
    try:
        blog = await service.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return BlogResponse.model_validate(blog)


@router.get("", response_model=list[BlogResponse])
async def list_blogs(
    db: AsyncSession = Depends(get_db),
) -> list[BlogResponse]:
    """List all active blogs. Passwords are masked.

    Fulfils VAL-BLOG-002.
    """
    service = BlogService(db)
    blogs = await service.list_all()
    return [BlogResponse.model_validate(b) for b in blogs]


@router.get("/{blog_id}", response_model=BlogResponse)
async def get_blog(
    blog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BlogResponse:
    """Get a single active blog by ID. Password is masked.

    Fulfils VAL-BLOG-003.
    """
    service = BlogService(db)
    blog = await service.get_by_id(blog_id)
    if blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")
    return BlogResponse.model_validate(blog)


@router.patch("/{blog_id}", response_model=BlogResponse)
async def update_blog(
    blog_id: uuid.UUID,
    payload: BlogUpdate,
    db: AsyncSession = Depends(get_db),
) -> BlogResponse:
    """Update blog metadata. Password is re-encrypted if changed.

    Fulfils VAL-BLOG-004.
    """
    service = BlogService(db)
    blog = await service.update(blog_id, payload)
    if blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")
    await db.commit()
    return BlogResponse.model_validate(blog)


@router.delete("/{blog_id}", status_code=204)
async def delete_blog(
    blog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a blog (sets ``is_active=False`` and ``deleted_at``).

    Fulfils VAL-BLOG-005.
    """
    service = BlogService(db)
    deleted = await service.soft_delete(blog_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Blog not found")
    await db.commit()
