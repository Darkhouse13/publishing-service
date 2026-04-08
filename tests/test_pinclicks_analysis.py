import json
import tempfile
import unittest
from pathlib import Path

from automating_wf.analysis.pinclicks import pareto_frontier_2d, rank_pinclicks_keywords
from automating_wf.models.pinterest import PinRecord, SeedScrapeResult


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
                reach_hat_map={"patio furniture": 0.8, "balcony decor": 0.4},
            )

        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].keyword, "patio furniture")
        self.assertEqual(winners[0].pinclicks_rank, 1)
        self.assertTrue(winners[0].click_score > 0)
        self.assertAlmostEqual(winners[0].reach_hat, 0.8)
        self.assertIn(winners[0].selection_reason, ("pareto_frontier", "backfill"))

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
                reach_hat_map={"patio storage": 0.6},
            )

            self.assertTrue((run_dir / "pinclicks_keyword_scores.json").exists())
            self.assertTrue((run_dir / "run_winners_top1.json").exists())

        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].keyword, "patio storage")
        self.assertEqual(winners[0].pinclicks_rank, 1)

    def test_rank_pinclicks_keywords_marks_engagement_unavailable(self) -> None:
        zero = _seed_result(
            "patio refresh",
            ["Patio refresh ideas", "Patio refresh guide"],
            [0, 0],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[zero],
                run_dir=run_dir,
                top_n=1,
                trend_rank_map={"patio refresh": 1},
                reach_hat_map={"patio refresh": 0.7},
            )
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(len(winners), 1)
        self.assertFalse(winners[0].engagement_available)
        self.assertFalse(metadata["engagement_signal_available"])
        self.assertEqual(metadata["keywords_without_engagement"], ["patio refresh"])

    def test_rank_pinclicks_keywords_populates_ctr_and_pareto_fields(self) -> None:
        result = _seed_result(
            "patio chairs",
            ["Best patio chairs guide", "How to choose patio chairs"],
            [100, 110],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            winners = rank_pinclicks_keywords(
                scrape_results=[result],
                run_dir=Path(tmp_dir),
                top_n=1,
                reach_hat_map={"patio chairs": 0.9},
            )

        self.assertEqual(len(winners), 1)
        w = winners[0]
        self.assertTrue(0.0 <= w.ctr_hat <= 1.0)
        self.assertTrue(0.0 <= w.ctr_confidence <= 1.0)
        self.assertAlmostEqual(w.reach_hat, 0.9)
        self.assertAlmostEqual(w.click_score, w.reach_hat * w.ctr_hat, places=5)
        self.assertTrue(w.is_pareto_efficient)
        self.assertIn(w.selection_reason, ("pareto_frontier", "backfill"))

    def test_selection_reason_assigned_to_all_candidates(self) -> None:
        """Every candidate in the full artifact should have a selection_reason."""
        high = _seed_result(
            "patio furniture",
            ["Best patio furniture ideas", "Patio furniture guide"],
            [120, 140],
        )
        low = _seed_result(
            "balcony decor",
            ["Balcony decor inspiration", "Small balcony style"],
            [20, 25],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            rank_pinclicks_keywords(
                scrape_results=[low, high],
                run_dir=run_dir,
                top_n=1,
                reach_hat_map={"patio furniture": 0.8, "balcony decor": 0.4},
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())

        # Winner should have a selection reason, non-winner should have "" or a non-winner reason
        reasons = [s["selection_reason"] for s in all_scores]
        self.assertTrue(any(r in ("pareto_frontier", "backfill") for r in reasons))

    def test_near_duplicate_suppression(self) -> None:
        """Near-duplicate keywords should be suppressed in favor of highest click_score."""
        original = _seed_result(
            "patio furniture",
            ["Best patio furniture ideas", "Patio furniture guide"],
            [120, 140],
        )
        plural = _seed_result(
            "patio furnitures",
            ["Best patio furnitures ideas", "Patio furnitures guide"],
            [50, 60],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[original, plural],
                run_dir=run_dir,
                top_n=2,
                reach_hat_map={"patio furniture": 0.8, "patio furnitures": 0.7},
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())

        # Only the better variant should be a winner
        winner_keywords = [w.keyword for w in winners]
        self.assertIn("patio furniture", winner_keywords)
        # The duplicate should be marked as suppressed
        suppressed = [s for s in all_scores if s["selection_reason"] == "suppressed_duplicate"]
        self.assertTrue(len(suppressed) >= 1)

    def test_min_click_score_gate(self) -> None:
        """Candidates below min_click_score should be disqualified."""
        weak = _seed_result(
            "niche obscure topic",
            ["Some vague inspiration"],
            [1],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[weak],
                run_dir=run_dir,
                top_n=1,
                reach_hat_map={"niche obscure topic": 0.01},
                min_click_score=0.5,
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())

        # With very high min_click_score, weak candidate should be disqualified
        disqualified = [s for s in all_scores if s["selection_reason"] == "disqualified"]
        self.assertTrue(len(winners) == 0 or len(disqualified) > 0)


class ParetoFrontierTests(unittest.TestCase):
    def test_pareto_frontier_basic(self) -> None:
        items = [
            {"x": 1.0, "y": 0.5},  # dominated by item 1
            {"x": 1.0, "y": 1.0},  # frontier
            {"x": 0.5, "y": 1.0},  # dominated by item 1
            {"x": 0.8, "y": 0.8},  # dominated by item 1
        ]
        frontier = pareto_frontier_2d(items, "x", "y")
        self.assertEqual(frontier, [1])

    def test_pareto_frontier_multiple_non_dominated(self) -> None:
        items = [
            {"x": 1.0, "y": 0.2},  # frontier (best x)
            {"x": 0.2, "y": 1.0},  # frontier (best y)
            {"x": 0.5, "y": 0.5},  # dominated by neither (also frontier)
        ]
        frontier = sorted(pareto_frontier_2d(items, "x", "y"))
        self.assertEqual(frontier, [0, 1, 2])

    def test_pareto_frontier_empty(self) -> None:
        self.assertEqual(pareto_frontier_2d([], "x", "y"), [])

    def test_pareto_frontier_single_item(self) -> None:
        items = [{"x": 0.5, "y": 0.5}]
        self.assertEqual(pareto_frontier_2d(items, "x", "y"), [0])


if __name__ == "__main__":
    unittest.main()
