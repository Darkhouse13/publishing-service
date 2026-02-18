import json
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import Mock, patch

from pinterest_analysis import analyze_seed, score_keyword_candidates
from pinterest_models import PinRecord, SeedScrapeResult


def _record(title: str, score_total: float, seed: str = "seed") -> PinRecord:
    return PinRecord(
        seed_keyword=seed,
        rank=1,
        pin_url="https://example.com/pin/1",
        pin_id="1",
        title=title,
        description="",
        tags=[],
        engagement={"score_total": score_total},
        scraped_at="2026-02-16T00:00:00Z",
    )


def _mock_response(content: str) -> Mock:
    response = Mock()
    choice = Mock()
    choice.message.content = content
    response.choices = [choice]
    return response


class PinterestAnalysisTests(unittest.TestCase):
    def test_score_keyword_candidates_uses_frequency_threshold(self) -> None:
        records = [
            _record("alpha beta gamma", 1),
            _record("alpha beta gamma", 1),
        ]
        candidates = score_keyword_candidates(records, min_frequency=3)
        self.assertEqual(candidates, [])

    def test_score_keyword_candidates_tiebreaks_by_engagement(self) -> None:
        records = [
            _record("alpha beta gamma", 1),
            _record("alpha beta gamma", 1),
            _record("alpha beta gamma", 1),
            _record("delta epsilon zeta", 10),
            _record("delta epsilon zeta", 10),
            _record("delta epsilon zeta", 10),
        ]
        candidates = score_keyword_candidates(records, min_frequency=3)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].term, "delta epsilon zeta")

    def test_analyze_seed_truncates_overlong_pin_fields(self) -> None:
        records = [
            _record("delta epsilon zeta", 10),
            _record("delta epsilon zeta", 10),
            _record("delta epsilon zeta", 10),
        ]
        scrape_result = SeedScrapeResult(
            blog_suffix="THE_SUNDAY_PATIO",
            seed_keyword="delta epsilon zeta",
            source_url="https://app.pinclicks.com/top-pins?query=delta+epsilon+zeta",
            records=records,
            scraped_at="2026-02-16T00:00:00Z",
        )

        long_title = "T" * 140
        long_desc = "D" * 620
        payload = {
            "primary_keyword": "delta epsilon zeta",
            "image_generation_prompt": "Photorealistic patio detail",
            "pin_text_overlay": "Simple hook",
            "pin_title": long_title,
            "pin_description": long_desc,
            "cluster_label": "Outdoor Living",
        }
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _mock_response(json.dumps(payload))

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "pinterest_analysis._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ), patch(
            "pinterest_analysis._load_prompt",
            return_value="prompt",
        ), patch.dict(
            environ,
            {"PINTEREST_ANALYSIS_ATTEMPTS": "1"},
            clear=False,
        ):
            output = analyze_seed(
                scrape_result=scrape_result,
                blog_suffix="THE_SUNDAY_PATIO",
                run_dir=Path(tmp_dir),
            )

        self.assertLessEqual(len(output.pin_title), 100)
        self.assertLessEqual(len(output.pin_description), 500)


if __name__ == "__main__":
    unittest.main()
