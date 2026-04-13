"""Tests for Blog CRUD endpoints.

Fulfils:
- VAL-BLOG-001: Create blog with default pipeline config
- VAL-BLOG-002: List blogs (no decrypted secrets)
- VAL-BLOG-003: Get blog details (no decrypted secrets)
- VAL-BLOG-004: Update blog metadata
- VAL-BLOG-005: Soft-delete blog
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def blog_payload() -> dict[str, Any]:
    """Minimal valid blog creation payload."""
    return {
        "name": "Test Blog",
        "url": "https://testblog.com",
        "wp_username": "admin",
        "wp_application_password": "super-secret-password",
    }


@pytest_asyncio.fixture()
async def existing_blog(client: AsyncClient, blog_payload: dict[str, Any]) -> dict[str, Any]:
    """Create a blog via the API and return the response JSON."""
    response = await client.post("/api/v1/blogs", json=blog_payload)
    assert response.status_code == 201
    return dict(response.json())


# ---------------------------------------------------------------------------
# VAL-BLOG-001: Create Blog
# ---------------------------------------------------------------------------


class TestCreateBlog:
    """POST /api/v1/blogs creates blog with encrypted password."""

    @pytest.mark.asyncio
    async def test_create_blog_returns_201(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_blog_returns_id(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert "id" in data
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_blog_returns_name(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["name"] == blog_payload["name"]

    @pytest.mark.asyncio
    async def test_create_blog_returns_url(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["url"] == blog_payload["url"]

    @pytest.mark.asyncio
    async def test_create_blog_returns_slug(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert "slug" in data
        assert data["slug"] == "test-blog"

    @pytest.mark.asyncio
    async def test_create_blog_returns_masked_password(
        self, client: AsyncClient, blog_payload: dict[str, Any]
    ) -> None:
        """API must never return the plaintext password."""
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["wp_application_password"] == "********"

    @pytest.mark.asyncio
    async def test_create_blog_password_encrypted_in_db(
        self,
        client: AsyncClient,
        blog_payload: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """The stored value in the DB must be a Fernet token, not plaintext."""
        from app.models.blog import Blog

        response = await client.post("/api/v1/blogs", json=blog_payload)
        assert response.status_code == 201
        blog_id = uuid.UUID(response.json()["id"])

        result = await db_session.execute(select(Blog).where(Blog.id == blog_id))
        blog = result.scalar_one()
        # The encrypted column should not contain the plaintext password
        assert blog.wp_app_password_encrypted != blog_payload["wp_application_password"]
        # It should be a non-empty string
        assert len(blog.wp_app_password_encrypted) > 0

    @pytest.mark.asyncio
    async def test_create_blog_password_can_be_decrypted(
        self,
        client: AsyncClient,
        blog_payload: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """Verify the stored encrypted password can be decrypted back."""
        from app.crypto import decrypt
        from app.models.blog import Blog

        response = await client.post("/api/v1/blogs", json=blog_payload)
        blog_id = uuid.UUID(response.json()["id"])

        result = await db_session.execute(select(Blog).where(Blog.id == blog_id))
        blog = result.scalar_one()
        decrypted = decrypt(blog.wp_app_password_encrypted)
        assert decrypted == blog_payload["wp_application_password"]

    @pytest.mark.asyncio
    async def test_create_blog_returns_wp_username(
        self, client: AsyncClient, blog_payload: dict[str, Any]
    ) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["wp_username"] == "admin"

    @pytest.mark.asyncio
    async def test_create_blog_returns_timestamps(
        self, client: AsyncClient, blog_payload: dict[str, Any]
    ) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_blog_default_is_active(
        self, client: AsyncClient, blog_payload: dict[str, Any]
    ) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_duplicate_slug_returns_409(
        self, client: AsyncClient, blog_payload: dict[str, Any]
    ) -> None:
        """Creating a blog with a name that produces the same slug should fail."""
        response1 = await client.post("/api/v1/blogs", json=blog_payload)
        assert response1.status_code == 201

        response2 = await client.post("/api/v1/blogs", json=blog_payload)
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_blog_missing_name_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/blogs",
            json={
                "url": "https://testblog.com",
                "wp_username": "admin",
                "wp_application_password": "secret",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_blog_missing_url_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/blogs",
            json={
                "name": "Test Blog",
                "wp_username": "admin",
                "wp_application_password": "secret",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_blog_slug_auto_generated_from_name(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/blogs",
            json={
                "name": "My Fancy Blog!",
                "url": "https://myfancy.com",
                "wp_username": "admin",
                "wp_application_password": "secret",
            },
        )
        data = response.json()
        assert data["slug"] == "my-fancy-blog"


# ---------------------------------------------------------------------------
# VAL-BLOG-002: List Blogs (No Decrypted Secrets)
# ---------------------------------------------------------------------------


class TestListBlogs:
    """GET /api/v1/blogs returns blog list without password."""

    @pytest.mark.asyncio
    async def test_list_blogs_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/blogs")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_blogs_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/blogs")
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_blogs_returns_created_blogs(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.get("/api/v1/blogs")
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == existing_blog["id"]

    @pytest.mark.asyncio
    async def test_list_blogs_masks_password(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Password must never appear in plaintext in list responses."""
        response = await client.get("/api/v1/blogs")
        data = response.json()
        for blog in data:
            assert blog["wp_application_password"] == "********"

    @pytest.mark.asyncio
    async def test_list_blogs_excludes_soft_deleted(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Soft-deleted blogs should not appear in the list."""
        blog_id = existing_blog["id"]
        await client.delete(f"/api/v1/blogs/{blog_id}")

        response = await client.get("/api/v1/blogs")
        assert response.json() == []


# ---------------------------------------------------------------------------
# VAL-BLOG-003: Get Blog Details (No Decrypted Secrets)
# ---------------------------------------------------------------------------


class TestGetBlog:
    """GET /api/v1/blogs/{id} returns blog details with masked password."""

    @pytest.mark.asyncio
    async def test_get_blog_returns_200(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.get(f"/api/v1/blogs/{existing_blog['id']}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_blog_returns_correct_data(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.get(f"/api/v1/blogs/{existing_blog['id']}")
        data = response.json()
        assert data["id"] == existing_blog["id"]
        assert data["name"] == "Test Blog"
        assert data["url"] == "https://testblog.com"

    @pytest.mark.asyncio
    async def test_get_blog_masks_password(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Password must be masked in detail responses."""
        response = await client.get(f"/api/v1/blogs/{existing_blog['id']}")
        data = response.json()
        assert data["wp_application_password"] == "********"

    @pytest.mark.asyncio
    async def test_get_nonexistent_blog_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/blogs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_soft_deleted_blog_returns_404(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        blog_id = existing_blog["id"]
        await client.delete(f"/api/v1/blogs/{blog_id}")

        response = await client.get(f"/api/v1/blogs/{blog_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# VAL-BLOG-004: Update Blog Metadata
# ---------------------------------------------------------------------------


class TestUpdateBlog:
    """PATCH /api/v1/blogs/{id} updates blog metadata."""

    @pytest.mark.asyncio
    async def test_update_blog_returns_200(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"name": "Updated Blog Name"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_blog_name(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"name": "Updated Blog Name"},
        )
        data = response.json()
        assert data["name"] == "Updated Blog Name"

    @pytest.mark.asyncio
    async def test_update_blog_url(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"url": "https://updated-url.com"},
        )
        data = response.json()
        assert data["url"] == "https://updated-url.com"

    @pytest.mark.asyncio
    async def test_update_blog_password(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Updating the password should re-encrypt and return masked."""
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"wp_application_password": "new-secret-password"},
        )
        data = response.json()
        assert data["wp_application_password"] == "********"

    @pytest.mark.asyncio
    async def test_update_blog_password_persists_encrypted(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """Updating the password should encrypt the new value in the DB."""
        from app.crypto import decrypt
        from app.models.blog import Blog

        new_password = "new-secret-password"
        await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"wp_application_password": new_password},
        )

        result = await db_session.execute(
            select(Blog).where(Blog.id == uuid.UUID(existing_blog["id"]))
        )
        blog = result.scalar_one()
        assert decrypt(blog.wp_app_password_encrypted) == new_password

    @pytest.mark.asyncio
    async def test_update_nonexistent_blog_returns_404(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/v1/blogs/00000000-0000-0000-0000-000000000000",
            json={"name": "Ghost Blog"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_blog_slug_regenerated_on_name_change(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Slug should be auto-regenerated when name is updated."""
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"name": "Completely New Name"},
        )
        data = response.json()
        assert data["slug"] == "completely-new-name"

    @pytest.mark.asyncio
    async def test_update_blog_updates_timestamp(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """The updated_at timestamp should change after an update."""
        import asyncio

        original_updated_at = existing_blog["updated_at"]
        # Small sleep to ensure timestamp differs
        await asyncio.sleep(0.05)

        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"name": "Time Check Blog"},
        )
        data = response.json()
        assert data["updated_at"] != original_updated_at


# ---------------------------------------------------------------------------
# VAL-BLOG-005: Soft-Delete Blog
# ---------------------------------------------------------------------------


class TestDeleteBlog:
    """DELETE /api/v1/blogs/{id} performs soft-delete."""

    @pytest.mark.asyncio
    async def test_delete_blog_returns_204(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.delete(f"/api/v1/blogs/{existing_blog['id']}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_blog_sets_inactive_in_db(
        self,
        client: AsyncClient,
        existing_blog: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        """Soft delete must set is_active=False and deleted_at in the DB."""
        from app.models.blog import Blog

        blog_id = uuid.UUID(existing_blog["id"])
        await client.delete(f"/api/v1/blogs/{blog_id}")

        result = await db_session.execute(select(Blog).where(Blog.id == blog_id))
        blog = result.scalar_one()
        assert blog.is_active is False
        assert blog.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_blog_returns_404(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/blogs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_blog_already_deleted_returns_404(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        blog_id = existing_blog["id"]
        await client.delete(f"/api/v1/blogs/{blog_id}")

        # Deleting again should return 404 (already inactive)
        response = await client.delete(f"/api/v1/blogs/{blog_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_blog_not_in_list(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        """Deleted blogs should not appear in list endpoint."""
        blog_id = existing_blog["id"]
        await client.delete(f"/api/v1/blogs/{blog_id}")

        response = await client.get("/api/v1/blogs")
        assert response.json() == []


# ---------------------------------------------------------------------------
# VAL-BLOG-001: Blog model exposes new fields as columns
# ---------------------------------------------------------------------------


class TestBlogModelColumns:
    """Verify Blog ORM model has all 6 new columns with correct types and defaults."""

    def test_blog_has_profile_prompt_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["profile_prompt"]
        assert col is not None
        assert not col.nullable

    def test_blog_has_fallback_category_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["fallback_category"]
        assert col is not None
        assert not col.nullable

    def test_blog_has_deprioritized_category_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["deprioritized_category"]
        assert col is not None
        assert not col.nullable

    def test_blog_has_category_keywords_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["category_keywords"]
        assert col is not None
        assert not col.nullable

    def test_blog_has_pinterest_board_map_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["pinterest_board_map"]
        assert col is not None
        assert not col.nullable

    def test_blog_has_seed_keywords_column(self) -> None:
        from app.models.blog import Blog

        col = Blog.__table__.columns["seed_keywords"]
        assert col is not None
        assert not col.nullable


# ---------------------------------------------------------------------------
# VAL-BLOG-002: Blog model stores and retrieves JSON nested structures
# ---------------------------------------------------------------------------


class TestBlogJSONFields:
    """Verify JSON fields store and retrieve nested structures."""

    @pytest.mark.asyncio
    async def test_category_keywords_stores_nested_structure(
        self, db_session: AsyncSession
    ) -> None:
        from app.models.blog import Blog

        nested = {"outdoor": ["patio", "deck"], "indoor": ["kitchen", "bathroom"]}
        blog = Blog(
            name="JSON Test",
            slug="json-test",
            url="https://json-test.com",
            wp_username="admin",
            wp_app_password_encrypted="encrypted",
            category_keywords=nested,
        )
        db_session.add(blog)
        await db_session.flush()
        await db_session.refresh(blog)
        assert blog.category_keywords == nested

    @pytest.mark.asyncio
    async def test_pinterest_board_map_stores_nested_structure(
        self, db_session: AsyncSession
    ) -> None:
        from app.models.blog import Blog

        board_map = {"home": "board-123", "garden": "board-456"}
        blog = Blog(
            name="Board Map Test",
            slug="board-map-test",
            url="https://board-test.com",
            wp_username="admin",
            wp_app_password_encrypted="encrypted",
            pinterest_board_map=board_map,
        )
        db_session.add(blog)
        await db_session.flush()
        await db_session.refresh(blog)
        assert blog.pinterest_board_map == board_map

    @pytest.mark.asyncio
    async def test_seed_keywords_stores_list_of_strings(
        self, db_session: AsyncSession
    ) -> None:
        from app.models.blog import Blog

        keywords = ["keyword1", "keyword2", "keyword3"]
        blog = Blog(
            name="Keywords Test",
            slug="keywords-test",
            url="https://kw-test.com",
            wp_username="admin",
            wp_app_password_encrypted="encrypted",
            seed_keywords=keywords,
        )
        db_session.add(blog)
        await db_session.flush()
        await db_session.refresh(blog)
        assert blog.seed_keywords == keywords


# ---------------------------------------------------------------------------
# VAL-BLOG-003: Blog API POST accepts new fields
# ---------------------------------------------------------------------------


class TestCreateBlogNewFields:
    """POST /api/v1/blogs accepts the 6 new fields and returns them."""

    @pytest.mark.asyncio
    async def test_create_blog_with_all_new_fields_returns_201(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Full Fields Blog",
            "url": "https://fullfields.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "profile_prompt": "Write about outdoor living",
            "fallback_category": "Home & Garden",
            "deprioritized_category": "Spam Category",
            "category_keywords": {"outdoor": ["patio", "deck"]},
            "pinterest_board_map": {"home": "board-123"},
            "seed_keywords": ["patio furniture", "outdoor decor"],
        }
        response = await client.post("/api/v1/blogs", json=payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_blog_returns_profile_prompt(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Prompt Blog",
            "url": "https://prompt.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "profile_prompt": "Write about outdoor living",
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["profile_prompt"] == "Write about outdoor living"

    @pytest.mark.asyncio
    async def test_create_blog_returns_fallback_category(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Fallback Blog",
            "url": "https://fallback.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "fallback_category": "Home & Garden",
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["fallback_category"] == "Home & Garden"

    @pytest.mark.asyncio
    async def test_create_blog_returns_deprioritized_category(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Depri Blog",
            "url": "https://depri.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "deprioritized_category": "Spam Category",
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["deprioritized_category"] == "Spam Category"

    @pytest.mark.asyncio
    async def test_create_blog_returns_category_keywords(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "CatKw Blog",
            "url": "https://catkw.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "category_keywords": {"outdoor": ["patio", "deck"]},
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["category_keywords"] == {"outdoor": ["patio", "deck"]}

    @pytest.mark.asyncio
    async def test_create_blog_returns_pinterest_board_map(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Board Blog",
            "url": "https://board.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "pinterest_board_map": {"home": "board-123"},
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["pinterest_board_map"] == {"home": "board-123"}

    @pytest.mark.asyncio
    async def test_create_blog_returns_seed_keywords(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Seed Blog",
            "url": "https://seed.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "seed_keywords": ["patio furniture", "outdoor decor"],
        }
        response = await client.post("/api/v1/blogs", json=payload)
        data = response.json()
        assert data["seed_keywords"] == ["patio furniture", "outdoor decor"]


# ---------------------------------------------------------------------------
# VAL-BLOG-004: Blog API POST applies defaults when new fields omitted
# ---------------------------------------------------------------------------


class TestCreateBlogDefaults:
    """POST /api/v1/blogs applies defaults when new fields are omitted."""

    @pytest.mark.asyncio
    async def test_default_profile_prompt(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["profile_prompt"] == ""

    @pytest.mark.asyncio
    async def test_default_fallback_category(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["fallback_category"] == ""

    @pytest.mark.asyncio
    async def test_default_deprioritized_category(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["deprioritized_category"] == ""

    @pytest.mark.asyncio
    async def test_default_category_keywords(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["category_keywords"] == {}

    @pytest.mark.asyncio
    async def test_default_pinterest_board_map(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["pinterest_board_map"] == {}

    @pytest.mark.asyncio
    async def test_default_seed_keywords(self, client: AsyncClient, blog_payload: dict[str, Any]) -> None:
        response = await client.post("/api/v1/blogs", json=blog_payload)
        data = response.json()
        assert data["seed_keywords"] == []


# ---------------------------------------------------------------------------
# VAL-BLOG-005: Blog API GET returns new fields
# ---------------------------------------------------------------------------


class TestGetBlogNewFields:
    """GET /api/v1/blogs/{id} returns all 6 new fields."""

    @pytest.mark.asyncio
    async def test_get_blog_returns_all_new_fields(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Get Fields Blog",
            "url": "https://getfields.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "profile_prompt": "Test prompt",
            "fallback_category": "Test Category",
            "deprioritized_category": "Spam",
            "category_keywords": {"k1": ["a", "b"]},
            "pinterest_board_map": {"board1": "id-1"},
            "seed_keywords": ["kw1", "kw2"],
        }
        create_resp = await client.post("/api/v1/blogs", json=payload)
        blog_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/blogs/{blog_id}")
        data = response.json()
        assert "profile_prompt" in data
        assert "fallback_category" in data
        assert "deprioritized_category" in data
        assert "category_keywords" in data
        assert "pinterest_board_map" in data
        assert "seed_keywords" in data
        assert data["profile_prompt"] == "Test prompt"
        assert data["fallback_category"] == "Test Category"
        assert data["deprioritized_category"] == "Spam"
        assert data["category_keywords"] == {"k1": ["a", "b"]}
        assert data["pinterest_board_map"] == {"board1": "id-1"}
        assert data["seed_keywords"] == ["kw1", "kw2"]


# ---------------------------------------------------------------------------
# VAL-BLOG-006: Blog API PATCH updates new fields individually
# ---------------------------------------------------------------------------


class TestPatchBlogNewFields:
    """PATCH /api/v1/blogs/{id} updates new fields individually."""

    @pytest.mark.asyncio
    async def test_patch_profile_prompt_only(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"profile_prompt": "Write about outdoor living"},
        )
        data = response.json()
        assert data["profile_prompt"] == "Write about outdoor living"
        # Other fields should remain at defaults
        assert data["fallback_category"] == ""
        assert data["deprioritized_category"] == ""
        assert data["category_keywords"] == {}
        assert data["pinterest_board_map"] == {}
        assert data["seed_keywords"] == []

    @pytest.mark.asyncio
    async def test_patch_fallback_category_only(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"fallback_category": "Home & Garden"},
        )
        data = response.json()
        assert data["fallback_category"] == "Home & Garden"

    @pytest.mark.asyncio
    async def test_patch_deprioritized_category_only(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"deprioritized_category": "Spam"},
        )
        data = response.json()
        assert data["deprioritized_category"] == "Spam"


# ---------------------------------------------------------------------------
# VAL-BLOG-007: Blog API PATCH updates JSON fields
# ---------------------------------------------------------------------------


class TestPatchBlogJSONFields:
    """PATCH /api/v1/blogs/{id} updates JSON fields."""

    @pytest.mark.asyncio
    async def test_patch_category_keywords(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        new_kw = {"k1": ["a", "b"]}
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"category_keywords": new_kw},
        )
        data = response.json()
        assert data["category_keywords"] == new_kw

        # Verify via GET
        get_resp = await client.get(f"/api/v1/blogs/{existing_blog['id']}")
        assert get_resp.json()["category_keywords"] == new_kw

    @pytest.mark.asyncio
    async def test_patch_pinterest_board_map(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        new_map = {"home": "board-123"}
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"pinterest_board_map": new_map},
        )
        data = response.json()
        assert data["pinterest_board_map"] == new_map

    @pytest.mark.asyncio
    async def test_patch_seed_keywords(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        new_kw = ["keyword1", "keyword2"]
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"seed_keywords": new_kw},
        )
        data = response.json()
        assert data["seed_keywords"] == new_kw


# ---------------------------------------------------------------------------
# VAL-BLOG-008: BlogCreate validates new field types
# ---------------------------------------------------------------------------


class TestBlogCreateValidation:
    """BlogCreate schema validates field types (422 on bad input)."""

    @pytest.mark.asyncio
    async def test_invalid_seed_keywords_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Invalid Blog",
            "url": "https://invalid.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "seed_keywords": "not a list",
        }
        response = await client.post("/api/v1/blogs", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_category_keywords_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Invalid Blog",
            "url": "https://invalid.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "category_keywords": "not a dict",
        }
        response = await client.post("/api/v1/blogs", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_pinterest_board_map_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Invalid Blog",
            "url": "https://invalid.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "pinterest_board_map": [1, 2, 3],
        }
        response = await client.post("/api/v1/blogs", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_profile_prompt_type_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {
            "name": "Invalid Blog",
            "url": "https://invalid.com",
            "wp_username": "admin",
            "wp_application_password": "secret",
            "profile_prompt": 12345,
        }
        response = await client.post("/api/v1/blogs", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# VAL-BLOG-009: BlogUpdate validates new field types
# ---------------------------------------------------------------------------


class TestBlogUpdateValidation:
    """BlogUpdate schema validates new field types on partial updates."""

    @pytest.mark.asyncio
    async def test_patch_invalid_category_keywords_type_returns_422(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"category_keywords": "not a dict"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_invalid_seed_keywords_type_returns_422(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"seed_keywords": "not a list"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_invalid_pinterest_board_map_type_returns_422(
        self, client: AsyncClient, existing_blog: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/blogs/{existing_blog['id']}",
            json={"pinterest_board_map": "not a dict"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# VAL-BLOG-010: BlogResponse includes new fields
# ---------------------------------------------------------------------------


class TestBlogResponseFields:
    """BlogResponse serialises all 6 new fields."""

    @pytest.mark.asyncio
    async def test_response_model_contains_all_new_keys(
        self, db_session: AsyncSession
    ) -> None:
        from app.models.blog import Blog
        from app.schemas.blog import BlogResponse

        blog = Blog(
            name="Schema Test",
            slug="schema-test",
            url="https://schema-test.com",
            wp_username="admin",
            wp_app_password_encrypted="encrypted",
            profile_prompt="test prompt",
            fallback_category="fc",
            deprioritized_category="dc",
            category_keywords={"k": ["v"]},
            pinterest_board_map={"b": "id"},
            seed_keywords=["kw"],
        )
        db_session.add(blog)
        await db_session.flush()
        await db_session.refresh(blog)

        response = BlogResponse.model_validate(blog)
        data = response.model_dump()
        assert "profile_prompt" in data
        assert "fallback_category" in data
        assert "deprioritized_category" in data
        assert "category_keywords" in data
        assert "pinterest_board_map" in data
        assert "seed_keywords" in data
        assert data["profile_prompt"] == "test prompt"
        assert data["category_keywords"] == {"k": ["v"]}
        assert data["seed_keywords"] == ["kw"]
