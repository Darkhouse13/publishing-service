from __future__ import annotations

import csv
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from dotenv import load_dotenv

from automating_wf.models.pinterest import CsvRow


CSV_HEADERS = (
    "Title",
    "Media URL",
    "Pinterest board",
    "Thumbnail",
    "Description",
    "Link",
    "Publish date",
    "Keywords",
)

CSV_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "Title": ("Title",),
    "Media URL": ("Media URL", "Image URL"),
    "Pinterest board": ("Pinterest board", "Pinterest Board"),
    "Thumbnail": ("Thumbnail",),
    "Description": ("Description",),
    "Link": ("Link",),
    "Publish date": ("Publish date", "Publish Date"),
    "Keywords": ("Keywords",),
}

DEFAULT_CSV_TEMPLATE = "artifacts/exports/pinterest_bulk_upload_{blog_suffix}.csv"
DEFAULT_CADENCE_MINUTES = 240
ROUNDING_MINUTES = 15


class ExporterError(RuntimeError):
    """Raised when Pinterest CSV export fails."""


def _load_board_mapping() -> dict[str, Any]:
    load_dotenv()
    raw = os.getenv("PINTEREST_BOARD_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_csv_path_for_blog(blog_suffix: str) -> Path:
    load_dotenv()
    template = os.getenv("PINTEREST_CSV_PATH_TEMPLATE", "").strip() or DEFAULT_CSV_TEMPLATE
    normalized = (blog_suffix or "").strip().upper()
    try:
        candidate = template.format(blog_suffix=normalized.lower(), BLOG_SUFFIX=normalized)
    except KeyError as exc:
        raise ExporterError(
            "PINTEREST_CSV_PATH_TEMPLATE supports only {blog_suffix} or {BLOG_SUFFIX} placeholders."
        ) from exc
    return Path(candidate)


def resolve_board_name(
    *,
    blog_suffix: str,
    primary_keyword: str,
    supporting_terms: list[str] | None = None,
) -> str:
    mapping = _load_board_mapping()
    blog_key = (blog_suffix or "").strip().upper()
    node = mapping.get(blog_key)
    if not isinstance(node, dict):
        return ""

    default_board = str(node.get("default", "")).strip()
    overrides = node.get("overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}

    haystacks = [primary_keyword.casefold()]
    for value in supporting_terms or []:
        haystacks.append(str(value).casefold())

    for override_key, board_name in overrides.items():
        if not isinstance(override_key, str) or not isinstance(board_name, str):
            continue
        trigger = override_key.casefold().strip()
        if not trigger:
            continue
        if any(trigger in haystack for haystack in haystacks):
            return board_name.strip()
    return default_board


def validate_board_mapping_for_blog(blog_suffix: str) -> None:
    """Validate that board mapping exists for the target blog suffix."""
    blog_key = (blog_suffix or "").strip().upper()
    mapping = _load_board_mapping()
    node = mapping.get(blog_key)
    if not isinstance(node, dict):
        example = {
            blog_key: {
                "default": "Your Pinterest Board Name",
                "overrides": {"keyword trigger": "Specific Board Name"},
            }
        }
        raise ExporterError(
            "Missing Pinterest board mapping for blog suffix "
            f"'{blog_key}' in PINTEREST_BOARD_MAP_JSON. "
            "Add an entry like: "
            f"{json.dumps(example, ensure_ascii=True)}"
        )

    default_board = str(node.get("default", "")).strip()
    if not default_board:
        example = {
            blog_key: {
                "default": "Your Pinterest Board Name",
                "overrides": {},
            }
        }
        raise ExporterError(
            "PINTEREST_BOARD_MAP_JSON entry for "
            f"'{blog_key}' must include a non-empty 'default' board name. "
            "Expected shape: "
            f"{json.dumps(example, ensure_ascii=True)}"
        )


def _timezone_name() -> str:
    load_dotenv()
    return os.getenv("WP_TIMEZONE", "UTC").strip() or "UTC"


def _load_zoneinfo(name: str) -> Any:
    try:
        from zoneinfo import ZoneInfo
    except ImportError as exc:
        raise ExporterError("Python zoneinfo support is required.") from exc
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def round_up_to_next_window(dt: datetime, window_minutes: int = ROUNDING_MINUTES) -> datetime:
    if window_minutes <= 0:
        return dt.replace(second=0, microsecond=0)

    normalized = dt.replace(second=0, microsecond=0)
    remainder = normalized.minute % window_minutes
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return normalized
    delta = window_minutes - remainder if remainder else window_minutes
    return normalized + timedelta(minutes=delta)


def _parse_publish_date(value: str, zone: Any) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        naive = datetime.strptime(text, "%Y-%m-%d")
        return naive.replace(tzinfo=zone)

    if "T" in text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(zone)

    for item in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = datetime.strptime(text, item)
            return naive.replace(tzinfo=zone)
        except ValueError:
            continue
    return None


def _select_next_publish_date(existing_rows: list[dict[str, str]], cadence_minutes: int, zone: Any) -> datetime:
    now = datetime.now(zone)
    rounded_now = round_up_to_next_window(now, ROUNDING_MINUTES)

    latest: datetime | None = None
    for row in existing_rows:
        parsed = _parse_publish_date(str(row.get("Publish date", "")), zone)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed

    if latest is None or latest < rounded_now:
        return rounded_now
    return latest + timedelta(minutes=max(1, cadence_minutes))


def _format_publish_date_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc.strip())


def _header_lookup(row: dict[str, Any]) -> dict[str, str]:
    return {str(key).strip().casefold(): str(key) for key in row.keys()}


def _canonicalize_row(row: dict[str, Any]) -> dict[str, str]:
    lookup = _header_lookup(row)
    normalized: dict[str, str] = {}
    for header in CSV_HEADERS:
        value = ""
        for alias in CSV_HEADER_ALIASES[header]:
            source_key = lookup.get(alias.casefold())
            if source_key is None:
                continue
            raw = row.get(source_key, "")
            value = str(raw).strip() if raw is not None else ""
            break
        normalized[header] = value
    return normalized


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_existing_rows(csv_path: Path, zone: Any) -> tuple[list[dict[str, str]], bool]:
    if not csv_path.exists():
        return [], False
    with csv_path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        if not reader.fieldnames:
            return [], False
        fieldnames = [str(name).strip() for name in reader.fieldnames if name is not None]
        requires_migration = fieldnames != list(CSV_HEADERS)
        rows: list[dict[str, str]] = []
        for row in reader:
            if not isinstance(row, dict):
                continue
            normalized_row = _canonicalize_row(dict(row))
            parsed_publish_date = _parse_publish_date(normalized_row.get("Publish date", ""), zone)
            if parsed_publish_date is not None:
                normalized_row["Publish date"] = _format_publish_date_utc(parsed_publish_date)
            rows.append(normalized_row)
    return rows, requires_migration


def _write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(CSV_HEADERS))
        writer.writeheader()
        for row in rows:
            writer.writerow({header: str(row.get(header, "")) for header in CSV_HEADERS})


def _validate_row_fields(row: CsvRow) -> None:
    title = row.title.strip()
    board = row.pinterest_board.strip()
    media_url = row.image_url.strip()
    description = row.description.strip()
    link = row.link.strip()

    if not title:
        raise ExporterError("CSV row title is required.")
    if len(title) > 100:
        raise ExporterError("CSV row title exceeds 100 characters.")
    if not media_url:
        raise ExporterError("CSV row media URL is required.")
    if not board:
        raise ExporterError("CSV row Pinterest board is required.")
    if description and len(description) > 500:
        raise ExporterError("CSV row description exceeds 500 characters.")
    if not _is_http_url(media_url):
        raise ExporterError("CSV row media URL must be an absolute http(s) URL.")
    if link and not _is_http_url(link):
        raise ExporterError("CSV row link must be an absolute http(s) URL when provided.")


def append_csv_row(
    *,
    row: CsvRow,
    csv_path: Path,
    cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
) -> dict[str, Any]:
    _validate_row_fields(row)

    zone = _load_zoneinfo(_timezone_name())
    lock_path = csv_path.with_suffix(csv_path.suffix + ".lock")

    with _exclusive_file_lock(lock_path):
        rows, requires_migration = _read_existing_rows(csv_path, zone)
        existing_titles = {
            str(item.get("Title", "")).strip().casefold()
            for item in rows
            if str(item.get("Title", "")).strip()
        }
        existing_links = {
            str(item.get("Link", "")).strip().casefold()
            for item in rows
            if str(item.get("Link", "")).strip()
        }
        incoming_title = row.title.strip().casefold()
        incoming_link = row.link.strip().casefold()

        is_duplicate = incoming_title in existing_titles or (
            bool(incoming_link) and incoming_link in existing_links
        )
        if is_duplicate:
            if requires_migration:
                _write_rows(csv_path, rows)
            return {"status": "skipped_duplicate", "publish_date": "", "row": row.to_dict()}

        raw_publish_date = row.publish_date.strip()
        if raw_publish_date:
            parsed_publish_date = _parse_publish_date(raw_publish_date, zone)
            if parsed_publish_date is None:
                raise ExporterError(
                    "Publish date is invalid. Use YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, or legacy local format."
                )
            publish_dt = parsed_publish_date
        else:
            publish_dt = _select_next_publish_date(rows, cadence_minutes=cadence_minutes, zone=zone)
        publish_date = _format_publish_date_utc(publish_dt)

        final_row = CsvRow(
            title=row.title.strip(),
            description=row.description.strip(),
            link=row.link.strip(),
            image_url=row.image_url.strip(),
            pinterest_board=row.pinterest_board.strip(),
            publish_date=publish_date,
            thumbnail=row.thumbnail.strip(),
            keywords=row.keywords.strip(),
        )
        rows.append(final_row.to_dict())
        _write_rows(csv_path, rows)
        return {"status": "appended", "publish_date": publish_date, "row": final_row.to_dict()}
