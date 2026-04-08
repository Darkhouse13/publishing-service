import csv
import json
import tempfile
import unittest
from pathlib import Path

from automating_wf.analysis.trends import SCORING_VERSION, analyze_trends_exports


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
        self.assertTrue(candidates[0].reach_hat > 0)
        self.assertTrue(candidates[0].qualified)

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

    def test_analyze_trends_exports_writes_scoring_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "patio furniture", "Trend Index": 80, "Growth": "20%", "Week 1": 70, "Week 2": 80},
                ],
            )
            analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=5,
            )
            metadata = json.loads((tmp_path / "trends_scoring_metadata.json").read_text())

        self.assertEqual(metadata["scoring_version"], SCORING_VERSION)

    def test_disqualifies_below_min_reach_hat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "patio furniture", "Trend Index": 95, "Growth": "50%", "Week 1": 80, "Week 2": 90},
                    {"Keyword": "patio rugs", "Trend Index": 10, "Growth": "1%", "Week 1": 5, "Week 2": 8},
                ],
            )
            candidates = analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=10,
                min_reach_hat=0.9,
            )
            all_cands = json.loads((tmp_path / "trends_keyword_candidates.json").read_text())

        qualified = [c for c in all_cands if c["qualified"]]
        disqualified = [c for c in all_cands if not c["qualified"]]
        self.assertEqual(len(candidates), len(qualified))
        self.assertTrue(len(disqualified) > 0 or len(all_cands) == 1)

    def test_near_duplicate_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "patio furniture", "Trend Index": 90, "Growth": "30%", "Week 1": 80, "Week 2": 88},
                    {"Keyword": "furniture patio", "Trend Index": 70, "Growth": "20%", "Week 1": 60, "Week 2": 68},
                    {"Keyword": "patio chairs", "Trend Index": 60, "Growth": "10%", "Week 1": 55, "Week 2": 62},
                ],
            )
            candidates = analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=10,
            )
            all_cands = json.loads((tmp_path / "trends_keyword_candidates.json").read_text())
            metadata = json.loads((tmp_path / "trends_scoring_metadata.json").read_text())

        # "patio furniture" and "furniture patio" should collapse
        winner_keywords = [c.keyword.lower() for c in candidates]
        self.assertIn("patio furniture", winner_keywords)
        self.assertNotIn("furniture patio", winner_keywords)
        # "patio chairs" is distinct and should survive
        self.assertIn("patio chairs", winner_keywords)
        # Check suppression metadata
        suppressed = [c for c in all_cands if c.get("suppressed_by")]
        self.assertTrue(len(suppressed) >= 1)
        self.assertGreaterEqual(metadata["suppressed_count"], 1)

    def test_include_keyword_ratio_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            export_file = tmp_path / "trends_seed.csv"
            self._write_csv(
                export_file,
                [
                    {"Keyword": "patio lights", "Trend Index": 80, "Growth": "20%", "Week 1": 70, "Week 2": 78},
                ],
            )
            candidates = analyze_trends_exports(
                export_files_by_seed={"patio": [str(export_file)]},
                run_dir=tmp_path,
                top_n=5,
            )

        self.assertEqual(len(candidates), 1)
        # Default: include_keyword_applied is True, so ratio should be 1.0
        self.assertAlmostEqual(candidates[0].include_keyword_ratio, 1.0)


if __name__ == "__main__":
    unittest.main()
