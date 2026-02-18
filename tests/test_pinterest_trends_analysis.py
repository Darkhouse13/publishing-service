import csv
import tempfile
import unittest
from pathlib import Path

from pinterest_trends_analysis import analyze_trends_exports


class PinterestTrendsAnalysisTests(unittest.TestCase):
    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        headers = list(rows[0].keys()) if rows else ["Keyword"]
        with path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_analyze_trends_exports_ranks_top_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "patio furniture", "Trend Index": 92, "Growth": "35%", "Week 1": 80, "Week 2": 89},
                    {"Keyword": "balcony plants", "Trend Index": 70, "Growth": "12%", "Week 1": 65, "Week 2": 68},
                    {"Keyword": "patio furniture", "Trend Index": 88, "Growth": "28%", "Week 1": 76, "Week 2": 84},
                ],
            )
            candidates = analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=2,
                region="GLOBAL",
                time_range="12m",
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].rank, 1)
        self.assertEqual(candidates[0].keyword.lower(), "patio furniture")

    def test_analyze_trends_exports_supports_xlsx(self) -> None:
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(["Keyword", "Trend Index", "Growth", "Week 1", "Week 2"])
            worksheet.append(["dark mode desk", 90, "40%", 75, 88])
            worksheet.append(["focus lighting", 65, "15%", 50, 63])
            workbook.save(str(export_file))
            workbook.close()

            candidates = analyze_trends_exports(
                export_files_by_seed={"desk": [str(export_file)]},
                run_dir=tmp_path,
                top_n=1,
                region="GLOBAL",
                time_range="12m",
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].keyword.lower(), "dark mode desk")

    def test_analyze_trends_exports_skips_metadata_and_rank_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "pinterest_trends_report.csv"
            export_file.write_text(
                "\n".join(
                    [
                        "Outil Pinterest Trends - https://trends.pinterest.com/search/?q=patio",
                        "Filtres sélectionnés",
                        "Types de tendance,Les tendances en vogue",
                        "Période,90 jours",
                        "",
                        "Rang,Tendance,Variation hebdomadaire,Variation mensuelle,Variation annuelle,2025-11-14,2025-11-21",
                        "1,patio furniture,40%,900%,200%,0,100",
                        "2,backyard seating ideas,20%,300%,120%,0,90",
                        "3,outdoor lighting patio,10%,100%,80%,10,80",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=5,
                region="GLOBAL",
                time_range="12m",
            )

        keywords = [item.keyword for item in candidates]
        self.assertIn("patio furniture", keywords)
        self.assertNotIn("backyard seating ideas", keywords)
        self.assertIn("outdoor lighting patio", keywords)
        self.assertNotIn("1", keywords)
        self.assertNotIn("2", keywords)
        self.assertNotIn("3", keywords)

    def test_analyze_trends_exports_filters_keywords_not_matching_seed_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "small tattoos", "Trend Index": 95, "Growth": "80%", "Week 1": 70, "Week 2": 90},
                    {"Keyword": "patio layout", "Trend Index": 70, "Growth": "20%", "Week 1": 65, "Week 2": 70},
                    {"Keyword": "backyard patio", "Trend Index": 72, "Growth": "25%", "Week 1": 66, "Week 2": 74},
                ],
            )

            candidates = analyze_trends_exports(
                export_files_by_seed={"small patio ideas": [str(export_file)]},
                run_dir=tmp_path,
                top_n=5,
                region="GLOBAL",
                time_range="12m",
            )

        keywords = [item.keyword.lower() for item in candidates]
        self.assertIn("patio layout", keywords)
        self.assertIn("backyard patio", keywords)
        self.assertNotIn("small tattoos", keywords)


if __name__ == "__main__":
    unittest.main()
