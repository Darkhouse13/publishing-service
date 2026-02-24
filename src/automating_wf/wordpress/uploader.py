from __future__ import annotations

import html
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


class WordPressUploadError(RuntimeError):
    """Raised when WordPress upload/publish operations fail."""


_ATX_H1_PATTERN = re.compile(r"^\s{0,3}#(?!#)\s*(?P<text>.*?)\s*#*\s*$")
_SETEXT_H1_UNDERLINE_PATTERN = re.compile(r"^\s{0,3}=+\s*$")
CROSS_BLOG_LINK_MAP_ENV = "CROSS_BLOG_LINK_MAP_JSON"
SEO_EXTERNAL_SOURCES_ENV = "SEO_EXTERNAL_SOURCES_JSON"
MAX_CROSS_BLOG_BACKLINKS = 3
SISTER_BLOG_FALLBACK_ANCHOR = "Explore a guide on our sister blog"
POST_SLUG_MAX_LENGTH = 60


def _normalize_heading_match_text(value: str) -> str:
    collapsed = " ".join(html.unescape(value).split()).casefold()
    return "".join(char for char in collapsed if char.isalnum())


def strip_duplicate_leading_h1(content_markdown: str, title: str) -> tuple[str, bool]:
    if not isinstance(content_markdown, str) or not content_markdown.strip():
        return content_markdown, False

    normalized_title = _normalize_heading_match_text(title or "")
    if not normalized_title:
        return content_markdown, False

    lines = content_markdown.splitlines(keepends=True)
    first_non_empty_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip():
            first_non_empty_index = index
            break
    if first_non_empty_index is None:
        return content_markdown, False

    heading_text = ""
    removal_end = first_non_empty_index
    first_line = lines[first_non_empty_index]

    atx_match = _ATX_H1_PATTERN.match(first_line)
    if atx_match:
        heading_text = atx_match.group("text")
        removal_end = first_non_empty_index + 1
    elif first_non_empty_index + 1 < len(lines):
        underline_line = lines[first_non_empty_index + 1]
        if first_line.strip() and _SETEXT_H1_UNDERLINE_PATTERN.match(underline_line):
            heading_text = first_line.strip()
            removal_end = first_non_empty_index + 2

    if not heading_text:
        return content_markdown, False

    normalized_heading = _normalize_heading_match_text(heading_text)
    if normalized_heading != normalized_title:
        return content_markdown, False

    while removal_end < len(lines) and not lines[removal_end].strip():
        removal_end += 1

    sanitized = "".join(lines[:first_non_empty_index] + lines[removal_end:])
    return sanitized, True


def _normalized_domain(url: str) -> str:
    parsed = urlparse((url or "").strip())
    netloc = parsed.netloc.strip().lower()
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _load_cross_blog_link_map() -> tuple[dict[str, str], list[str]]:
    load_dotenv()
    warnings: list[str] = []
    raw_mapping = os.getenv(CROSS_BLOG_LINK_MAP_ENV, "").strip()
    if not raw_mapping:
        warnings.append(
            f"{CROSS_BLOG_LINK_MAP_ENV} is missing; skipping cross-blog backlink injection."
        )
        return {}, warnings

    try:
        parsed = json.loads(raw_mapping)
    except json.JSONDecodeError:
        warnings.append(
            f"{CROSS_BLOG_LINK_MAP_ENV} is not valid JSON; skipping cross-blog backlink injection."
        )
        return {}, warnings

    if not isinstance(parsed, dict):
        warnings.append(
            f"{CROSS_BLOG_LINK_MAP_ENV} must be a JSON object; skipping cross-blog backlink injection."
        )
        return {}, warnings

    cleaned: dict[str, str] = {}
    for trigger, url in parsed.items():
        if not isinstance(trigger, str) or not trigger.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        normalized_url = url.strip()
        if not (normalized_url.startswith("http://") or normalized_url.startswith("https://")):
            warnings.append(
                f"Skipping trigger '{trigger.strip()}': mapped URL must start with http:// or https://."
            )
            continue
        cleaned[trigger.strip()] = normalized_url

    return cleaned, warnings


def _is_plain_paragraph_block(block_text: str) -> bool:
    stripped = block_text.strip()
    if not stripped:
        return False

    first_line = ""
    for line in block_text.splitlines():
        if line.strip():
            first_line = line.lstrip()
            break
    if not first_line:
        return False

    if first_line.startswith("#") or first_line.startswith(">") or first_line.startswith("|"):
        return False
    if re.match(r"^([-*+]\s+|\d+[.)]\s+)", first_line):
        return False
    if re.match(r"^\s{4,}\S", first_line):
        return False

    # Skip blocks that already contain links or images.
    if re.search(r"!\[[^\]]*\]\([^)]+\)", block_text):
        return False
    if re.search(r"\[[^\]]+\]\([^)]+\)", block_text):
        return False
    return True


def _inject_triggers_into_paragraph(
    paragraph: str,
    trigger_map: dict[str, str],
    replaced_triggers: set[str],
    remaining_slots: int,
) -> tuple[str, int]:
    if remaining_slots <= 0:
        return paragraph, 0

    updated = paragraph
    inserted = 0
    ordered_triggers = sorted(trigger_map.keys(), key=len, reverse=True)
    for trigger in ordered_triggers:
        if inserted >= remaining_slots:
            break
        if trigger in replaced_triggers:
            continue
        url = trigger_map[trigger]
        pattern = re.compile(
            rf"(?<![A-Za-z0-9])({re.escape(trigger)})(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        if not pattern.search(updated):
            continue
        updated = pattern.sub(
            lambda match: f"[{match.group(1)}]({url})",
            updated,
            count=1,
        )
        replaced_triggers.add(trigger)
        inserted += 1
    return updated, inserted


def _has_sibling_domain_link(article_markdown: str, sibling_domains: set[str]) -> bool:
    for url in _extract_markdown_links(article_markdown):
        domain = _normalized_domain(url)
        if domain and domain in sibling_domains:
            return True
    return False


def _select_fallback_sibling_url(trigger_map: dict[str, str]) -> str:
    ordered: list[tuple[str, str, str]] = []
    for trigger, url in trigger_map.items():
        domain = _normalized_domain(url)
        if not domain:
            continue
        ordered.append((domain, trigger.casefold(), url))
    if not ordered:
        return ""
    ordered.sort(key=lambda item: (item[0], item[1], item[2]))
    return ordered[0][2]


def _append_fallback_sibling_link(article_markdown: str, fallback_url: str) -> str:
    updated_markdown = article_markdown.rstrip()
    fallback_line = f"[{SISTER_BLOG_FALLBACK_ANCHOR}]({fallback_url})"
    if updated_markdown:
        return f"{updated_markdown}\n\n{fallback_line}"
    return fallback_line


def inject_cross_blog_backlinks(
    article_markdown: str,
    target_suffix: str,
    max_backlinks: int = MAX_CROSS_BLOG_BACKLINKS,
) -> tuple[str, list[str]]:
    if not isinstance(article_markdown, str) or not article_markdown.strip():
        return article_markdown, []

    trigger_map, warnings = _load_cross_blog_link_map()
    if not trigger_map:
        return article_markdown, warnings

    wp_url, _, _ = _get_wp_config(target_suffix=target_suffix)
    current_domain = _normalized_domain(wp_url)

    filtered_map: dict[str, str] = {}
    for trigger, url in trigger_map.items():
        target_domain = _normalized_domain(url)
        if not target_domain:
            warnings.append(f"Skipping trigger '{trigger}': could not parse target domain.")
            continue
        if current_domain and target_domain == current_domain:
            warnings.append(
                f"Skipping trigger '{trigger}': mapped URL points to current blog domain."
            )
            continue
        filtered_map[trigger] = url

    if not filtered_map:
        return article_markdown, warnings

    lines = article_markdown.splitlines(keepends=True)
    output: list[str] = []
    paragraph_buffer: list[str] = []
    in_fenced_code = False
    replaced_triggers: set[str] = set()
    inserted_links = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer, inserted_links
        if not paragraph_buffer:
            return
        block = "".join(paragraph_buffer)
        paragraph_buffer = []
        if _is_plain_paragraph_block(block) and inserted_links < max_backlinks:
            updated_block, block_inserted = _inject_triggers_into_paragraph(
                paragraph=block,
                trigger_map=filtered_map,
                replaced_triggers=replaced_triggers,
                remaining_slots=max_backlinks - inserted_links,
            )
            inserted_links += block_inserted
            output.append(updated_block)
            return
        output.append(block)

    for line in lines:
        stripped = line.strip()
        if re.match(r"^(```|~~~)", stripped):
            flush_paragraph()
            in_fenced_code = not in_fenced_code
            output.append(line)
            continue

        if in_fenced_code:
            output.append(line)
            continue

        if not stripped:
            flush_paragraph()
            output.append(line)
            continue

        paragraph_buffer.append(line)

    flush_paragraph()
    updated_markdown = "".join(output)
    sibling_domains = {
        _normalized_domain(url)
        for url in filtered_map.values()
        if _normalized_domain(url)
    }
    if sibling_domains and not _has_sibling_domain_link(updated_markdown, sibling_domains):
        fallback_url = _select_fallback_sibling_url(filtered_map)
        if fallback_url:
            updated_markdown = _append_fallback_sibling_link(updated_markdown, fallback_url)
    return updated_markdown, warnings


def build_post_slug(focus_keyword: str, title: str, max_length: int = POST_SLUG_MAX_LENGTH) -> str:
    _ = title, max_length
    slug = focus_keyword.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "post"


def _ensure_alt_text_has_focus_keyword(alt_text: str, focus_keyword: str) -> str:
    keyword = str(focus_keyword or "").strip()
    base = str(alt_text or "").strip() or "Image"
    if not keyword:
        return base
    if keyword.casefold() in base.casefold():
        return base
    return f"{keyword} - {base}"


def _extract_markdown_links(article_markdown: str) -> list[str]:
    link_pattern = re.compile(
        r"(?<!!)\[[^\]]+\]\((?P<url>https?://[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    )
    return [match.group("url").strip() for match in link_pattern.finditer(article_markdown)]


def _audit_internal_external_links(
    article_markdown: str, current_domain: str
) -> tuple[bool, bool]:
    has_internal = False
    has_external = False
    for url in _extract_markdown_links(article_markdown):
        link_domain = _normalized_domain(url)
        if not link_domain:
            continue
        if current_domain and link_domain == current_domain:
            has_internal = True
        else:
            has_external = True
    return has_internal, has_external


def _load_external_sources_config() -> tuple[dict[str, Any], list[str]]:
    load_dotenv()
    warnings: list[str] = []
    raw_sources = os.getenv(SEO_EXTERNAL_SOURCES_ENV, "").strip()
    if not raw_sources:
        warnings.append(f"{SEO_EXTERNAL_SOURCES_ENV} is missing; external reference link was not added.")
        return {}, warnings

    try:
        payload = json.loads(raw_sources)
    except json.JSONDecodeError:
        warnings.append(
            f"{SEO_EXTERNAL_SOURCES_ENV} is not valid JSON; external reference link was not added."
        )
        return {}, warnings

    if not isinstance(payload, dict):
        warnings.append(
            f"{SEO_EXTERNAL_SOURCES_ENV} must be a JSON object; external reference link was not added."
        )
        return {}, warnings
    return payload, warnings


def _select_authority_source(
    target_suffix: str, current_domain: str
) -> tuple[dict[str, str] | None, list[str]]:
    payload, warnings = _load_external_sources_config()
    if not payload:
        return None, warnings

    ordered_keys = [target_suffix.strip().upper(), "default"]
    for key in ordered_keys:
        if key not in payload:
            continue
        candidates = payload.get(key)
        if not isinstance(candidates, list):
            warnings.append(
                f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' must be a list; skipping this source set."
            )
            continue
        for item in candidates:
            if not isinstance(item, dict):
                warnings.append(
                    f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' has a non-object entry; skipping."
                )
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                warnings.append(
                    f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' has an entry with missing URL; skipping."
                )
                continue
            clean_url = url.strip()
            if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
                warnings.append(
                    f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' has a malformed URL '{clean_url}'; skipping."
                )
                continue
            source_domain = _normalized_domain(clean_url)
            if not source_domain:
                warnings.append(
                    f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' has an unparsable URL '{clean_url}'; skipping."
                )
                continue
            if current_domain and source_domain == current_domain:
                warnings.append(
                    f"{SEO_EXTERNAL_SOURCES_ENV} key '{key}' URL '{clean_url}' matches current blog domain; skipping."
                )
                continue
            anchor = item.get("anchor")
            anchor_text = (
                anchor.strip()
                if isinstance(anchor, str) and anchor.strip()
                else "official guidance"
            )
            return {"url": clean_url, "anchor": anchor_text}, warnings

    warnings.append(
        f"No valid authority source found in {SEO_EXTERNAL_SOURCES_ENV}; external reference link was not added."
    )
    return None, warnings


def _resolve_internal_link(target_suffix: str, category_id: int | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    wp_url, _, _ = _get_wp_config(target_suffix=target_suffix)
    homepage_url = wp_url.rstrip("/") + "/"

    if category_id is None:
        warnings.append("Category ID missing; using homepage as internal link fallback.")
        return homepage_url, warnings

    try:
        categories = list_categories(target_suffix=target_suffix)
    except WordPressUploadError as exc:
        warnings.append(
            f"Category lookup failed while creating internal link ({exc}); using homepage fallback."
        )
        return homepage_url, warnings

    for category in categories:
        category_item_id = category.get("id")
        slug = str(category.get("slug", "")).strip()
        if category_item_id == int(category_id) and slug:
            return f"{homepage_url}category/{slug}/", warnings

    warnings.append("Selected category not found; using homepage as internal link fallback.")
    return homepage_url, warnings


def ensure_required_markdown_links(
    article_markdown: str,
    target_suffix: str,
    category_id: int | None,
) -> tuple[str, list[str]]:
    if not isinstance(article_markdown, str) or not article_markdown.strip():
        return article_markdown, []

    warnings: list[str] = []
    wp_url, _, _ = _get_wp_config(target_suffix=target_suffix)
    current_domain = _normalized_domain(wp_url)
    has_internal, has_external = _audit_internal_external_links(
        article_markdown=article_markdown,
        current_domain=current_domain,
    )

    updated_markdown = article_markdown.rstrip()

    if not has_internal:
        internal_url, internal_warnings = _resolve_internal_link(
            target_suffix=target_suffix,
            category_id=category_id,
        )
        warnings.extend(internal_warnings)
        updated_markdown += f"\n\nRelated reading: [Explore more on this topic]({internal_url})"

    if not has_external:
        authority_source, authority_warnings = _select_authority_source(
            target_suffix=target_suffix,
            current_domain=current_domain,
        )
        warnings.extend(authority_warnings)
        if authority_source is not None:
            updated_markdown += (
                f"\n\nReference: [{authority_source['anchor']}]({authority_source['url']})"
            )

    trailing_newline = "\n" if article_markdown.endswith("\n") else ""
    return updated_markdown + trailing_newline, warnings


def _get_wp_config(target_suffix: str) -> tuple[str, str, str]:
    load_dotenv()

    suffix = (target_suffix or "").strip().upper()
    if not suffix:
        raise WordPressUploadError("target_suffix is required for WordPress configuration.")

    wp_url_key = f"WP_URL_{suffix}"
    wp_user_key = f"WP_USER_{suffix}"
    wp_key_key = f"WP_KEY_{suffix}"

    wp_url = os.getenv(wp_url_key, "").strip().rstrip("/")
    wp_user = os.getenv(wp_user_key, "").strip()
    wp_key = os.getenv(wp_key_key, "").strip()

    missing = [
        name
        for name, value in [(wp_url_key, wp_url), (wp_user_key, wp_user), (wp_key_key, wp_key)]
        if not value
    ]
    if missing:
        raise WordPressUploadError(
            "Missing WordPress environment variables for target "
            f"'{suffix}': " + ", ".join(missing)
        )

    if not wp_url.startswith("http://") and not wp_url.startswith("https://"):
        raise WordPressUploadError(f"{wp_url_key} must start with http:// or https://")

    return wp_url, wp_user, wp_key


def markdown_to_html(content_markdown: str) -> str:
    if not isinstance(content_markdown, str) or not content_markdown.strip():
        raise WordPressUploadError("Markdown content is empty.")

    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise WordPressUploadError(
            "markdown-it-py package is required. Install dependencies first."
        ) from exc

    markdown_parser = MarkdownIt(
        "commonmark",
        {"html": False, "linkify": True, "typographer": True},
    )
    return markdown_parser.render(content_markdown).strip()


def upload_media(file_path: Path, alt_text: str, target_suffix: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise WordPressUploadError(f"Image file not found: {path}")

    wp_url, wp_user, wp_key = _get_wp_config(target_suffix=target_suffix)
    endpoint = f"{wp_url}/wp-json/wp/v2/media"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    try:
        with path.open("rb") as file_handle:
            response = requests.post(
                endpoint,
                auth=HTTPBasicAuth(wp_user, wp_key),
                files={"file": (path.name, file_handle, mime_type)},
                data={"alt_text": alt_text},
                timeout=120,
            )
    except requests.RequestException as exc:
        raise WordPressUploadError(f"Media upload request failed: {exc}") from exc

    if response.status_code not in (200, 201):
        raise WordPressUploadError(
            f"Media upload failed ({response.status_code}): {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise WordPressUploadError("Media upload returned non-JSON response.") from exc

    if "id" not in payload or "source_url" not in payload:
        raise WordPressUploadError("Media upload response missing 'id' or 'source_url'.")

    return {"id": int(payload["id"]), "source_url": str(payload["source_url"])}


def list_categories(target_suffix: str) -> list[dict[str, Any]]:
    wp_url, wp_user, wp_key = _get_wp_config(target_suffix=target_suffix)
    endpoint = f"{wp_url}/wp-json/wp/v2/categories"

    try:
        response = requests.get(
            endpoint,
            auth=HTTPBasicAuth(wp_user, wp_key),
            params={"per_page": 100, "orderby": "name", "order": "asc"},
            timeout=120,
        )
    except requests.RequestException as exc:
        raise WordPressUploadError(f"Category lookup failed: {exc}") from exc

    if response.status_code != 200:
        if response.status_code in (401, 403):
            raise WordPressUploadError(
                f"WordPress authentication failed ({response.status_code}). Check scoped WP_USER/WP_KEY."
            )
        raise WordPressUploadError(
            f"Category lookup failed ({response.status_code}): {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise WordPressUploadError("Category lookup returned non-JSON response.") from exc

    if not isinstance(payload, list):
        raise WordPressUploadError("Category lookup returned invalid payload shape.")

    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        name = item.get("name")
        slug = item.get("slug")
        if not isinstance(item_id, int) or not isinstance(name, str) or not isinstance(slug, str):
            continue
        normalized.append(
            {
                "id": int(item_id),
                "name": html.unescape(name).strip(),
                "slug": slug.strip(),
            }
        )
    return normalized


def ensure_category(name: str, target_suffix: str) -> int:
    clean_name = (name or "").strip()
    if not clean_name:
        raise WordPressUploadError("Category name is required.")

    categories = list_categories(target_suffix=target_suffix)
    clean_folded = clean_name.casefold()
    for category in categories:
        existing_name = str(category.get("name", "")).strip()
        if existing_name.casefold() == clean_folded:
            return int(category["id"])

    wp_url, wp_user, wp_key = _get_wp_config(target_suffix=target_suffix)
    endpoint = f"{wp_url}/wp-json/wp/v2/categories"
    try:
        response = requests.post(
            endpoint,
            auth=HTTPBasicAuth(wp_user, wp_key),
            json={"name": clean_name},
            timeout=120,
        )
    except requests.RequestException as exc:
        raise WordPressUploadError(f"Category create request failed: {exc}") from exc

    if response.status_code not in (200, 201):
        # Handle WP race where category may already exist and term_id is returned.
        if response.status_code == 400:
            try:
                duplicate_payload = response.json()
            except ValueError:
                duplicate_payload = {}
            if isinstance(duplicate_payload, dict):
                data = duplicate_payload.get("data")
                if isinstance(data, dict) and isinstance(data.get("term_id"), int):
                    return int(data["term_id"])
        raise WordPressUploadError(
            f"Category create failed ({response.status_code}): {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise WordPressUploadError("Category create returned non-JSON response.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("id"), int):
        raise WordPressUploadError("Category create response missing category id.")
    return int(payload["id"])


def resolve_category_id(selected_name: str, typed_new_name: str, target_suffix: str) -> int:
    typed = (typed_new_name or "").strip()
    if typed:
        return ensure_category(typed, target_suffix=target_suffix)

    selected = (selected_name or "").strip()
    if not selected:
        raise WordPressUploadError("Select a category or provide a new category name.")

    selected_folded = selected.casefold()
    categories = list_categories(target_suffix=target_suffix)
    for category in categories:
        existing_name = str(category.get("name", "")).strip()
        if existing_name.casefold() == selected_folded:
            return int(category["id"])

    raise WordPressUploadError(
        f"Selected category '{selected}' no longer exists. Refresh categories and try again."
    )


def inject_detail_image_after_first_paragraph(
    content_html: str, detail_image_url: str, alt_text: str
) -> str:
    if not isinstance(content_html, str) or not content_html.strip():
        raise WordPressUploadError("HTML content is empty.")
    if not isinstance(detail_image_url, str) or not detail_image_url.strip():
        raise WordPressUploadError("Detail image URL is empty.")

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


def publish_post(
    title: str,
    content_markdown: str,
    hero_path: Path,
    detail_path: Path,
    target_suffix: str,
    focus_keyword: str,
    meta_description: str,
    seo_title: str,
    status: str = "draft",
    category_id: int | None = None,
) -> dict[str, Any]:
    if not isinstance(title, str) or not title.strip():
        raise WordPressUploadError("Title is required.")
    if not isinstance(focus_keyword, str) or not focus_keyword.strip():
        raise WordPressUploadError("focus_keyword is required.")
    if not isinstance(meta_description, str) or not meta_description.strip():
        raise WordPressUploadError("meta_description is required.")
    if not isinstance(seo_title, str) or not seo_title.strip():
        raise WordPressUploadError("seo_title is required.")

    normalized_markdown, _ = strip_duplicate_leading_h1(
        content_markdown=content_markdown,
        title=title.strip(),
    )
    linked_markdown, backlink_warnings = inject_cross_blog_backlinks(
        article_markdown=normalized_markdown,
        target_suffix=target_suffix,
    )
    ensured_markdown, assurance_warnings = ensure_required_markdown_links(
        article_markdown=linked_markdown,
        target_suffix=target_suffix,
        category_id=category_id,
    )
    publish_warnings = backlink_warnings + assurance_warnings
    content_html = markdown_to_html(ensured_markdown)
    hero_alt_text = _ensure_alt_text_has_focus_keyword(
        alt_text=f"{title.strip()} hero image",
        focus_keyword=focus_keyword.strip(),
    )
    detail_alt_text = _ensure_alt_text_has_focus_keyword(
        alt_text=f"{title.strip()} detail image",
        focus_keyword=focus_keyword.strip(),
    )

    hero_media = upload_media(
        Path(hero_path),
        alt_text=hero_alt_text,
        target_suffix=target_suffix,
    )
    detail_media = upload_media(
        Path(detail_path),
        alt_text=detail_alt_text,
        target_suffix=target_suffix,
    )

    content_with_detail = inject_detail_image_after_first_paragraph(
        content_html=content_html,
        detail_image_url=detail_media["source_url"],
        alt_text=detail_alt_text,
    )

    wp_url, wp_user, wp_key = _get_wp_config(target_suffix=target_suffix)
    endpoint = f"{wp_url}/wp-json/wp/v2/posts"

    payload = {
        "title": title.strip(),
        "slug": build_post_slug(
            focus_keyword=focus_keyword.strip(),
            title=title.strip(),
            max_length=POST_SLUG_MAX_LENGTH,
        ),
        "content": content_with_detail,
        "featured_media": int(hero_media["id"]),
        "status": status.strip() or "draft",
        "meta": {
            "rank_math_title": seo_title.strip(),
            "rank_math_description": meta_description.strip(),
            "rank_math_focus_keyword": focus_keyword.strip(),
        },
    }
    if category_id is not None:
        payload["categories"] = [int(category_id)]

    try:
        response = requests.post(
            endpoint,
            auth=HTTPBasicAuth(wp_user, wp_key),
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise WordPressUploadError(f"Post publish request failed: {exc}") from exc

    if response.status_code not in (200, 201):
        if response.status_code in (401, 403):
            raise WordPressUploadError(
                f"WordPress authentication failed ({response.status_code}). Check scoped WP_USER/WP_KEY."
            )
        raise WordPressUploadError(
            f"Post publish failed ({response.status_code}): {response.text[:500]}"
        )

    try:
        post_payload = response.json()
    except ValueError as exc:
        raise WordPressUploadError("Post publish returned non-JSON response.") from exc

    return {
        "post_id": int(post_payload.get("id", 0)),
        "post_url": str(post_payload.get("link", "")),
        "post_slug": str(
            post_payload.get(
                "slug",
                build_post_slug(
                    focus_keyword=focus_keyword.strip(),
                    title=title.strip(),
                    max_length=POST_SLUG_MAX_LENGTH,
                ),
            )
        ),
        "status": str(post_payload.get("status", payload["status"])),
        "hero_media_id": int(hero_media["id"]),
        "detail_media_id": int(detail_media["id"]),
        "category_ids": [int(item) for item in post_payload.get("categories", payload.get("categories", []))],
        "publish_warnings": publish_warnings,
    }
