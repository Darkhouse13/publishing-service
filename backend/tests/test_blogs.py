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
