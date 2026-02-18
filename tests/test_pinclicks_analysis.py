import tempfile
import unittest
from pathlib import Path

from pinclicks_analysis import rank_pinclicks_keywords
from pinterest_models import PinRecord, SeedScrapeResult


def _seed_result(keyword: str, titles: list[str], scores: list[float]) -> SeedScrapeResult:
    records = []
    for index, (title, score) in enumerate(zip(titles, scores), start=1):
        records.append(
            PinRecord(
                seed_keyword=keyword,
                rank=index,
                pin_url=f"https://example.com/pin/{index}",
                pin_id=str(index),
                title=title,
                description="Helpful guide and ideas",
                tags=["tips", "ideas"],
                engagement={"score_total": score},
                scraped_at="2026-02-16T00:00:00Z",
            )
        )
    return SeedScrapeResult(
        blog_suffix="THE_SUNDAY_PATIO",
        seed_keyword=keyword,
        source_url="https://app.pinclicks.com/top-pins",
        records=records,
        source_file="",
        scraped_at="2026-02-16T00:00:00Z",
    )


class PinClicksAnalysisTests(unittest.TestCase):
    def test_rank_pinclicks_keywords_returns_top_winners(self) -> None:
        high = _seed_result(
            "patio furniture",
            ["Best patio furniture ideas", "Patio furniture guide"],
            [120, 140],
        )
        low = _seed_result(
            "balcony decor",
            ["Balcony decor inspiration", "Small balcony tips"],
            [20, 25],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            winners = rank_pinclicks_keywords(
                scrape_results=[low, high],
                run_dir=Path(tmp_dir),
                top_n=1,
                trend_rank_map={"patio furniture": 2, "balcony decor": 1},
            )

        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].keyword, "patio furniture")
        self.assertEqual(winners[0].pinclicks_rank, 1)

    def test_rank_pinclicks_keywords_handles_partial_rankable_inputs(self) -> None:
        rankable = _seed_result(
            "patio storage",
            ["Patio storage ideas", "Best patio storage tips"],
            [80, 85],
        )
        empty = SeedScrapeResult(
            blog_suffix="THE_SUNDAY_PATIO",
            seed_keyword="appliance garage cabinet",
            source_url="https://app.pinclicks.com/top-pins",
            records=[],
            source_file="",
            scraped_at="2026-02-16T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[empty, rankable],
                run_dir=run_dir,
                top_n=1,
                trend_rank_map={"patio storage": 3},
            )

            self.assertTrue((run_dir / "pinclicks_keyword_scores.json").exists())
            self.assertTrue((run_dir / "run_winners_top1.json").exists())

        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].keyword, "patio storage")
        self.assertEqual(winners[0].pinclicks_rank, 1)


if __name__ == "__main__":
    unittest.main()
