"""PublisherService — WordPress publishing flow.

Converts markdown to HTML using the ``markdown`` library, uploads hero and
detail images via a WordPress provider, injects the detail image after the
first paragraph in the HTML body, creates a post with featured media,
categories, and SEO meta, and returns a :class:`PublishResult`.

Ported from ``src/automating_wf/wordpress/uploader.py`` but rewritten
cleanly against the new async provider architecture.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from pathlib import Path

import markdown as md_lib

from app.providers.base import WordPressProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishResult:
    """Structured result of a successful WordPress post creation.

    Attributes:
        wp_post_id: The WordPress post ID.
        wp_permalink: The public permalink URL of the published post.
    """

    wp_post_id: int
    wp_permalink: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PublishingError(RuntimeError):
    """Raised when the publishing flow fails."""


# ---------------------------------------------------------------------------
# Markdown → HTML conversion
# ---------------------------------------------------------------------------


def markdown_to_html(content_markdown: str) -> str:
    """Convert markdown content to well-formed HTML.

    Args:
        content_markdown: Raw markdown string.

    Returns:
        HTML string with proper tags (``<p>``, ``<h2>``, etc.).

    Raises:
        PublishingError: If the markdown content is empty.
    """
    if not isinstance(content_markdown, str) or not content_markdown.strip():
        raise PublishingError("Markdown content is empty.")

    html_content = md_lib.markdown(
        content_markdown.strip(),
        extensions=["extra", "nl2br"],
    )
    return html_content.strip()


# ---------------------------------------------------------------------------
# Detail image injection
# ---------------------------------------------------------------------------


def inject_detail_image_after_first_paragraph(
    content_html: str,
    detail_image_url: str,
    alt_text: str,
) -> str:
    """Insert a detail ``<img>`` element immediately after the first ``</p>``.

    If no ``</p>`` tag is found, the image is appended to the end of the HTML.

    Args:
        content_html: The HTML content body.
        detail_image_url: URL of the uploaded detail image.
        alt_text: Alternative text for the image.

    Returns:
        Modified HTML string with the detail image inserted.

    Raises:
        PublishingError: If the HTML content or image URL is empty.
    """
    if not isinstance(content_html, str) or not content_html.strip():
        raise PublishingError("HTML content is empty.")
    if not isinstance(detail_image_url, str) or not detail_image_url.strip():
        raise PublishingError("Detail image URL is empty.")

    escaped_url = html.escape(detail_image_url.strip(), quote=True)
    escaped_alt = html.escape(alt_text.strip(), quote=True) or "Detail image"
    detail_image_html = (
        f'\n<figure class="midnight-engine-detail">'
        f'<img src="{escaped_url}" alt="{escaped_alt}" loading="lazy" />'
        f"</figure>\n"
    )

    paragraph_end = content_html.find("</p>")
    if paragraph_end == -1:
        return content_html + detail_image_html

    insert_index = paragraph_end + len("</p>")
    return content_html[:insert_index] + detail_image_html + content_html[insert_index:]


# ---------------------------------------------------------------------------
# Alt text helpers
# ---------------------------------------------------------------------------


def _ensure_alt_text_has_focus_keyword(alt_text: str, focus_keyword: str) -> str:
    """Prepend the focus keyword to alt text if not already present."""
    keyword = str(focus_keyword or "").strip()
    base = str(alt_text or "").strip() or "Image"
    if not keyword:
        return base
    if keyword.casefold() in base.casefold():
        return base
    return f"{keyword} - {base}"


# ---------------------------------------------------------------------------
# PublisherService
# ---------------------------------------------------------------------------


class PublisherService:
    """WordPress publishing service.

    Converts markdown to HTML, uploads images, injects a detail image
    after the first paragraph, and creates a WordPress post with SEO meta.

    Parameters:
        provider: A :class:`WordPressProvider` instance for API operations.
    """

    def __init__(self, provider: WordPressProvider) -> None:
        self._provider = provider

    async def publish_article(
        self,
        *,
        title: str,
        content_markdown: str,
        hero_image_path: Path,
        detail_image_path: Path,
        focus_keyword: str,
        meta_description: str,
        seo_title: str,
        publish_status: str = "draft",
        categories: list[int] | None = None,
    ) -> PublishResult:
        """Publish an article to WordPress.

        Args:
            title: Post title.
            content_markdown: Article body in markdown format.
            hero_image_path: Local path to the hero image file.
            detail_image_path: Local path to the detail image file.
            focus_keyword: SEO focus keyword.
            meta_description: SEO meta description.
            seo_title: SEO title (Rank Math).
            publish_status: Publication status (``"draft"`` or ``"publish"``).
            categories: Optional list of WordPress category IDs.

        Returns:
            A :class:`PublishResult` with the WordPress post ID and permalink.

        Raises:
            PublishingError: If any step in the publishing flow fails.
        """
        # --- Validate inputs ---
        title = str(title or "").strip()
        if not title:
            raise PublishingError("Title is required.")
        content_markdown = str(content_markdown or "").strip()
        if not content_markdown:
            raise PublishingError("Content markdown is required.")
        focus_keyword = str(focus_keyword or "").strip()
        if not focus_keyword:
            raise PublishingError("Focus keyword is required.")

        hero_path = Path(hero_image_path)
        if not hero_path.exists():
            raise PublishingError(f"Hero image file not found: {hero_path}")

        detail_path = Path(detail_image_path)
        if not detail_path.exists():
            raise PublishingError(f"Detail image file not found: {detail_path}")

        # --- Convert markdown to HTML ---
        try:
            content_html = markdown_to_html(content_markdown)
        except PublishingError:
            raise
        except Exception as exc:
            raise PublishingError(f"Markdown conversion failed: {exc}") from exc

        logger.info("Converted markdown to HTML (%d chars)", len(content_html))

        # --- Upload hero image ---
        hero_alt_text = _ensure_alt_text_has_focus_keyword(
            alt_text=f"{title} hero image",
            focus_keyword=focus_keyword,
        )
        try:
            hero_media = await self._provider.upload_media(
                file_data=hero_path.read_bytes(),
                filename=hero_path.name,
                media_type="image/jpeg",
                alt_text=hero_alt_text,
            )
        except Exception as exc:
            logger.error("Hero image upload failed: %s", exc)
            raise PublishingError(f"Hero image upload failed: {exc}") from exc

        logger.info("Hero image uploaded: media_id=%d", hero_media.id)

        # --- Upload detail image ---
        detail_alt_text = _ensure_alt_text_has_focus_keyword(
            alt_text=f"{title} detail image",
            focus_keyword=focus_keyword,
        )
        try:
            detail_media = await self._provider.upload_media(
                file_data=detail_path.read_bytes(),
                filename=detail_path.name,
                media_type="image/jpeg",
                alt_text=detail_alt_text,
            )
        except Exception as exc:
            logger.error("Detail image upload failed: %s", exc)
            raise PublishingError(f"Detail image upload failed: {exc}") from exc

        logger.info("Detail image uploaded: media_id=%d", detail_media.id)

        # --- Inject detail image after first paragraph ---
        content_with_detail = inject_detail_image_after_first_paragraph(
            content_html=content_html,
            detail_image_url=detail_media.url,
            alt_text=detail_alt_text,
        )

        # --- Create WordPress post ---
        try:
            post_result = await self._provider.create_post(
                title=title,
                content=content_with_detail,
                status=publish_status.strip() or "draft",
                categories=categories,
                featured_media=hero_media.id,
                rank_math_title=str(seo_title or "").strip(),
                rank_math_description=str(meta_description or "").strip(),
                rank_math_focus_keyword=focus_keyword,
            )
        except Exception as exc:
            logger.error("Post creation failed: %s", exc)
            raise PublishingError(f"Post creation failed: {exc}") from exc

        logger.info(
            "Article published: post_id=%d, url=%s, status=%s",
            post_result.id,
            post_result.url,
            post_result.status,
        )

        return PublishResult(
            wp_post_id=post_result.id,
            wp_permalink=post_result.url,
        )
