import csv
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from automating_wf.export.pinterest_csv import (
    CSV_HEADERS,
    ExporterError,
    append_csv_row,
    build_csv_path_for_blog,
    round_up_to_next_window,
    validate_board_mapping_for_blog,
)
from automating_wf.models.pinterest import CsvRow


class PinterestExporterTests(unittest.TestCase):
    def test_build_csv_path_for_blog_uses_template(self) -> None:
        with patch.dict(
            environ,
            {"PINTEREST_CSV_PATH_TEMPLATE": "exports/pins_{blog_suffix}.csv"},
            clear=False,
        ):
            path = build_csv_path_for_blog("THE_SUNDAY_PATIO")
        self.assertEqual(path.as_posix(), "exports/pins_the_sunday_patio.csv")

    def test_validate_board_mapping_for_blog_missing_suffix_raises(self) -> None:
        with patch.dict(
            environ,
            {"PINTEREST_BOARD_MAP_JSON": '{"THE_SUNDAY_PATIO":{"default":"Patio Inspiration"}}'},
            clear=False,
        ):
            with self.assertRaises(ExporterError):
                validate_board_mapping_for_blog("THE_WEEKEND_FOLIO")

    def test_validate_board_mapping_for_blog_requires_non_empty_default(self) -> None:
        with patch.dict(
            environ,
            {"PINTEREST_BOARD_MAP_JSON": '{"THE_WEEKEND_FOLIO":{"default":"   ","overrides":{}}}'},
            clear=False,
        ):
            with self.assertRaises(ExporterError):
                validate_board_mapping_for_blog("THE_WEEKEND_FOLIO")

    def test_validate_board_mapping_for_blog_accepts_valid_mapping(self) -> None:
        with patch.dict(
            environ,
            {"PINTEREST_BOARD_MAP_JSON": '{"THE_WEEKEND_FOLIO":{"default":"Weekend Lifestyle Ideas","overrides":{}}}'},
            clear=False,
        ):
            validate_board_mapping_for_blog("THE_WEEKEND_FOLIO")

    def test_append_csv_row_writes_pinterest_schema_and_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(
            environ,
            {"WP_TIMEZONE": "UTC"},
            clear=False,
        ):
            csv_path = Path(tmp_dir) / "pinterest_bulk_upload_the_sunday_patio.csv"

            first = CsvRow(
                title="Cozy Patio Setup Ideas",
                description="Smart and practical layout ideas.",
                link="https://example.com/cozy-patio-setup-ideas/",
                image_url="https://example.com/wp-content/uploads/pin1.jpg",
                pinterest_board="Patio Inspiration",
                publish_date="",
                keywords="cozy patio, patio setup ideas",
            )
            first_result = append_csv_row(row=first, csv_path=csv_path, cadence_minutes=240)
            self.assertEqual(first_result["status"], "appended")
            self.assertRegex(first_result["publish_date"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

            duplicate = CsvRow(
                title="Cozy Patio Setup Ideas",
                description="Duplicate title should skip.",
                link="https://example.com/another-link/",
                image_url="https://example.com/wp-content/uploads/pin2.jpg",
                pinterest_board="Patio Inspiration",
                publish_date="",
            )
            duplicate_result = append_csv_row(row=duplicate, csv_path=csv_path, cadence_minutes=240)
            self.assertEqual(duplicate_result["status"], "skipped_duplicate")

            with csv_path.open("r", encoding="utf-8", newline="") as file_handle:
                reader = csv.DictReader(file_handle)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, list(CSV_HEADERS))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Title"], "Cozy Patio Setup Ideas")
            self.assertEqual(rows[0]["Media URL"], "https://example.com/wp-content/uploads/pin1.jpg")
            self.assertEqual(rows[0]["Pinterest board"], "Patio Inspiration")
            self.assertEqual(rows[0]["Keywords"], "cozy patio, patio setup ideas")

    def test_append_csv_row_uses_latest_publish_date_plus_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(
            environ,
            {"WP_TIMEZONE": "UTC"},
            clear=False,
        ):
            csv_path = Path(tmp_dir) / "pins.csv"
            row_one = CsvRow(
                title="Row One",
                description="Desc",
                link="https://example.com/one/",
                image_url="https://example.com/uploads/one.jpg",
                pinterest_board="Board",
                publish_date="2099-01-01T10:00:00",
            )
            append_csv_row(row=row_one, csv_path=csv_path, cadence_minutes=240)

            row_two = CsvRow(
                title="Row Two",
                description="Desc",
                link="https://example.com/two/",
                image_url="https://example.com/uploads/two.jpg",
                pinterest_board="Board",
                publish_date="",
            )
            result = append_csv_row(row=row_two, csv_path=csv_path, cadence_minutes=240)
            self.assertEqual(result["publish_date"], "2099-01-01T14:00:00")

    def test_append_csv_row_migrates_legacy_headers_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, patch.dict(
            environ,
            {"WP_TIMEZONE": "UTC"},
            clear=False,
        ):
            csv_path = Path(tmp_dir) / "pins.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
                writer = csv.DictWriter(
                    file_handle,
                    fieldnames=["Title", "Description", "Link", "Image URL", "Pinterest Board", "Publish Date"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Title": "Legacy Row",
                        "Description": "Legacy description",
                        "Link": "https://example.com/legacy/",
                        "Image URL": "https://example.com/uploads/legacy.jpg",
                        "Pinterest Board": "Legacy Board",
                        "Publish Date": "2099-01-01 10:00",
                    }
                )

            new_row = CsvRow(
                title="New Row",
                description="New description",
                link="https://example.com/new/",
                image_url="https://example.com/uploads/new.jpg",
                pinterest_board="New Board",
                publish_date="",
            )
            append_csv_row(row=new_row, csv_path=csv_path, cadence_minutes=240)

            with csv_path.open("r", encoding="utf-8", newline="") as file_handle:
                reader = csv.DictReader(file_handle)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, list(CSV_HEADERS))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Title"], "Legacy Row")
        self.assertEqual(rows[0]["Media URL"], "https://example.com/uploads/legacy.jpg")
        self.assertEqual(rows[0]["Pinterest board"], "Legacy Board")
        self.assertEqual(rows[0]["Publish date"], "2099-01-01T10:00:00")

    def test_append_csv_row_rejects_overlong_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pins.csv"
            row = CsvRow(
                title="x" * 101,
                description="Desc",
                link="https://example.com/post/",
                image_url="https://example.com/uploads/pin.jpg",
                pinterest_board="Board",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=row, csv_path=csv_path)

    def test_append_csv_row_rejects_overlong_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pins.csv"
            row = CsvRow(
                title="Valid Title",
                description="x" * 501,
                link="https://example.com/post/",
                image_url="https://example.com/uploads/pin.jpg",
                pinterest_board="Board",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=row, csv_path=csv_path)

    def test_append_csv_row_requires_media_url_and_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pins.csv"
            missing_media = CsvRow(
                title="Valid Title",
                description="Desc",
                link="https://example.com/post/",
                image_url="",
                pinterest_board="Board",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=missing_media, csv_path=csv_path)

            missing_board = CsvRow(
                title="Valid Title",
                description="Desc",
                link="https://example.com/post/",
                image_url="https://example.com/uploads/pin.jpg",
                pinterest_board="",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=missing_board, csv_path=csv_path)

    def test_append_csv_row_rejects_invalid_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pins.csv"

            invalid_media = CsvRow(
                title="Valid Title",
                description="Desc",
                link="https://example.com/post/",
                image_url="ftp://example.com/uploads/pin.jpg",
                pinterest_board="Board",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=invalid_media, csv_path=csv_path)

            invalid_link = CsvRow(
                title="Valid Title 2",
                description="Desc",
                link="not-a-url",
                image_url="https://example.com/uploads/pin.jpg",
                pinterest_board="Board",
                publish_date="",
            )
            with self.assertRaises(ExporterError):
                append_csv_row(row=invalid_link, csv_path=csv_path)

    def test_round_up_to_next_window(self) -> None:
        from datetime import datetime

        value = datetime(2026, 2, 16, 10, 7, 15)
        rounded = round_up_to_next_window(value, 15)
        self.assertEqual(rounded.strftime("%Y-%m-%d %H:%M:%S"), "2026-02-16 10:15:00")


if __name__ == "__main__":
    unittest.main()
