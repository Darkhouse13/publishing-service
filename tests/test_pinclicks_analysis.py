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

        reasons = [s["selection_reason"] for s in all_scores]
        self.assertTrue(any(r in ("pareto_frontier", "backfill") for r in reasons))

    def test_near_duplicate_suppression(self) -> None:
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

        winner_keywords = [w.keyword for w in winners]
        self.assertIn("patio furniture", winner_keywords)
        suppressed = [s for s in all_scores if s["selection_reason"] == "suppressed_duplicate"]
        self.assertTrue(len(suppressed) >= 1)

    def test_min_click_score_gate(self) -> None:
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

        disqualified = [s for s in all_scores if s["selection_reason"] == "disqualified"]
        self.assertTrue(len(winners) == 0 or len(disqualified) > 0)

    # ── Problem 2: Missing engagement handled correctly ─────────────────

    def test_missing_engagement_uses_no_engagement_ctr_model(self) -> None:
        """Keywords without engagement should use the no_engagement CTR model."""
        with_eng = _seed_result(
            "patio furniture",
            ["Best patio furniture guide", "Patio furniture tips"],
            [100, 120],
        )
        without_eng = _seed_result(
            "patio chairs",
            ["Patio chairs ideas", "How to pick patio chairs"],
            [0, 0],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            rank_pinclicks_keywords(
                scrape_results=[with_eng, without_eng],
                run_dir=run_dir,
                top_n=2,
                reach_hat_map={"patio furniture": 0.8, "patio chairs": 0.7},
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        models = {s["keyword"]: s["ctr_model"] for s in all_scores}
        self.assertEqual(models["patio furniture"], "full")
        self.assertEqual(models["patio chairs"], "no_engagement")
        self.assertAlmostEqual(metadata["engagement_coverage_ratio"], 0.5, places=2)
        self.assertTrue(metadata["ctr_model_partial"])
        self.assertEqual(metadata["full_ctr_model_count"], 1)
        self.assertEqual(metadata["no_engagement_ctr_model_count"], 1)

    def test_all_missing_engagement_warns_and_uses_fallback(self) -> None:
        """When no keyword has engagement, all should use no_engagement model."""
        a = _seed_result("kw_a", ["Guide to A", "Tips for A"], [0, 0])
        b = _seed_result("kw_b", ["Guide to B", "Tips for B"], [0, 0])
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            rank_pinclicks_keywords(
                scrape_results=[a, b],
                run_dir=run_dir,
                top_n=2,
                reach_hat_map={"kw_a": 0.6, "kw_b": 0.5},
            )
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        self.assertAlmostEqual(metadata["engagement_coverage_ratio"], 0.0)
        self.assertTrue(metadata["ctr_model_partial"])
        self.assertEqual(metadata["no_engagement_ctr_model_count"], 2)
        self.assertTrue(any("Engagement data" in w for w in metadata["run_warnings"]))

    def test_engagement_not_treated_as_zero(self) -> None:
        """A keyword with real engagement should use a different CTR model
        than one without, producing different effective weight distributions."""
        with_eng = _seed_result(
            "patio furniture",
            ["Best patio furniture guide", "How to choose patio furniture"],
            [200, 300],
        )
        # Third keyword ensures percentile ranks differentiate.
        middle = _seed_result(
            "patio decor",
            ["Patio decor tips", "Easy patio decorating guide"],
            [50, 60],
        )
        without_eng = _seed_result(
            "patio rugs",
            ["Patio rugs inspiration", "Beautiful patio rug"],
            [0, 0],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            winners = rank_pinclicks_keywords(
                scrape_results=[with_eng, middle, without_eng],
                run_dir=Path(tmp_dir),
                top_n=3,
                reach_hat_map={"patio furniture": 0.7, "patio decor": 0.6, "patio rugs": 0.7},
            )

        scores = {w.keyword: w for w in winners}
        self.assertEqual(scores["patio furniture"].ctr_model, "full")
        self.assertEqual(scores["patio rugs"].ctr_model, "no_engagement")
        # The full model uses 3-component weights; the no_engagement model uses 2.
        # With different pin content, their ctr_hat should differ.
        self.assertNotAlmostEqual(
            scores["patio furniture"].ctr_hat,
            scores["patio rugs"].ctr_hat,
            places=2,
        )

    # ── Problem 3: Topic-family suppression ──────────────────────────────

    def test_topic_family_suppression_groups_similar_keywords(self) -> None:
        """Keywords in the same editorial family should be suppressed."""
        tank_top = _seed_result(
            "crochet tank top free pattern",
            ["Best crochet tank top guide", "Free pattern for tank top"],
            [100, 110],
        )
        halter_top = _seed_result(
            "crochet halter top pattern",
            ["Crochet halter top guide", "Halter top pattern"],
            [80, 90],
        )
        beach_cover = _seed_result(
            "crochet beach cover up",
            ["Best beach cover up ideas", "Crochet beach wrap"],
            [70, 80],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[tank_top, halter_top, beach_cover],
                run_dir=run_dir,
                top_n=3,
                reach_hat_map={
                    "crochet tank top free pattern": 0.8,
                    "crochet halter top pattern": 0.75,
                    "crochet beach cover up": 0.7,
                },
                family_similarity_threshold=0.5,
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        winner_keywords = [w.keyword for w in winners]
        # tank_top and halter_top share "crochet" + "top" after modifier stripping
        # so one should be suppressed as a family duplicate
        family_suppressed = [s for s in all_scores if s["selection_reason"] == "suppressed_family"]
        self.assertTrue(len(family_suppressed) >= 1)
        self.assertGreaterEqual(metadata["suppressed_family_count"], 1)

        # beach_cover has different core tokens ("beach", "cover") so should survive
        self.assertIn("crochet beach cover up", winner_keywords)

    def test_wp_slug_overlap_suppression(self) -> None:
        """Keywords matching existing WP slugs should be suppressed."""
        result = _seed_result(
            "patio furniture",
            ["Best patio furniture guide", "Patio furniture tips"],
            [100, 120],
        )
        result2 = _seed_result(
            "garden lighting",
            ["Garden lighting guide", "Best garden lights"],
            [90, 100],
        )
        existing_posts = [
            {"slug": "patio-furniture-3", "title": "Patio Furniture Guide", "url": "https://example.com/patio-furniture-3/", "date": "2026-04-01"},
            {"slug": "balcony-decor", "title": "Balcony Decor Ideas", "url": "", "date": ""},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[result, result2],
                run_dir=run_dir,
                top_n=2,
                reach_hat_map={"patio furniture": 0.8, "garden lighting": 0.7},
                existing_wp_posts=existing_posts,
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        wp_suppressed = [s for s in all_scores if s["selection_reason"] == "suppressed_wp_overlap"]
        self.assertTrue(len(wp_suppressed) >= 1)
        self.assertEqual(wp_suppressed[0]["keyword"], "patio furniture")
        self.assertTrue(wp_suppressed[0]["wp_overlap_detail"])
        self.assertGreaterEqual(metadata["suppressed_wp_overlap_count"], 1)
        self.assertEqual(metadata["wp_posts_checked"], 2)

        winner_keywords = [w.keyword for w in winners]
        self.assertIn("garden lighting", winner_keywords)

    def test_wp_title_similarity_suppresses_when_slug_differs(self) -> None:
        """Even when slugs differ, high title similarity should suppress."""
        result = _seed_result(
            "crochet summer tops",
            ["Best crochet summer tops guide", "Free summer top patterns"],
            [100, 110],
        )
        result2 = _seed_result(
            "knitting basics",
            ["Knitting basics guide", "Learn to knit"],
            [80, 90],
        )
        existing_posts = [
            {
                "slug": "free-crochet-summer-top-patterns",
                "title": "Free Crochet Summer Top Patterns",
                "url": "https://example.com/free-crochet-summer-top-patterns/",
                "date": "2026-03-20",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[result, result2],
                run_dir=run_dir,
                top_n=2,
                reach_hat_map={"crochet summer tops": 0.8, "knitting basics": 0.6},
                existing_wp_posts=existing_posts,
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())

        # "crochet summer tops" content tokens ≈ existing title tokens → suppress
        wp_suppressed = [s for s in all_scores if s["selection_reason"] == "suppressed_wp_overlap"]
        self.assertTrue(len(wp_suppressed) >= 1)
        self.assertEqual(wp_suppressed[0]["keyword"], "crochet summer tops")
        # "knitting basics" is distinct → survives
        winner_keywords = [w.keyword for w in winners]
        self.assertIn("knitting basics", winner_keywords)

    def test_wp_containment_overlap_warns_but_keeps_distinct_topic(self) -> None:
        """Containment alone should warn, not suppress broader-but-distinct topics."""
        result = _seed_result(
            "spring mocktail recipes",
            ["Best spring mocktail recipes", "Easy mocktail recipe ideas"],
            [100, 110],
        )
        existing_posts = [
            {
                "slug": "dirty-alani-recipes-6",
                "title": "Dirty Alani Recipes: The Ultimate Caffeinated Mocktail Guide",
                "url": "https://example.com/dirty-alani-recipes-6/",
                "date": "2026-03-20",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[result],
                run_dir=run_dir,
                top_n=1,
                reach_hat_map={"spring mocktail recipes": 0.8},
                existing_wp_posts=existing_posts,
            )
            all_scores = json.loads((run_dir / "pinclicks_keyword_scores.json").read_text())
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        self.assertEqual([w.keyword for w in winners], ["spring mocktail recipes"])
        candidate = next(s for s in all_scores if s["keyword"] == "spring mocktail recipes")
        self.assertIn(candidate["selection_reason"], ("pareto_frontier", "backfill"))
        self.assertIn("containment", candidate["wp_overlap_detail"])
        self.assertGreaterEqual(metadata["wp_overlap_warning_count"], 1)

    def test_wp_no_false_suppression_for_distinct_topics(self) -> None:
        """Clearly distinct topics should not be suppressed by WP overlap."""
        result = _seed_result(
            "garden furniture",
            ["Best garden furniture guide", "Garden furniture tips"],
            [100, 120],
        )
        existing_posts = [
            {"slug": "indoor-plant-care", "title": "Indoor Plant Care Guide", "url": "", "date": ""},
            {"slug": "kitchen-renovation", "title": "Kitchen Renovation Ideas", "url": "", "date": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            winners = rank_pinclicks_keywords(
                scrape_results=[result],
                run_dir=Path(tmp_dir),
                top_n=1,
                reach_hat_map={"garden furniture": 0.8},
                existing_wp_posts=existing_posts,
            )
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].keyword, "garden furniture")
        self.assertEqual(winners[0].wp_overlap_detail, "")

    def test_wp_lookup_failure_degrades_safely(self) -> None:
        """When existing_wp_posts is empty, pipeline continues without WP overlap."""
        result = _seed_result(
            "patio furniture",
            ["Patio furniture guide", "Best patio tips"],
            [100, 120],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            winners = rank_pinclicks_keywords(
                scrape_results=[result],
                run_dir=run_dir,
                top_n=1,
                reach_hat_map={"patio furniture": 0.8},
                existing_wp_posts=[],
            )
            metadata = json.loads((run_dir / "pinclicks_ranking_metadata.json").read_text())

        self.assertEqual(len(winners), 1)
        self.assertEqual(metadata["wp_posts_checked"], 0)
        self.assertTrue(any("WordPress" in w for w in metadata["run_warnings"]))

    def test_topic_family_key_persisted(self) -> None:
        result = _seed_result(
            "crochet tank top free pattern",
            ["Crochet tank top guide"],
            [100],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            winners = rank_pinclicks_keywords(
                scrape_results=[result],
                run_dir=Path(tmp_dir),
                top_n=1,
                reach_hat_map={"crochet tank top free pattern": 0.8},
            )

        self.assertEqual(len(winners), 1)
        self.assertTrue(len(winners[0].topic_family_key) > 0)
        # "free" and "pattern" are modifiers, "crochet", "tank", "top" are content tokens
        self.assertIn("crochet", winners[0].topic_family_key)
        self.assertNotIn("free", winners[0].topic_family_key)
        self.assertNotIn("pattern", winners[0].topic_family_key)


class ParetoFrontierTests(unittest.TestCase):
    def test_pareto_frontier_basic(self) -> None:
        items = [
            {"x": 1.0, "y": 0.5},
            {"x": 1.0, "y": 1.0},
            {"x": 0.5, "y": 1.0},
            {"x": 0.8, "y": 0.8},
        ]
        frontier = pareto_frontier_2d(items, "x", "y")
        self.assertEqual(frontier, [1])

    def test_pareto_frontier_multiple_non_dominated(self) -> None:
        items = [
            {"x": 1.0, "y": 0.2},
            {"x": 0.2, "y": 1.0},
            {"x": 0.5, "y": 0.5},
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
