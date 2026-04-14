"""FastAPI router for Article endpoints.

Routes:
    POST   /api/v1/articles         → Create article (triggers single article pipeline)
    GET    /api/v1/articles         → List all articles
    GET    /api/v1/articles/{id}    → Get article details
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.article import Article
from app.models.blog import Blog
from app.schemas.article import ArticleCreate, ArticleResponse
from app.services.article import ArticleService
from app.tasks.pipeline import generate_single_article_task

router = APIRouter(prefix="/api/v1/articles", tags=["articles"])


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article(
    payload: ArticleCreate,
    db: AsyncSession = Depends(get_db),
) -> ArticleResponse:
    """Create a new article and dispatch the single article pipeline task.

    Validates the blog exists, creates an Article with status='pending',
    and dispatches the generate_single_article_task.

    Fulfils VAL-API-006 through VAL-API-009.
    """

    # Validate blog exists
    result = await db.execute(
        select(Blog).where(Blog.id == payload.blog_id, Blog.is_active == True)  # noqa: E712
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(
            status_code=422,
            detail=f"Blog with id '{payload.blog_id}' not found or inactive.",
        )

    # Create the Article
    article = Article(
        blog_id=payload.blog_id,
        run_id=None,
        keyword=payload.topic,
        status="pending",
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)

    # Dispatch the single article task
    generate_single_article_task.delay(str(article.id))

    await db.commit()
    await db.refresh(article)
    return ArticleResponse.model_validate(article)


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
