"""WordPress REST API provider implementation.

Uses ``httpx.AsyncClient`` with HTTP Basic Auth for authentication
against the WordPress REST API v2.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.providers.base import (
    WPMediaResult,
    WPPostResult,
    WordPressProvider,
)

_API_PREFIX = "/wp-json/wp/v2"


class WPRestProvider(WordPressProvider):
    """Concrete WordPress provider using the WP REST API v2.

    Authentication uses HTTP Basic Auth with the WordPress application
    password format (``username:application_password`` encoded as Base64).

    Args:
        base_url: The WordPress site's base URL (e.g. ``https://blog.example.com``).
        username: WordPress username.
        password: WordPress application password.
        _transport: Internal parameter for injecting a mock transport in tests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._transport = _transport
        self._api_prefix = _API_PREFIX
        self._client: httpx.AsyncClient | None = None

        # Pre-compute Basic Auth header value
        credentials = f"{self._username}:{self._password}"
        self._auth_header = "Basic " + base64.b64encode(
            credentials.encode()
        ).decode()

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and cache the ``httpx.AsyncClient``."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": self._auth_header,
                },
                transport=self._transport,
                timeout=30.0,
            )
        return self._client

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    async def create_post(
        self,
        title: str,
        content: str,
        *,
        status: str = "draft",
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: Any,
    ) -> WPPostResult:
        """Create a new WordPress post via the REST API.

        Args:
            title: Post title.
            content: Post body HTML.
            status: Publication status.
            categories: Category IDs.
            featured_media: Featured image media ID.
            **kwargs: Additional WP REST API fields.

        Returns:
            A :class:`WPPostResult` with the created post's details.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        body: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if categories is not None:
            body["categories"] = categories
        if featured_media is not None:
            body["featured_media"] = featured_media
        body.update(kwargs)

        client = self._get_client()
        response = await client.post(f"{self._api_prefix}/posts", json=body)
        response.raise_for_status()

        data = response.json()
        return WPPostResult(
            id=data["id"],
            url=data.get("link", ""),
            status=data.get("status", "draft"),
            title=data.get("title", {}).get("rendered", ""),
        )

    async def update_post(
        self,
        post_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        categories: list[int] | None = None,
        featured_media: int | None = None,
        **kwargs: Any,
    ) -> WPPostResult:
        """Update an existing WordPress post via the REST API.

        Uses POST method (WordPress convention for updates).

        Args:
            post_id: The post ID to update.
            title: New title (if provided).
            content: New body HTML (if provided).
            status: New status (if provided).
            categories: New category IDs (if provided).
            featured_media: New featured image ID (if provided).
            **kwargs: Additional fields.

        Returns:
            A :class:`WPPostResult` with updated post details.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if content is not None:
            body["content"] = content
        if status is not None:
            body["status"] = status
        if categories is not None:
            body["categories"] = categories
        if featured_media is not None:
            body["featured_media"] = featured_media
        body.update(kwargs)

        client = self._get_client()
        response = await client.post(
            f"{self._api_prefix}/posts/{post_id}", json=body
        )
        response.raise_for_status()

        data = response.json()
        return WPPostResult(
            id=data["id"],
            url=data.get("link", ""),
            status=data.get("status", "draft"),
            title=data.get("title", {}).get("rendered", ""),
        )

    async def get_post(self, post_id: int) -> WPPostResult:
        """Retrieve a single WordPress post by ID.

        Args:
            post_id: The WordPress post ID.

        Returns:
            A :class:`WPPostResult` with the post's details.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        client = self._get_client()
        response = await client.get(f"{self._api_prefix}/posts/{post_id}")
        response.raise_for_status()

        data = response.json()
        return WPPostResult(
            id=data["id"],
            url=data.get("link", ""),
            status=data.get("status", "draft"),
            title=data.get("title", {}).get("rendered", ""),
        )

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    async def upload_media(
        self,
        file_data: bytes,
        filename: str,
        *,
        media_type: str = "image/jpeg",
        alt_text: str = "",
        title: str | None = None,
    ) -> WPMediaResult:
        """Upload a media file to WordPress.

        Args:
            file_data: Raw file bytes.
            filename: Name for the uploaded file.
            media_type: MIME type.
            alt_text: Alternative text.
            title: Optional media library title.

        Returns:
            A :class:`WPMediaResult` with the uploaded media details.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        # WordPress media upload uses multipart-like but actually
        # raw binary with Content-Disposition and Content-Type headers
        headers: dict[str, str] = {
            "Content-Type": media_type,
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if alt_text:
            headers["X-Alt-Text"] = alt_text
        if title:
            headers["X-Title"] = title

        client = self._get_client()
        response = await client.post(
            f"{self._api_prefix}/media",
            content=file_data,
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        return WPMediaResult(
            id=data["id"],
            url=data.get("source_url", ""),
            media_type=data.get("media_type", ""),
        )

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    async def list_categories(
        self,
        *,
        per_page: int = 100,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """List WordPress categories.

        Args:
            per_page: Maximum categories to return.
            search: Filter by name.

        Returns:
            A list of category dicts.

        Raises:
            httpx.HTTPStatusError: On non-2xx API responses.
        """
        params: dict[str, Any] = {"per_page": per_page}
        if search is not None:
            params["search"] = search

        client = self._get_client()
        response = await client.get(
            f"{self._api_prefix}/categories",
            params=params,
        )
        response.raise_for_status()

        return list(response.json())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
