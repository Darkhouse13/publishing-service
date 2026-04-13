"""FastAPI router for Article endpoints.

Routes:
    GET    /api/v1/articles         → List all articles
    GET    /api/v1/articles/{id}    → Get article details
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.article import ArticleResponse
from app.services.article import ArticleService

router = APIRouter(prefix="/api/v1/articles", tags=["articles"])


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    db: AsyncSession = Depends(get_db),
) -> list[ArticleResponse]:
    """List all articles."""
    service = ArticleService(db)
    articles = await service.list_all()
    return [ArticleResponse.model_validate(a) for a in articles]


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ArticleResponse:
    """Get a single article by ID."""
    service = ArticleService(db)
    article = await service.get_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)
