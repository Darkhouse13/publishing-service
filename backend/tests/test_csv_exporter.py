"""Tests for CSVExporter service.

Validates Pinterest bulk-upload CSV generation with exact column order,
scheduled publish dates, 15-minute window rounding, row data population,
and required-field validation.

Fulfils:
    VAL-CSVX-001 — correct column order
    VAL-CSVX-002 — schedules based on existing rows + cadence
    VAL-CSVX-003 — first row uses current UTC + cadence
    VAL-CSVX-004 — populates row data correctly
    VAL-CSVX-005 — rounds publish dates to 15-minute windows
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.csv_exporter import (
    CSVExporter,
    CSV_HEADERS,
    CSVRow,
    ExporterError,
    round_up_to_next_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read CSV file and return (headers, rows-as-dicts)."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return headers, rows


def _make_row(
    *,
    title: str = "Test Article Title",
    media_url: str = "https://example.com/image.jpg",
    board: str = "My Board",
    description: str = "A test description",
    link: str = "https://example.com/post",
    keywords: str = "test, article",
    thumbnail: str = "",
) -> CSVRow:
    """Create a CSVRow with sensible defaults for testing."""
    return CSVRow(
        title=title,
        media_url=media_url,
        board=board,
        thumbnail=thumbnail,
        description=description,
        link=link,
        keywords=keywords,
    )


# ===========================================================================
# VAL-CSVX-001: CSVExporter writes correct column order
# ===========================================================================


class TestColumnOrder:
    """The generated CSV file's header row is exactly:
    Title,Media URL,Pinterest board,Thumbnail,Description,Link,Publish date,Keywords.
    """

    def test_header_exact_order(self, tmp_path: Path) -> None:
        """First line of CSV matches expected header exactly."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=240,
            board_name="TestBoard",
        )
        row = _make_row()
        exporter.export_rows([row])

        headers, _ = _read_csv(csv_path)
        assert headers == list(CSV_HEADERS)

    def test_header_has_8_columns(self, tmp_path: Path) -> None:
        """Header must contain exactly 8 columns."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=240,
            board_name="TestBoard",
        )
        exporter.export_rows([_make_row()])

        headers, _ = _read_csv(csv_path)
        assert len(headers) == 8

    def test_csv_headers_constant(self) -> None:
        """CSV_HEADERS constant has the exact expected value."""
        expected = [
            "Title",
            "Media URL",
            "Pinterest board",
            "Thumbnail",
            "Description",
            "Link",
            "Publish date",
            "Keywords",
        ]
        assert list(CSV_HEADERS) == expected


# ===========================================================================
# VAL-CSVX-002: Schedules based on existing rows + cadence
# ===========================================================================


class TestSchedulingFromExistingRows:
    """When the CSV already contains N rows, the next row's publish date
    is scheduled at latest_existing_date + cadence_minutes.
    """

    def test_appends_after_existing_rows(self, tmp_path: Path) -> None:
        """Appending rows to an existing CSV schedules from the last date."""
        csv_path = tmp_path / "export.csv"
        cadence = 120
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="TestBoard",
        )

        # Export first batch of 2 rows
        exporter.export_rows([_make_row(title=f"Article {i}") for i in range(2)])

        _, rows_first = _read_csv(csv_path)
        assert len(rows_first) == 2

        # Parse the last publish date from the first batch
        last_date_str = rows_first[-1]["Publish date"]
        last_date = datetime.fromisoformat(last_date_str)

        # Export a second batch — should schedule from last_date + cadence
        exporter2 = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="TestBoard",
        )
        exporter2.export_rows([_make_row(title="Article 2")])

        _, rows_all = _read_csv(csv_path)
        assert len(rows_all) == 3

        new_date_str = rows_all[-1]["Publish date"]
        new_date = datetime.fromisoformat(new_date_str)

        expected = last_date + timedelta(minutes=cadence)
        # Allow a few seconds of tolerance for execution time
        assert abs((new_date - expected).total_seconds()) < 120

    def test_existing_csv_with_manual_date(self, tmp_path: Path) -> None:
        """When CSV has existing rows with known dates, new rows follow."""
        csv_path = tmp_path / "export.csv"
        cadence = 60

        # Write a CSV with a known publish date
        known_date = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(CSV_HEADERS))
            writer.writeheader()
            writer.writerow({
                "Title": "Existing",
                "Media URL": "https://example.com/existing.jpg",
                "Pinterest board": "Board",
                "Thumbnail": "",
                "Description": "desc",
                "Link": "",
                "Publish date": known_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "Keywords": "",
            })

        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="Board",
        )
        exporter.export_rows([_make_row(title="New Article")])

        _, rows = _read_csv(csv_path)
        assert len(rows) == 2

        new_date = datetime.fromisoformat(rows[-1]["Publish date"])
        expected = known_date + timedelta(minutes=cadence)
        assert new_date == expected


# ===========================================================================
# VAL-CSVX-003: First row uses current UTC + cadence
# ===========================================================================


class TestFirstRowScheduling:
    """For an empty CSV, the first row's publish date is
    now_utc + csv_cadence_minutes.
    """

    def test_first_row_publish_date_near_now_plus_cadence(
        self, tmp_path: Path
    ) -> None:
        """Publish date is within now_utc + cadence_minutes (rounded up)."""
        csv_path = tmp_path / "export.csv"
        cadence = 180

        before = datetime.now(timezone.utc)
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="TestBoard",
        )
        exporter.export_rows([_make_row()])
        after = datetime.now(timezone.utc)

        _, rows = _read_csv(csv_path)
        assert len(rows) == 1

        pub_date = datetime.fromisoformat(rows[0]["Publish date"])
        # The publish date should be >= before + cadence
        # (because rounding only pushes it later, never earlier)
        assert pub_date >= before + timedelta(minutes=cadence)
        # And not more than 15 minutes after after + cadence
        # (rounding can add at most 14 minutes 59 seconds)
        assert pub_date <= after + timedelta(minutes=cadence + 15)

    def test_multiple_rows_increasing_dates(self, tmp_path: Path) -> None:
        """Multiple rows exported at once have increasing publish dates."""
        csv_path = tmp_path / "export.csv"
        cadence = 30

        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="TestBoard",
        )
        exporter.export_rows([_make_row(title=f"Art {i}") for i in range(3)])

        _, rows = _read_csv(csv_path)
        assert len(rows) == 3

        dates = [datetime.fromisoformat(r["Publish date"]) for r in rows]
        for i in range(1, len(dates)):
            diff = (dates[i] - dates[i - 1]).total_seconds() / 60
            assert diff == cadence


# ===========================================================================
# VAL-CSVX-004: Populates row data correctly
# ===========================================================================


class TestRowData:
    """Given an article with known title, hero_image_url, pin_description,
    and keyword, the CSV row contains the article's title in the Title column,
    the hero_image_url in Media URL, the Pinterest board in Pinterest board,
    the pin_description in Description, and the keyword in Keywords.
    """

    def test_row_fields_populated(self, tmp_path: Path) -> None:
        """CSV row parsed via csv.DictReader matches expected field values."""
        csv_path = tmp_path / "export.csv"
        board = "Outdoor Living Ideas"
        row = CSVRow(
            title="DIY Stone Fire Pit Guide",
            media_url="https://example.com/fire-pit.jpg",
            board=board,
            thumbnail="",
            description="Learn to build a cozy fire pit.",
            link="https://example.com/fire-pit-post",
            keywords="fire pit, diy, outdoor",
        )

        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=240,
            board_name=board,
        )
        exporter.export_rows([row])

        _, rows = _read_csv(csv_path)
        assert len(rows) == 1

        assert rows[0]["Title"] == "DIY Stone Fire Pit Guide"
        assert rows[0]["Media URL"] == "https://example.com/fire-pit.jpg"
        assert rows[0]["Pinterest board"] == board
        assert rows[0]["Description"] == "Learn to build a cozy fire pit."
        assert rows[0]["Link"] == "https://example.com/fire-pit-post"
        assert rows[0]["Keywords"] == "fire pit, diy, outdoor"

    def test_board_name_from_exporter_used(self, tmp_path: Path) -> None:
        """Pinterest board comes from the exporter's board_name setting."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="My Custom Board",
        )
        exporter.export_rows([_make_row()])

        _, rows = _read_csv(csv_path)
        assert rows[0]["Pinterest board"] == "My Custom Board"

    def test_thumbnail_default_empty(self, tmp_path: Path) -> None:
        """Thumbnail column defaults to empty string when not provided."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        exporter.export_rows([_make_row(thumbnail="")])

        _, rows = _read_csv(csv_path)
        assert rows[0]["Thumbnail"] == ""

    def test_thumbnail_populated_when_provided(self, tmp_path: Path) -> None:
        """Thumbnail column is populated when provided."""
        csv_path = tmp_path / "export.csv"
        row = CSVRow(
            title="Test",
            media_url="https://example.com/img.jpg",
            board="Board",
            thumbnail="https://example.com/thumb.jpg",
            description="desc",
            link="",
            keywords="kw",
        )
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        exporter.export_rows([row])

        _, rows = _read_csv(csv_path)
        assert rows[0]["Thumbnail"] == "https://example.com/thumb.jpg"

    def test_empty_link_and_keywords(self, tmp_path: Path) -> None:
        """Link and Keywords can be empty strings."""
        csv_path = tmp_path / "export.csv"
        row = CSVRow(
            title="Test",
            media_url="https://example.com/img.jpg",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="",
        )
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        exporter.export_rows([row])

        _, rows = _read_csv(csv_path)
        assert rows[0]["Link"] == ""
        assert rows[0]["Keywords"] == ""


# ===========================================================================
# VAL-CSVX-005: Rounds publish dates to 15-minute windows
# ===========================================================================


class TestRounding:
    """Publish dates are rounded up to the next 15-minute boundary.
    The calculated publish date is a valid ISO UTC datetime.
    """

    def test_round_up_basic(self) -> None:
        """round_up_to_next_window rounds minutes to next 15-min slot."""
        dt = datetime(2026, 4, 14, 10, 7, 30, tzinfo=timezone.utc)
        rounded = round_up_to_next_window(dt, window_minutes=15)
        assert rounded.minute == 15
        assert rounded.second == 0

    def test_round_up_at_exact_boundary(self) -> None:
        """Exact boundary is kept as-is."""
        dt = datetime(2026, 4, 14, 10, 15, 0, tzinfo=timezone.utc)
        rounded = round_up_to_next_window(dt, window_minutes=15)
        assert rounded.minute == 15
        assert rounded.second == 0

    def test_round_up_past_boundary(self) -> None:
        """Just past a boundary rounds to the next one."""
        dt = datetime(2026, 4, 14, 10, 15, 1, tzinfo=timezone.utc)
        rounded = round_up_to_next_window(dt, window_minutes=15)
        assert rounded.minute == 30

    def test_round_up_minutes_component_valid(self) -> None:
        """Rounded datetime minutes are in [0, 15, 30, 45]."""
        for minute in range(60):
            dt = datetime(2026, 4, 14, 10, minute, 30, tzinfo=timezone.utc)
            rounded = round_up_to_next_window(dt, window_minutes=15)
            assert rounded.minute in (0, 15, 30, 45)

    def test_exported_dates_are_rounded(self, tmp_path: Path) -> None:
        """All publish dates in the CSV have minutes in [0, 15, 30, 45]."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=7,  # non-multiple of 15 to exercise rounding
            board_name="Board",
        )
        exporter.export_rows([_make_row(title=f"Art {i}") for i in range(5)])

        _, rows = _read_csv(csv_path)
        for row in rows:
            pub_date = datetime.fromisoformat(row["Publish date"])
            assert pub_date.minute in (0, 15, 30, 45), (
                f"Publish date {pub_date} not on 15-min boundary"
            )

    def test_publish_date_is_valid_iso_utc(self, tmp_path: Path) -> None:
        """The publish date is a valid ISO UTC datetime string."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=240,
            board_name="Board",
        )
        exporter.export_rows([_make_row()])

        _, rows = _read_csv(csv_path)
        date_str = rows[0]["Publish date"]
        parsed = datetime.fromisoformat(date_str)
        assert parsed.tzinfo is not None

    def test_round_up_crossing_hour(self) -> None:
        """Rounding near hour boundary crosses to next hour correctly."""
        dt = datetime(2026, 4, 14, 10, 52, 0, tzinfo=timezone.utc)
        rounded = round_up_to_next_window(dt, window_minutes=15)
        assert rounded.hour == 11
        assert rounded.minute == 0

    def test_round_up_crossing_day(self) -> None:
        """Rounding near midnight crosses to next day correctly."""
        dt = datetime(2026, 4, 14, 23, 52, 0, tzinfo=timezone.utc)
        rounded = round_up_to_next_window(dt, window_minutes=15)
        assert rounded.day == 15
        assert rounded.hour == 0
        assert rounded.minute == 0


# ===========================================================================
# Validation: required fields
# ===========================================================================


class TestRequiredFieldValidation:
    """Validates required fields (title, media URL, board)."""

    def test_empty_title_raises(self, tmp_path: Path) -> None:
        """Empty title raises ExporterError."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        row = CSVRow(
            title="",
            media_url="https://example.com/img.jpg",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError, match="[Tt]itle"):
            exporter.export_rows([row])

    def test_empty_media_url_raises(self, tmp_path: Path) -> None:
        """Empty media URL raises ExporterError."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        row = CSVRow(
            title="Title",
            media_url="",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError, match="[Mm]edia.*[Uu][Rr][Ll]|[Mm]edia"):
            exporter.export_rows([row])

    def test_empty_board_raises(self, tmp_path: Path) -> None:
        """Empty board raises ExporterError."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="",
        )
        row = CSVRow(
            title="Title",
            media_url="https://example.com/img.jpg",
            board="",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError, match="[Bb]oard"):
            exporter.export_rows([row])

    def test_whitespace_title_raises(self, tmp_path: Path) -> None:
        """Whitespace-only title raises ExporterError."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        row = CSVRow(
            title="   ",
            media_url="https://example.com/img.jpg",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError, match="[Tt]itle"):
            exporter.export_rows([row])

    def test_media_url_must_be_http(self, tmp_path: Path) -> None:
        """Non-HTTP media URL raises ExporterError."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        row = CSVRow(
            title="Title",
            media_url="ftp://example.com/img.jpg",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError, match="[Mm]edia.*[Uu][Rr][Ll]|http"):
            exporter.export_rows([row])

    def test_valid_rows_pass_validation(self, tmp_path: Path) -> None:
        """Valid rows export without error."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        # Should not raise
        exporter.export_rows([_make_row()])

        _, rows = _read_csv(csv_path)
        assert len(rows) == 1

    def test_partial_invalid_stops_all(self, tmp_path: Path) -> None:
        """If any row is invalid, no rows are written."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        bad_row = CSVRow(
            title="",  # invalid
            media_url="https://example.com/img.jpg",
            board="Board",
            thumbnail="",
            description="desc",
            link="",
            keywords="kw",
        )
        with pytest.raises(ExporterError):
            exporter.export_rows([_make_row(title="Valid"), bad_row])

        # CSV should not exist (no partial write)
        assert not csv_path.exists()


# ===========================================================================
# Integration: end-to-end export
# ===========================================================================


class TestEndToEnd:
    """Full export flow: multiple articles, dates, reading back."""

    def test_export_5_articles(self, tmp_path: Path) -> None:
        """Export 5 articles produces 5 rows with correct data."""
        csv_path = tmp_path / "export.csv"
        cadence = 120
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name="Test Board",
        )

        rows_in = [
            CSVRow(
                title=f"Article {i}",
                media_url=f"https://example.com/img{i}.jpg",
                board="Test Board",
                thumbnail="",
                description=f"Description for article {i}",
                link=f"https://example.com/post{i}",
                keywords=f"keyword{i}, test",
            )
            for i in range(5)
        ]
        exporter.export_rows(rows_in)

        headers, rows_out = _read_csv(csv_path)
        assert headers == list(CSV_HEADERS)
        assert len(rows_out) == 5

        # Check each row's data
        for i, row in enumerate(rows_out):
            assert row["Title"] == f"Article {i}"
            assert row["Media URL"] == f"https://example.com/img{i}.jpg"
            assert row["Pinterest board"] == "Test Board"
            assert row["Description"] == f"Description for article {i}"
            assert row["Link"] == f"https://example.com/post{i}"
            assert row["Keywords"] == f"keyword{i}, test"

        # Check dates are spaced by cadence
        dates = [datetime.fromisoformat(r["Publish date"]) for r in rows_out]
        for i in range(1, len(dates)):
            diff_minutes = (dates[i] - dates[i - 1]).total_seconds() / 60
            assert diff_minutes == cadence

    def test_export_empty_list_creates_file_with_header(self, tmp_path: Path) -> None:
        """Exporting zero rows creates a file with only the header."""
        csv_path = tmp_path / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        exporter.export_rows([])

        assert csv_path.exists()
        headers, rows = _read_csv(csv_path)
        assert headers == list(CSV_HEADERS)
        assert len(rows) == 0

    def test_export_creates_parent_directories(self, tmp_path: Path) -> None:
        """Export creates parent directories if they don't exist."""
        csv_path = tmp_path / "nested" / "dir" / "export.csv"
        exporter = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=60,
            board_name="Board",
        )
        exporter.export_rows([_make_row()])

        assert csv_path.exists()

    def test_append_to_existing_csv(self, tmp_path: Path) -> None:
        """Exporting to an existing file appends new rows."""
        csv_path = tmp_path / "export.csv"
        cadence = 60
        board = "My Board"

        # First export
        exporter1 = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name=board,
        )
        exporter1.export_rows([_make_row(title="First")])

        _, rows1 = _read_csv(csv_path)
        assert len(rows1) == 1

        # Second export (append)
        exporter2 = CSVExporter(
            csv_path=csv_path,
            cadence_minutes=cadence,
            board_name=board,
        )
        exporter2.export_rows([_make_row(title="Second")])

        _, rows2 = _read_csv(csv_path)
        assert len(rows2) == 2
        assert rows2[0]["Title"] == "First"
        assert rows2[1]["Title"] == "Second"
