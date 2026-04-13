"""CSVExporter — Pinterest bulk-upload CSV generation.

Exports a Pinterest-compatible CSV with exact column order:
``Title, Media URL, Pinterest board, Thumbnail, Description, Link,
Publish date, Keywords``.

Schedules publish dates using UTC with 15-minute window rounding:

- First row (empty CSV): ``round_up(now_utc + cadence_minutes)``
- Subsequent rows: ``round_up(last_publish_date + cadence_minutes)``

Ported from ``src/automating_wf/export/pinterest_csv.py`` but rewritten
cleanly: no ``os.getenv`` / ``load_dotenv``, pure file I/O, async-compatible.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_HEADERS: tuple[str, ...] = (
    "Title",
    "Media URL",
    "Pinterest board",
    "Thumbnail",
    "Description",
    "Link",
    "Publish date",
    "Keywords",
)

DEFAULT_CADENCE_MINUTES: int = 240
ROUNDING_WINDOW_MINUTES: int = 15

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExporterError(RuntimeError):
    """Raised when Pinterest CSV export fails."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CSVRow:
    """A single row of data for the Pinterest bulk-upload CSV.

    Attributes:
        title: Pin title (required).
        media_url: Image URL (required, must be http/https).
        board: Pinterest board name (required).
        thumbnail: Optional thumbnail URL.
        description: Pin description.
        link: Destination link URL.
        keywords: Comma-separated keywords.
    """

    title: str
    media_url: str
    board: str
    thumbnail: str = ""
    description: str = ""
    link: str = ""
    keywords: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def round_up_to_next_window(
    dt: datetime,
    window_minutes: int = ROUNDING_WINDOW_MINUTES,
) -> datetime:
    """Round *dt* up to the next ``window_minutes`` boundary.

    If *dt* already sits exactly on a boundary (seconds and microseconds
    are zero), it is returned unchanged.  Otherwise, it is advanced to the
    next boundary.

    Args:
        dt: The datetime to round.
        window_minutes: The rounding window in minutes (default 15).

    Returns:
        A :class:`datetime` on the boundary with seconds and microseconds
        zeroed.
    """
    if window_minutes <= 0:
        return dt.replace(second=0, microsecond=0)

    normalized = dt.replace(second=0, microsecond=0)
    remainder = normalized.minute % window_minutes

    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return normalized

    delta = window_minutes - remainder if remainder else window_minutes
    return normalized + timedelta(minutes=delta)


def _format_utc(dt: datetime) -> str:
    """Format a datetime as a UTC ISO string ``YYYY-MM-DDTHH:MM:SS+00:00``."""
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def _is_http_url(value: str) -> bool:
    """Return True if *value* is an absolute http(s) URL."""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc.strip())


def _parse_publish_date(value: str) -> datetime | None:
    """Parse a publish-date string from the CSV.

    Supports ISO format (``YYYY-MM-DDTHH:MM:SS``) and plain date
    (``YYYY-MM-DD``).  Returns ``None`` if the string is empty or
    unparseable.
    """
    text = (value or "").strip()
    if not text:
        return None

    # ISO format with optional Z / offset
    if "T" in text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    # YYYY-MM-DD
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_row(row: CSVRow, board_name: str) -> None:
    """Validate that required fields are present and well-formed.

    Args:
        row: The :class:`CSVRow` to validate.
        board_name: The effective board name (from exporter config).

    Raises:
        ExporterError: When validation fails.
    """
    title = (row.title or "").strip()
    if not title:
        raise ExporterError("CSV row title is required.")

    media_url = (row.media_url or "").strip()
    if not media_url:
        raise ExporterError("CSV row media URL is required.")
    if not _is_http_url(media_url):
        raise ExporterError("CSV row media URL must be an absolute http(s) URL.")

    board = (board_name or "").strip()
    if not board:
        raise ExporterError("CSV row Pinterest board is required.")


# ---------------------------------------------------------------------------
# CSVExporter
# ---------------------------------------------------------------------------


class CSVExporter:
    """Pinterest bulk-upload CSV exporter.

    Writes (or appends to) a CSV file at *csv_path* with the exact column
    order defined by :data:`CSV_HEADERS`.  Publish dates are scheduled in
    UTC and rounded up to 15-minute boundaries.

    Parameters:
        csv_path: Destination file path.
        cadence_minutes: Minutes between consecutive publish slots.
        board_name: Default Pinterest board name applied to all rows.
    """

    def __init__(
        self,
        *,
        csv_path: Path,
        cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
        board_name: str = "",
    ) -> None:
        self._csv_path = Path(csv_path)
        self._cadence = max(1, int(cadence_minutes))
        self._board_name = board_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_rows(self, rows: Sequence[CSVRow]) -> list[dict[str, str]]:
        """Validate *rows*, schedule publish dates, and write the CSV.

        If the destination file already exists, its rows are preserved and
        the new rows are appended after the last existing publish date.

        Args:
            rows: A sequence of :class:`CSVRow` instances to export.

        Returns:
            A list of dicts (one per row) with the final CSV field values.

        Raises:
            ExporterError: If any row fails validation.
        """
        # --- Validate all rows before writing anything ---
        for row in rows:
            _validate_row(row, self._board_name)

        # --- Read existing rows ---
        existing_rows = self._read_existing()

        # --- Compute the base publish date ---
        next_publish = self._next_publish_date(existing_rows)

        # --- Build final rows ---
        all_rows: list[dict[str, str]] = list(existing_rows)
        exported: list[dict[str, str]] = []

        for row in rows:
            rounded = round_up_to_next_window(
                next_publish, ROUNDING_WINDOW_MINUTES
            )
            record: dict[str, str] = {
                "Title": (row.title or "").strip(),
                "Media URL": (row.media_url or "").strip(),
                "Pinterest board": (self._board_name or row.board or "").strip(),
                "Thumbnail": (row.thumbnail or "").strip(),
                "Description": (row.description or "").strip(),
                "Link": (row.link or "").strip(),
                "Publish date": _format_utc(rounded),
                "Keywords": (row.keywords or "").strip(),
            }
            all_rows.append(record)
            exported.append(record)
            next_publish = rounded + timedelta(minutes=self._cadence)

        # --- Write CSV ---
        self._write_csv(all_rows)

        logger.info(
            "CSV export complete: %d rows written to %s",
            len(exported),
            self._csv_path,
        )
        return exported

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_existing(self) -> list[dict[str, str]]:
        """Read existing rows from the CSV file.

        Returns an empty list if the file does not exist or is empty.
        """
        if not self._csv_path.exists():
            return []

        try:
            with self._csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    return []
                rows: list[dict[str, str]] = []
                for row in reader:
                    if not isinstance(row, dict):
                        continue
                    normalized: dict[str, str] = {}
                    for header in CSV_HEADERS:
                        normalized[header] = str(row.get(header, "")).strip()
                    rows.append(normalized)
                return rows
        except Exception:
            logger.warning("Could not read existing CSV at %s", self._csv_path)
            return []

    def _next_publish_date(
        self, existing_rows: list[dict[str, str]]
    ) -> datetime:
        """Determine the next publish date.

        - Empty CSV → ``now_utc + cadence_minutes``
        - Existing rows → ``latest_existing_date + cadence_minutes``
        """
        latest: datetime | None = None
        for row in existing_rows:
            parsed = _parse_publish_date(row.get("Publish date", ""))
            if parsed is None:
                continue
            if latest is None or parsed > latest:
                latest = parsed

        if latest is None:
            return datetime.now(timezone.utc) + timedelta(
                minutes=self._cadence
            )

        return latest + timedelta(minutes=self._cadence)

    def _write_csv(self, rows: list[dict[str, str]]) -> None:
        """Write *all* rows to the CSV file, creating parent dirs as needed."""
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self._csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(CSV_HEADERS))
            writer.writeheader()
            for row in rows:
                writer.writerow({h: row.get(h, "") for h in CSV_HEADERS})
