from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


DEFAULT_REPORT_PATH = Path("artifacts") / "reports" / "wp_onboarding_report.json"
DEFAULT_BASE_PAGES = ("about", "contact", "privacy-policy")
PRIVACY_PLACEHOLDER_HTML = (
    "<h2>Privacy Policy</h2>"
    "<p>This page will contain the site's final privacy policy language.</p>"
    "<p>Update this content before publishing legal-sensitive features.</p>"
)
PRIVACY_STUB_MARKERS = (
    "suggested text:",
    "who we are",
    "comments",
    "cookies",
    "embedded content from other websites",
)


class WordPressOnboardingError(RuntimeError):
    """Raised when WordPress onboarding actions fail."""


@dataclass
class OnboardingConfig:
    wp_url: str
    wp_user: str
    wp_key: str
    dry_run: bool = True
    timezone: str = "UTC"
    enable_indexing: bool = False
    default_comment_status: str = "open"
    base_pages: tuple[str, ...] = DEFAULT_BASE_PAGES
    seo_plugin: str = "seo-by-rank-math"
    use_wp_cli: bool = True
    delete_default_plugins: bool = True

    @classmethod
    def from_env(cls, dry_run: bool = True) -> OnboardingConfig:
        load_dotenv()

        wp_url = os.getenv("WP_URL", "").strip().rstrip("/")
        wp_user = os.getenv("WP_USER", "").strip()
        wp_key = os.getenv("WP_KEY", "").strip()

        missing = [
            name
            for name, value in [("WP_URL", wp_url), ("WP_USER", wp_user), ("WP_KEY", wp_key)]
            if not value
        ]
        if missing:
            raise WordPressOnboardingError(
                "Missing WordPress environment variables: " + ", ".join(missing)
            )

        if not wp_url.startswith(("http://", "https://")):
            raise WordPressOnboardingError("WP_URL must start with http:// or https://")

        timezone = os.getenv("WP_TIMEZONE", "UTC").strip() or "UTC"
        enable_indexing = _parse_bool(os.getenv("WP_ENABLE_INDEXING"), default=False)
        default_comment_status = (
            os.getenv("WP_DEFAULT_COMMENT_STATUS", "open").strip().lower() or "open"
        )
        if default_comment_status not in {"open", "closed"}:
            raise WordPressOnboardingError(
                "WP_DEFAULT_COMMENT_STATUS must be 'open' or 'closed'."
            )

        base_pages = _parse_base_pages(
            os.getenv("WP_BASE_PAGES", ",".join(DEFAULT_BASE_PAGES))
        )
        seo_plugin = os.getenv("WP_SEO_PLUGIN", "seo-by-rank-math").strip()
        if not seo_plugin:
            seo_plugin = "seo-by-rank-math"

        use_wp_cli = _parse_bool(os.getenv("WP_USE_WPCLI"), default=True)
        delete_default_plugins = _parse_bool(
            os.getenv("WP_DELETE_DEFAULT_PLUGINS"), default=True
        )

        return cls(
            wp_url=wp_url,
            wp_user=wp_user,
            wp_key=wp_key,
            dry_run=dry_run,
            timezone=timezone,
            enable_indexing=enable_indexing,
            default_comment_status=default_comment_status,
            base_pages=base_pages,
            seo_plugin=seo_plugin,
            use_wp_cli=use_wp_cli,
            delete_default_plugins=delete_default_plugins,
        )


@dataclass
class CleanupReport:
    mode: str
    planned_actions: list[str] = field(default_factory=list)
    executed_actions: list[str] = field(default_factory=list)
    skipped_actions: list[str] = field(default_factory=list)
    manual_wpcli_actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _WPClient:
    def __init__(self, config: OnboardingConfig):
        self._config = config
        self._auth = HTTPBasicAuth(config.wp_user, config.wp_key)

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        clean_endpoint = endpoint.strip().lstrip("/")
        url = f"{self._config.wp_url}/wp-json/wp/v2/{clean_endpoint}"

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                auth=self._auth,
                params=params,
                json=json_body,
                timeout=120,
            )
        except requests.RequestException as exc:
            raise WordPressOnboardingError(f"WordPress request failed for {url}: {exc}") from exc

        if response.status_code >= 400:
            if response.status_code in (401, 403):
                raise WordPressOnboardingError(
                    "WordPress authentication/authorization failed. Check WP_USER/WP_KEY."
                )
            raise WordPressOnboardingError(
                f"WordPress API error {response.status_code} for {url}: {response.text[:500]}"
            )

        if response.status_code == 204 or not response.text:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise WordPressOnboardingError(f"WordPress API returned non-JSON for {url}") from exc


def verify_access(config: OnboardingConfig) -> dict[str, Any]:
    client = _WPClient(config)
    payload = client.request("GET", "users/me")
    if not isinstance(payload, dict):
        raise WordPressOnboardingError("Unexpected users/me response payload.")
    return payload


def run_onboarding(config: OnboardingConfig) -> CleanupReport:
    client = _WPClient(config)
    report = CleanupReport(mode="dry-run" if config.dry_run else "apply")
    starter_parent_ids: set[int] = set()

    user_payload = verify_access(config)
    report.metadata["authenticated_user"] = {
        "id": user_payload.get("id"),
        "name": user_payload.get("name"),
        "slug": user_payload.get("slug"),
    }
    _record(report, "Verified WordPress API access with /users/me", executed=True)

    settings_payload = _fetch_settings(client, report)
    report.metadata["rest_supported_settings"] = sorted(settings_payload.keys())

    _delete_default_post(client, report, starter_parent_ids)
    _delete_sample_page(client, report, starter_parent_ids)
    _delete_starter_media(client, report, starter_parent_ids)
    _apply_timezone_setting(client, report, settings_payload, config)
    _ensure_privacy_policy(client, report, settings_payload)
    _ensure_base_pages(client, report, config.base_pages)
    _append_wpcli_runbook(report, config)

    return report


def _fetch_settings(client: _WPClient, report: CleanupReport) -> dict[str, Any]:
    payload = client.request("GET", "settings")
    if not isinstance(payload, dict):
        report.errors.append("Settings response was not an object.")
        return {}
    _record(report, "Fetched /settings capabilities", executed=True)
    return payload


def _delete_default_post(
    client: _WPClient, report: CleanupReport, starter_parent_ids: set[int]
) -> None:
    posts_payload = client.request("GET", "posts", params={"slug": "hello-world", "per_page": 100})
    posts = posts_payload if isinstance(posts_payload, list) else []
    if not posts:
        _record(report, "Default post slug 'hello-world' not found", skipped=True)
        return

    for post in posts:
        post_id = _coerce_int(post.get("id"))
        if post_id is None:
            continue
        action = f"Delete starter post id={post_id} slug=hello-world (force=true)"
        if config_is_dry_run(report):
            _record(report, action, planned=True)
        else:
            client.request("DELETE", f"posts/{post_id}", params={"force": "true"})
            _record(report, action, executed=True)
        starter_parent_ids.add(post_id)


def _delete_sample_page(
    client: _WPClient, report: CleanupReport, starter_parent_ids: set[int]
) -> None:
    pages_payload = client.request(
        "GET", "pages", params={"slug": "sample-page", "per_page": 100}
    )
    pages = pages_payload if isinstance(pages_payload, list) else []
    if not pages:
        _record(report, "Sample page slug 'sample-page' not found", skipped=True)
        return

    for page in pages:
        page_id = _coerce_int(page.get("id"))
        if page_id is None:
            continue
        action = f"Delete sample page id={page_id} slug=sample-page (force=true)"
        if config_is_dry_run(report):
            _record(report, action, planned=True)
        else:
            client.request("DELETE", f"pages/{page_id}", params={"force": "true"})
            _record(report, action, executed=True)
        starter_parent_ids.add(page_id)


def _delete_starter_media(
    client: _WPClient, report: CleanupReport, starter_parent_ids: set[int]
) -> None:
    if not starter_parent_ids:
        _record(report, "No starter parent IDs found for media cleanup", skipped=True)
        return

    media_payload = client.request("GET", "media", params={"per_page": 100})
    media_items = media_payload if isinstance(media_payload, list) else []
    if not media_items:
        _record(report, "No media entries found", skipped=True)
        return

    deleted_count = 0
    for item in media_items:
        media_id = _coerce_int(item.get("id"))
        parent_id = _coerce_int(item.get("post"))
        if media_id is None or parent_id is None or parent_id not in starter_parent_ids:
            continue

        action = (
            f"Delete starter media id={media_id} attached_to={parent_id} (force=true)"
        )
        if config_is_dry_run(report):
            _record(report, action, planned=True)
        else:
            client.request("DELETE", f"media/{media_id}", params={"force": "true"})
            _record(report, action, executed=True)
        deleted_count += 1

    if deleted_count == 0:
        _record(report, "No starter media linked to deleted default content", skipped=True)


def _apply_timezone_setting(
    client: _WPClient,
    report: CleanupReport,
    settings_payload: dict[str, Any],
    config: OnboardingConfig,
) -> None:
    if "timezone" not in settings_payload:
        _record(report, "REST settings do not expose 'timezone'; skipping write", skipped=True)
        report.manual_wpcli_actions.append(f"wp option update timezone_string '{config.timezone}'")
        return

    current = str(settings_payload.get("timezone", "") or "").strip()
    if current == config.timezone:
        _record(report, f"Timezone already set to '{config.timezone}'", skipped=True)
        return

    action = f"Set timezone via REST to '{config.timezone}'"
    if config_is_dry_run(report):
        _record(report, action, planned=True)
    else:
        client.request("POST", "settings", json_body={"timezone": config.timezone})
        _record(report, action, executed=True)


def _ensure_privacy_policy(
    client: _WPClient, report: CleanupReport, settings_payload: dict[str, Any]
) -> None:
    privacy_page = _resolve_privacy_policy_page(client, settings_payload)

    if privacy_page is None:
        action = "Create privacy policy page (slug=privacy-policy, status=publish)"
        if config_is_dry_run(report):
            _record(report, action, planned=True)
            report.manual_wpcli_actions.append(
                "wp option update wp_page_for_privacy_policy <NEW_PRIVACY_PAGE_ID>"
            )
            return

        created = client.request(
            "POST",
            "pages",
            json_body={
                "title": "Privacy Policy",
                "slug": "privacy-policy",
                "status": "publish",
                "content": PRIVACY_PLACEHOLDER_HTML,
            },
        )
        created_id = _coerce_int(created.get("id") if isinstance(created, dict) else None)
        _record(report, action, executed=True)
        if created_id is not None:
            report.manual_wpcli_actions.append(
                f"wp option update wp_page_for_privacy_policy {created_id}"
            )
        else:
            report.manual_wpcli_actions.append(
                "wp option update wp_page_for_privacy_policy <NEW_PRIVACY_PAGE_ID>"
            )
        return

    page_id = _coerce_int(privacy_page.get("id"))
    if page_id is None:
        report.errors.append("Resolved privacy policy page is missing a valid id.")
        return

    status = str(privacy_page.get("status", "") or "").strip().lower()
    content = _extract_content_text(privacy_page)
    update_payload: dict[str, Any] = {}
    if status != "publish":
        update_payload["status"] = "publish"
    if _is_default_privacy_stub(content):
        update_payload["content"] = PRIVACY_PLACEHOLDER_HTML

    if not update_payload:
        _record(
            report,
            f"Privacy policy page id={page_id} already published and non-stub",
            skipped=True,
        )
        return

    action = f"Update privacy policy page id={page_id} in place"
    if config_is_dry_run(report):
        _record(report, action, planned=True)
    else:
        client.request("POST", f"pages/{page_id}", json_body=update_payload)
        _record(report, action, executed=True)


def _resolve_privacy_policy_page(
    client: _WPClient, settings_payload: dict[str, Any]
) -> dict[str, Any] | None:
    policy_id = _coerce_int(settings_payload.get("page_for_privacy_policy"))
    if policy_id is not None and policy_id > 0:
        page = client.request("GET", f"pages/{policy_id}", params={"context": "edit"})
        if isinstance(page, dict):
            return page

    slug_payload = client.request("GET", "pages", params={"slug": "privacy-policy", "per_page": 100})
    if isinstance(slug_payload, list) and slug_payload:
        first = slug_payload[0]
        first_id = _coerce_int(first.get("id"))
        if first_id is not None:
            full = client.request("GET", f"pages/{first_id}", params={"context": "edit"})
            if isinstance(full, dict):
                return full
        if isinstance(first, dict):
            return first

    search_payload = client.request(
        "GET", "pages", params={"search": "Privacy Policy", "per_page": 100}
    )
    if not isinstance(search_payload, list):
        return None
    for page in search_payload:
        if not isinstance(page, dict):
            continue
        title = _extract_rendered_field(page, "title").strip().lower()
        if "privacy policy" not in title:
            continue
        page_id = _coerce_int(page.get("id"))
        if page_id is None:
            continue
        full = client.request("GET", f"pages/{page_id}", params={"context": "edit"})
        if isinstance(full, dict):
            return full
        return page
    return None


def _ensure_base_pages(client: _WPClient, report: CleanupReport, base_pages: tuple[str, ...]) -> None:
    for slug in base_pages:
        clean_slug = slug.strip().lower()
        if clean_slug in {"", "privacy-policy"}:
            continue
        payload = client.request("GET", "pages", params={"slug": clean_slug, "per_page": 100})
        pages = payload if isinstance(payload, list) else []
        if pages:
            _record(report, f"Page slug '{clean_slug}' already exists", skipped=True)
            continue

        title = clean_slug.replace("-", " ").title()
        action = f"Create page slug='{clean_slug}' title='{title}'"
        if config_is_dry_run(report):
            _record(report, action, planned=True)
        else:
            client.request(
                "POST",
                "pages",
                json_body={
                    "title": title,
                    "slug": clean_slug,
                    "status": "publish",
                    "content": f"<h2>{title}</h2><p>Update this page content.</p>",
                },
            )
            _record(report, action, executed=True)


def _append_wpcli_runbook(report: CleanupReport, config: OnboardingConfig) -> None:
    if not config.use_wp_cli:
        _record(report, "WP-CLI runbook disabled by config", skipped=True)
        return

    indexing_value = "1" if config.enable_indexing else "0"
    commands = [
        "wp rewrite structure '/%postname%/' --hard",
        "wp rewrite flush --hard",
        f"wp option update blog_public {indexing_value}",
        f"wp option update default_comment_status {config.default_comment_status}",
        f"wp plugin install {config.seo_plugin} --activate",
    ]
    if config.delete_default_plugins:
        commands.append("wp plugin delete hello akismet")

    verification = [
        f"wp option get blog_public  # expected {indexing_value}",
        f"wp option get default_comment_status  # expected {config.default_comment_status}",
        "wp rewrite list",
        f"wp plugin is-installed {config.seo_plugin} && wp plugin is-active {config.seo_plugin}",
    ]

    report.manual_wpcli_actions.extend(commands + verification)
    _record(report, "Generated WP-CLI operator runbook", executed=True)


def _extract_rendered_field(payload: dict[str, Any], key: str) -> str:
    field = payload.get(key)
    if isinstance(field, dict):
        rendered = field.get("rendered")
        if isinstance(rendered, str):
            return rendered
    if isinstance(field, str):
        return field
    return ""


def _extract_content_text(page_payload: dict[str, Any]) -> str:
    content = page_payload.get("content")
    if isinstance(content, dict):
        for key in ("raw", "rendered"):
            value = content.get(key)
            if isinstance(value, str):
                return value
    if isinstance(content, str):
        return content
    return ""


def _is_default_privacy_stub(content: str) -> bool:
    lowered = content.strip().lower()
    if not lowered:
        return True
    return all(marker in lowered for marker in PRIVACY_STUB_MARKERS)


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_base_pages(raw_value: str) -> tuple[str, ...]:
    pages = [item.strip().lower() for item in raw_value.split(",")]
    filtered: list[str] = []
    seen: set[str] = set()
    for page in pages:
        if not page or page in seen:
            continue
        seen.add(page)
        filtered.append(page)
    return tuple(filtered or list(DEFAULT_BASE_PAGES))


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record(
    report: CleanupReport,
    message: str,
    *,
    planned: bool = False,
    executed: bool = False,
    skipped: bool = False,
) -> None:
    if planned:
        report.planned_actions.append(message)
        return
    if executed:
        report.executed_actions.append(message)
        return
    if skipped:
        report.skipped_actions.append(message)
        return
    report.executed_actions.append(message)


def config_is_dry_run(report: CleanupReport) -> bool:
    return report.mode == "dry-run"


def _save_report(report: CleanupReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run WordPress onboarding cleanup workflow.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute mutations. Default mode is --dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without mutating WordPress content.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Report output path (default: {DEFAULT_REPORT_PATH}).",
    )
    args = parser.parse_args()

    dry_run = True
    if args.apply and not args.dry_run:
        dry_run = False

    config = OnboardingConfig.from_env(dry_run=dry_run)
    report = run_onboarding(config)

    output_path = Path(args.output)
    _save_report(report, output_path)
    print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    main()
