import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automating_wf.ui.bulk_pipeline import (
    STAGE_GENERATION,
    _detect_resume_stage,
    _latest_run_seed_keywords,
    _preferred_seed_keywords,
    _save_seed_preset,
    _saved_seed_keywords,
)


class BulkPipelineResumeTests(unittest.TestCase):
    def test_detect_resume_stage_treats_article_and_wp_failures_as_generation(self) -> None:
        for status in ("article_failed", "wp_failed"):
            with self.subTest(status=status), TemporaryDirectory() as tmp_dir:
                run_dir = Path(tmp_dir)
                manifest_path = run_dir / "manifest.jsonl"
                manifest_path.write_text(
                    json.dumps(
                        {
                            "run_id": "20260218_100000",
                            "blog_suffix": "THE_SUNDAY_PATIO",
                            "seed_keyword": "backyard fence ideas",
                            "status": status,
                            "event_time": "2026-02-18T10:00:00Z",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                stage = _detect_resume_stage(run_dir)
                self.assertEqual(stage, STAGE_GENERATION)

    def test_save_and_load_seed_presets(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            presets_path = Path(tmp_dir) / "bulk_seed_presets.json"
            with patch("automating_wf.ui.bulk_pipeline._seed_presets_path", return_value=presets_path):
                _save_seed_preset("THE_SUNDAY_PATIO", ["patio furniture", "small patio ideas"])
                loaded = _saved_seed_keywords("THE_SUNDAY_PATIO")

        self.assertEqual(loaded, ["patio furniture", "small patio ideas"])

    def test_latest_run_seed_keywords_reads_run_options(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_root = Path(tmp_dir)
            latest_dir = run_root / "20260316_100000"
            latest_dir.mkdir(parents=True, exist_ok=True)
            (latest_dir / "run_options.json").write_text(
                json.dumps(
                    {
                        "blog_suffix": "THE_SUNDAY_PATIO",
                        "seed_keywords": ["backyard patio", "deck ideas"],
                    }
                ),
                encoding="utf-8",
            )

            with patch("automating_wf.ui.bulk_pipeline.RUN_ROOT", run_root):
                loaded = _latest_run_seed_keywords("THE_SUNDAY_PATIO")

        self.assertEqual(loaded, ["backyard patio", "deck ideas"])

    def test_preferred_seed_keywords_uses_saved_presets_before_env_defaults(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            presets_path = Path(tmp_dir) / "bulk_seed_presets.json"
            with patch("automating_wf.ui.bulk_pipeline._seed_presets_path", return_value=presets_path):
                _save_seed_preset("THE_SUNDAY_PATIO", ["saved one", "saved two"])
                preferred = _preferred_seed_keywords("THE_SUNDAY_PATIO")

        self.assertEqual(preferred, ["saved one", "saved two"])


if __name__ == "__main__":
    unittest.main()
