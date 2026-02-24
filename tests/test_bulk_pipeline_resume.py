import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from automating_wf.ui.bulk_pipeline import STAGE_GENERATION, _detect_resume_stage


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


if __name__ == "__main__":
    unittest.main()
