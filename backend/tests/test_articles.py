"""Tests for Article model, schema, service, and API endpoints.

Fulfils:
- VAL-ART-001: Article model adds blog_id FK column
- VAL-ART-002: Article model adds content fields
- VAL-ART-003: Article model adds image fields
- VAL-ART-004: Article model adds Pinterest fields
- VAL-ART-005: Article model adds metadata fields
- VAL-ART-006: Article run_id is now nullable
- VAL-ART-007: Article blog_id FK relationship works
- VAL-ART-008: Article validation_errors stores list
- VAL-ART-009: Article brain_output stores nested JSON
- VAL-ART-010: Article generation_attempts defaults to 0
- VAL-ART-011: Article API returns new fields
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.blog import Blog
from app.models.run import Run
from app.crypto import encrypt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_blog_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid blog creation payload."""
    return {
        "name": "Test Blog",
        "url": "https://testblog.com",
        "wp_username": "admin",
        "wp_application_password": "super-secret-password",
        **overrides,
    }


def _make_run_payload(blog_id: uuid.UUID) -> dict[str, Any]:
    """Return a minimal valid run creation payload (direct model creation)."""
    return {
        "blog_id": blog_id,
    }


# ---------------------------------------------------------------------------
# Async fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def blog_in_db(db_session: AsyncSession) -> Blog:
    """Create and persist a Blog, returning the ORM instance."""
    blog = Blog(
        name="Test Blog",
        slug="test-blog",
        url="https://testblog.com",
        wp_username="admin",
        wp_app_password_encrypted=encrypt("super-secret-password"),
    )
    db_session.add(blog)
    await db_session.flush()
    await db_session.refresh(blog)
    return blog


@pytest_asyncio.fixture()
async def run_in_db(
    db_session: AsyncSession,
    blog_in_db: Blog,
) -> Run:
    """Create and persist a Run linked to ``blog_in_db``."""
    run = Run(blog_id=blog_in_db.id)
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    return run


@pytest_asyncio.fixture()
async def existing_blog_via_api(client: AsyncClient) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=_make_blog_payload())
    assert response.status_code == 201
    return dict(response.json())


# ===================================================================
# VAL-ART-001: Article model adds blog_id FK column
# ===================================================================


class TestArticleBlogIdFK:
    """Verify blog_id FK column exists on Article model."""

    def test_blog_id_column_exists(self) -> None:
        """Article model defines a blog_id column."""
        assert "blog_id" in Article.__table__.columns

    def test_blog_id_is_uuid(self) -> None:
        """blog_id column has UUID type."""
        from sqlalchemy import Uuid
        col = Article.__table__.columns["blog_id"]
        assert isinstance(col.type, Uuid)

    def test_blog_id_not_nullable(self) -> None:
        """blog_id column is NOT NULL."""
        assert Article.__table__.columns["blog_id"].nullable is False

    def test_blog_id_references_blogs(self) -> None:
        """blog_id has a foreign key referencing blogs.id."""
        fks = list(Article.__table__.columns["blog_id"].foreign_keys)
        assert len(fks) == 1
        assert str(fks[0].target_fullname) == "blogs.id"


# ===================================================================
# VAL-ART-002: Article model adds content fields
# ===================================================================


class TestArticleContentFields:
    """Verify content fields exist on Article model."""

    @pytest.mark.parametrize(
        "field_name,col_type,max_len",
        [
            ("seo_title", "String(1024)", 1024),
            ("meta_description", "Text", None),
            ("focus_keyword", "String(255)", 255),
            ("content_markdown", "Text", None),
            ("content_html", "Text", None),
        ],
    )
    def test_content_field_exists(self, field_name: str, col_type: str, max_len: int | None) -> None:
        """Content column exists with correct type."""
        assert field_name in Article.__table__.columns
        col = Article.__table__.columns[field_name]
        assert col.nullable is True

    def test_seo_title_type(self) -> None:
        """seo_title is String(1024)."""
        from sqlalchemy import String
        col = Article.__table__.columns["seo_title"]
        assert isinstance(col.type, String)
        assert col.type.length == 1024

    def test_meta_description_type(self) -> None:
        """meta_description is Text."""
        from sqlalchemy import Text as SAText
        col = Article.__table__.columns["meta_description"]
        assert isinstance(col.type, SAText)

    def test_focus_keyword_type(self) -> None:
        """focus_keyword is String(255)."""
        from sqlalchemy import String
        col = Article.__table__.columns["focus_keyword"]
        assert isinstance(col.type, String)
        assert col.type.length == 255

    def test_content_markdown_type(self) -> None:
        """content_markdown is Text."""
        from sqlalchemy import Text as SAText
        col = Article.__table__.columns["content_markdown"]
        assert isinstance(col.type, SAText)

    def test_content_html_type(self) -> None:
        """content_html is Text."""
        from sqlalchemy import Text as SAText
        col = Article.__table__.columns["content_html"]
        assert isinstance(col.type, SAText)


# ===================================================================
# VAL-ART-003: Article model adds image fields
# ===================================================================


class TestArticleImageFields:
    """Verify image fields exist on Article model."""

    def test_hero_image_prompt_exists(self) -> None:
        """hero_image_prompt column exists."""
        assert "hero_image_prompt" in Article.__table__.columns

    def test_hero_image_url_exists(self) -> None:
        """hero_image_url column exists."""
        assert "hero_image_url" in Article.__table__.columns

    def test_detail_image_prompt_exists(self) -> None:
        """detail_image_prompt column exists."""
        assert "detail_image_prompt" in Article.__table__.columns

    def test_detail_image_url_exists(self) -> None:
        """detail_image_url column exists."""
        assert "detail_image_url" in Article.__table__.columns

    def test_all_image_fields_nullable(self) -> None:
        """All image fields are nullable."""
        for field in ["hero_image_prompt", "hero_image_url", "detail_image_prompt", "detail_image_url"]:
            assert Article.__table__.columns[field].nullable is True

    def test_image_prompt_types_are_text(self) -> None:
        """Image prompt fields are Text type."""
        from sqlalchemy import Text as SAText
        for field in ["hero_image_prompt", "detail_image_prompt"]:
            assert isinstance(Article.__table__.columns[field].type, SAText)

    def test_image_url_types_are_string_2048(self) -> None:
        """Image URL fields are String(2048)."""
        from sqlalchemy import String
        for field in ["hero_image_url", "detail_image_url"]:
            col = Article.__table__.columns[field]
            assert isinstance(col.type, String)
            assert col.type.length == 2048


# ===================================================================
# VAL-ART-004: Article model adds Pinterest fields
# ===================================================================


class TestArticlePinterestFields:
    """Verify Pinterest fields exist on Article model."""

    def test_pin_title_exists(self) -> None:
        """pin_title column exists."""
        assert "pin_title" in Article.__table__.columns

    def test_pin_description_exists(self) -> None:
        """pin_description column exists."""
        assert "pin_description" in Article.__table__.columns

    def test_pin_text_overlay_exists(self) -> None:
        """pin_text_overlay column exists."""
        assert "pin_text_overlay" in Article.__table__.columns

    def test_pin_image_url_exists(self) -> None:
        """pin_image_url column exists."""
        assert "pin_image_url" in Article.__table__.columns

    def test_all_pinterest_fields_nullable(self) -> None:
        """All Pinterest fields are nullable."""
        for field in ["pin_title", "pin_description", "pin_text_overlay", "pin_image_url"]:
            assert Article.__table__.columns[field].nullable is True

    def test_pin_title_type(self) -> None:
        """pin_title is String(255)."""
        from sqlalchemy import String
        col = Article.__table__.columns["pin_title"]
        assert isinstance(col.type, String)
        assert col.type.length == 255

    def test_pin_description_type(self) -> None:
        """pin_description is Text."""
        from sqlalchemy import Text as SAText
        assert isinstance(Article.__table__.columns["pin_description"].type, SAText)

    def test_pin_text_overlay_type(self) -> None:
        """pin_text_overlay is String(255)."""
        from sqlalchemy import String
        col = Article.__table__.columns["pin_text_overlay"]
        assert isinstance(col.type, String)
        assert col.type.length == 255

    def test_pin_image_url_type(self) -> None:
        """pin_image_url is String(2048)."""
        from sqlalchemy import String
        col = Article.__table__.columns["pin_image_url"]
        assert isinstance(col.type, String)
        assert col.type.length == 2048


# ===================================================================
# VAL-ART-005: Article model adds metadata fields
# ===================================================================


class TestArticleMetadataFields:
    """Verify metadata fields exist on Article model."""

    def test_category_name_exists(self) -> None:
        """category_name column exists."""
        assert "category_name" in Article.__table__.columns

    def test_generation_attempts_exists(self) -> None:
        """generation_attempts column exists."""
        assert "generation_attempts" in Article.__table__.columns

    def test_validation_errors_exists(self) -> None:
        """validation_errors column exists."""
        assert "validation_errors" in Article.__table__.columns

    def test_brain_output_exists(self) -> None:
        """brain_output column exists."""
        assert "brain_output" in Article.__table__.columns

    def test_category_name_type(self) -> None:
        """category_name is String(255), nullable."""
        from sqlalchemy import String
        col = Article.__table__.columns["category_name"]
        assert isinstance(col.type, String)
        assert col.type.length == 255
        assert col.nullable is True

    def test_generation_attempts_type_and_default(self) -> None:
        """generation_attempts is Integer, NOT NULL, default 0."""
        from sqlalchemy import Integer
        col = Article.__table__.columns["generation_attempts"]
        assert isinstance(col.type, Integer)
        assert col.nullable is False

    def test_validation_errors_type(self) -> None:
        """validation_errors is JSON, NOT NULL."""
        from sqlalchemy import JSON
        col = Article.__table__.columns["validation_errors"]
        assert isinstance(col.type, JSON)
        assert col.nullable is False

    def test_brain_output_type(self) -> None:
        """brain_output is JSON, nullable."""
        from sqlalchemy import JSON
        col = Article.__table__.columns["brain_output"]
        assert isinstance(col.type, JSON)
        assert col.nullable is True


# ===================================================================
# VAL-ART-006: Article run_id is now nullable
# ===================================================================


class TestArticleRunIdNullable:
    """Verify run_id is now nullable."""

    def test_run_id_nullable(self) -> None:
        """run_id column has nullable=True."""
        assert Article.__table__.columns["run_id"].nullable is True

    @pytest.mark.asyncio
    async def test_article_without_run(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Article can be created with run_id=None."""
        article = Article(
            blog_id=blog_in_db.id,
            run_id=None,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.run_id is None


# ===================================================================
# VAL-ART-007: Article blog_id FK relationship works
# ===================================================================


class TestArticleBlogRelationship:
    """Verify blog_id FK relationship resolves to parent Blog."""

    @pytest.mark.asyncio
    async def test_blog_relationship_resolves(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """article.blog resolves to the parent Blog object."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.blog is not None
        assert article.blog.id == blog_in_db.id

    @pytest.mark.asyncio
    async def test_blog_backref_articles(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Blog has an 'articles' backref containing related articles."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        # Use expire_on_commit=False + refresh with selectin loading
        await db_session.refresh(blog_in_db, ["articles"])
        assert len(blog_in_db.articles) >= 1
        assert blog_in_db.articles[0].keyword == "test keyword"


# ===================================================================
# VAL-ART-008: Article validation_errors stores list
# ===================================================================


class TestArticleValidationErrors:
    """Verify validation_errors stores and retrieves a list."""

    @pytest.mark.asyncio
    async def test_validation_errors_stores_list(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Setting validation_errors to a list persists and retrieves correctly."""
        errors = ["word count too low", "missing keyword"]
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
            validation_errors=errors,
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.validation_errors == errors
        assert isinstance(article.validation_errors, list)

    @pytest.mark.asyncio
    async def test_validation_errors_default_empty_list(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default validation_errors is an empty list."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.validation_errors == []


# ===================================================================
# VAL-ART-009: Article brain_output stores nested JSON
# ===================================================================


class TestArticleBrainOutput:
    """Verify brain_output stores and retrieves nested JSON."""

    @pytest.mark.asyncio
    async def test_brain_output_stores_nested_json(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Setting brain_output to a nested dict persists and retrieves correctly."""
        brain = {"keywords": [{"title": "k1", "score": 3}]}
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
            brain_output=brain,
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.brain_output == brain
        assert article.brain_output["keywords"][0]["title"] == "k1"

    @pytest.mark.asyncio
    async def test_brain_output_default_none(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Default brain_output is None."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.brain_output is None


# ===================================================================
# VAL-ART-010: Article generation_attempts defaults to 0
# ===================================================================


class TestArticleGenerationAttempts:
    """Verify generation_attempts defaults to 0."""

    @pytest.mark.asyncio
    async def test_generation_attempts_default(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Creating an Article without specifying generation_attempts yields 0."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.generation_attempts == 0

    @pytest.mark.asyncio
    async def test_generation_attempts_explicit(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
    ) -> None:
        """Creating an Article with explicit generation_attempts stores the value."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
            generation_attempts=3,
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        assert article.generation_attempts == 3


# ===================================================================
# VAL-ART-011: Article API returns new fields
# ===================================================================


class TestArticleAPIReturnsNewFields:
    """Verify GET /api/v1/articles/{id} returns all new fields."""

    @pytest_asyncio.fixture()
    async def article_with_all_fields(
        self,
        db_session: AsyncSession,
        blog_in_db: Blog,
        run_in_db: Run,
    ) -> Article:
        """Create an Article with all new fields populated."""
        article = Article(
            blog_id=blog_in_db.id,
            run_id=run_in_db.id,
            keyword="test keyword",
            title="Test Article Title",
            status="pending",
            # Content fields
            seo_title="SEO Title for Article",
            meta_description="A meta description for the article.",
            focus_keyword="test keyword",
            content_markdown="# Test\n\nContent here.",
            content_html="<h1>Test</h1><p>Content here.</p>",
            # Image fields
            hero_image_prompt="A beautiful landscape",
            hero_image_url="https://example.com/hero.jpg",
            detail_image_prompt="A detailed shot",
            detail_image_url="https://example.com/detail.jpg",
            # Pinterest fields
            pin_title="Pin Title",
            pin_description="Pin description text.",
            pin_text_overlay="Short overlay",
            pin_image_url="https://example.com/pin.jpg",
            # Metadata fields
            category_name="Outdoor Living",
            generation_attempts=2,
            validation_errors=["word count too low"],
            brain_output={"primary_keyword": "test", "score": 5},
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)
        return article

    async def test_api_returns_blog_id(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes blog_id."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        assert resp.status_code == 200
        assert resp.json()["blog_id"] == str(article_with_all_fields.blog_id)

    async def test_api_returns_content_fields(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes all content fields."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        assert data["seo_title"] == "SEO Title for Article"
        assert data["meta_description"] == "A meta description for the article."
        assert data["focus_keyword"] == "test keyword"
        assert data["content_markdown"] == "# Test\n\nContent here."
        assert data["content_html"] == "<h1>Test</h1><p>Content here.</p>"

    async def test_api_returns_image_fields(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes all image fields."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        assert data["hero_image_prompt"] == "A beautiful landscape"
        assert data["hero_image_url"] == "https://example.com/hero.jpg"
        assert data["detail_image_prompt"] == "A detailed shot"
        assert data["detail_image_url"] == "https://example.com/detail.jpg"

    async def test_api_returns_pinterest_fields(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes all Pinterest fields."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        assert data["pin_title"] == "Pin Title"
        assert data["pin_description"] == "Pin description text."
        assert data["pin_text_overlay"] == "Short overlay"
        assert data["pin_image_url"] == "https://example.com/pin.jpg"

    async def test_api_returns_metadata_fields(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes all metadata fields."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        assert data["category_name"] == "Outdoor Living"
        assert data["generation_attempts"] == 2
        assert data["validation_errors"] == ["word count too low"]
        assert data["brain_output"] == {"primary_keyword": "test", "score": 5}

    async def test_api_returns_run_id(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response includes run_id."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        assert data["run_id"] == str(article_with_all_fields.run_id)

    async def test_api_returns_null_run_id_when_no_run(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """API response shows run_id as null when article has no run."""
        article = Article(
            blog_id=blog_in_db.id,
            run_id=None,
            keyword="standalone keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)

        resp = await client.get(f"/api/v1/articles/{article.id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] is None

    async def test_api_returns_defaults_for_new_article(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        blog_in_db: Blog,
    ) -> None:
        """API response shows defaults for unset fields."""
        article = Article(
            blog_id=blog_in_db.id,
            keyword="test keyword",
        )
        db_session.add(article)
        await db_session.flush()
        await db_session.refresh(article)

        resp = await client.get(f"/api/v1/articles/{article.id}")
        data = resp.json()
        assert data["generation_attempts"] == 0
        assert data["validation_errors"] == []
        assert data["brain_output"] is None
        assert data["seo_title"] is None
        assert data["category_name"] is None

    async def test_api_all_new_field_keys_present(
        self,
        client: AsyncClient,
        article_with_all_fields: Article,
    ) -> None:
        """API response JSON contains all expected keys."""
        resp = await client.get(f"/api/v1/articles/{article_with_all_fields.id}")
        data = resp.json()
        expected_keys = {
            "blog_id",
            "seo_title", "meta_description", "focus_keyword",
            "content_markdown", "content_html",
            "hero_image_prompt", "hero_image_url",
            "detail_image_prompt", "detail_image_url",
            "pin_title", "pin_description", "pin_text_overlay", "pin_image_url",
            "category_name", "generation_attempts",
            "validation_errors", "brain_output",
        }
        assert expected_keys.issubset(set(data.keys()))


# ===================================================================
# Existing tests (updated for new schema)
# ===================================================================


class TestListArticles:
    """Tests for GET /api/v1/articles."""

    async def test_list_articles_returns_200(self, client: AsyncClient) -> None:
        """Listing articles should return HTTP 200."""
        resp = await client.get("/api/v1/articles")
        assert resp.status_code == 200

    async def test_list_articles_empty(self, client: AsyncClient) -> None:
        """With no articles, the response should be an empty list."""
        resp = await client.get("/api/v1/articles")
        assert resp.json() == []

    async def test_list_articles_returns_list(self, client: AsyncClient) -> None:
        """Response should be a JSON array."""
        resp = await client.get("/api/v1/articles")
        assert isinstance(resp.json(), list)


class TestGetArticle:
    """Tests for GET /api/v1/articles/{article_id}."""

    async def test_get_nonexistent_article_returns_404(self, client: AsyncClient) -> None:
        """Requesting a non-existent article should return 404."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/articles/{fake_id}")
        assert resp.status_code == 404

    async def test_get_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Passing an invalid UUID should return 422."""
        resp = await client.get("/api/v1/articles/not-a-uuid")
        assert resp.status_code == 422
