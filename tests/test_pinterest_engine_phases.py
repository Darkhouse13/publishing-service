import unittest
from pathlib import Path
import subprocess
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automating_wf.engine.config import (
    EngineRunOptions,
    PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
    TrendCandidates,
)
from automating_wf.engine.pipeline import (
    _run_scraper_subprocess,
    collect_pinclicks_data_sync,
    collect_trends_candidates_sync,
    replay_pending_csv_sync,
    run_engine,
    run_winner_generation_sync,
)
from automating_wf.models.pinterest import PinClicksKeywordScore, SeedScrapeResult
from automating_wf.scrapers.pinclicks import ScraperError


def _opts() -> EngineRunOptions:
    return EngineRunOptions(
        blog_suffix="THE_SUNDAY_PATIO",
        seed_keywords=["patio furniture", "small patio ideas"],
        trends_region="GLOBAL",
        trends_range="monthly",
        trends_top_n=10,
        selected_trend_keywords=[],
        pinclicks_max_records=31,
        winners_count=2,
        publish_status="pending",
        headed=False,
        resume_run_id=None,
    )


class PinterestEnginePhaseTests(unittest.TestCase):
    def test_collect_trends_candidates_returns_trend_candidates(self) -> None:
        opts = _opts()
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline._resolve_run_dir",
                return_value=("20260217_120000", run_dir),
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline.validate_board_mapping_for_blog",
            ), patch(
                "automating_wf.engine.pipeline._replay_pending_csv",
            ), patch(
                "automating_wf.engine.pipeline._load_cached_top_keywords",
                return_value=[
                    {
                        "keyword": "patio furniture",
                        "rank": 1,
                        "hybrid_score": 0.91,
                        "growth_norm": 0.6,
                        "trend_index_norm": 0.8,
                        "source_count": 5,
                    }
                ],
            ):
                result = collect_trends_candidates_sync(opts)

        self.assertIsInstance(result, TrendCandidates)
        self.assertEqual(result.run_id, "20260217_120000")
        self.assertEqual(result.ranked_keywords[0]["keyword"], "patio furniture")
        self.assertAlmostEqual(result.ranked_keywords[0]["score"], 0.91)

    def test_collect_pinclicks_data_uses_selected_keywords_and_max_records(self) -> None:
        opts = _opts()
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._append_manifest",
            ), patch(
                "automating_wf.engine.pipeline._load_cached_top_keywords",
                return_value=[{"keyword": "patio furniture", "rank": 1}],
            ), patch(
                "automating_wf.engine.pipeline.scrape_seed",
                return_value=SeedScrapeResult(
                    blog_suffix="THE_SUNDAY_PATIO",
                    seed_keyword="patio furniture",
                    source_url="https://app.pinclicks.com/pins",
                    source_file="seed_scrape_result.json",
                    records=[],
                    scraped_at="2026-02-17T10:00:00Z",
                ),
            ) as mock_scrape_seed, patch(
                "automating_wf.engine.pipeline.rank_pinclicks_keywords",
                return_value=[
                    PinClicksKeywordScore(
                        keyword="patio furniture",
                        total_score=0.88,
                        frequency_score=1.2,
                        engagement_score=10.1,
                        intent_score=0.5,
                        record_count=12,
                        trend_rank=1,
                        pinclicks_rank=1,
                    )
                ],
            ):
                results = collect_pinclicks_data_sync(
                    opts=opts,
                    selected_keywords=["patio furniture"],
                    run_id="20260217_120000",
                )

        self.assertEqual(len(results.winners), 1)
        self.assertEqual(results.winners[0]["keyword"], "patio furniture")
        self.assertEqual(
            mock_scrape_seed.call_args.kwargs.get("max_records"),
            opts.pinclicks_max_records,
        )

    def test_collect_pinclicks_data_returns_structured_skipped_payload(self) -> None:
        opts = _opts()
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._append_manifest",
            ), patch(
                "automating_wf.engine.pipeline._load_cached_top_keywords",
                return_value=[{"keyword": "patio furniture", "rank": 1}],
            ), patch(
                "automating_wf.engine.pipeline.scrape_seed",
                side_effect=ScraperError(
                    "Could not enter keyword in PinClicks search box.",
                    reason=PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED,
                    attempts=3,
                    used_headed_fallback=True,
                ),
            ), patch(
                "automating_wf.engine.pipeline.rank_pinclicks_keywords",
                return_value=[],
            ):
                results = collect_pinclicks_data_sync(
                    opts=opts,
                    selected_keywords=["patio furniture"],
                    run_id="20260217_120000",
                )

        self.assertEqual(len(results.winners), 0)
        self.assertEqual(len(results.skipped), 1)
        skipped = results.skipped[0]
        self.assertEqual(skipped["keyword"], "patio furniture")
        self.assertEqual(skipped["reason"], PINCLICKS_SKIP_REASON_SEARCH_INPUT_REJECTED)
        self.assertEqual(skipped["attempts"], 3)
        self.assertTrue(skipped["used_headed_fallback"])
        self.assertEqual(skipped["source_stage"], "pinclicks")

    def test_collect_trends_candidates_streamlit_uses_subprocess(self) -> None:
        opts = _opts()
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline._resolve_run_dir",
                return_value=("20260217_120000", run_dir),
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline.validate_board_mapping_for_blog",
            ), patch(
                "automating_wf.engine.pipeline._replay_pending_csv",
            ), patch(
                "automating_wf.engine.pipeline._load_cached_top_keywords",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._running_in_streamlit",
                return_value=True,
            ), patch(
                "automating_wf.engine.pipeline._run_scraper_subprocess",
                return_value={"patio furniture": ["tmp/test.csv"]},
            ) as mock_subprocess, patch(
                "automating_wf.engine.pipeline.scrape_trends_exports",
            ) as mock_direct_scrape, patch(
                "automating_wf.engine.pipeline.analyze_trends_exports",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._append_manifest",
            ):
                collect_trends_candidates_sync(opts)

        self.assertFalse(mock_direct_scrape.called)
        self.assertTrue(mock_subprocess.called)
        self.assertEqual(mock_subprocess.call_args.args[0]["action"], "scrape_trends")

    def test_collect_pinclicks_data_streamlit_uses_subprocess(self) -> None:
        opts = _opts()
        sample = SeedScrapeResult(
            blog_suffix="THE_SUNDAY_PATIO",
            seed_keyword="patio furniture",
            source_url="https://app.pinclicks.com/pins",
            source_file="seed_scrape_result.json",
            records=[],
            scraped_at="2026-02-17T10:00:00Z",
        )
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._append_manifest",
            ), patch(
                "automating_wf.engine.pipeline._load_cached_top_keywords",
                return_value=[{"keyword": "patio furniture", "rank": 1}],
            ), patch(
                "automating_wf.engine.pipeline._running_in_streamlit",
                return_value=True,
            ), patch(
                "automating_wf.engine.pipeline._run_scraper_subprocess",
                return_value=sample.to_dict(),
            ) as mock_subprocess, patch(
                "automating_wf.engine.pipeline.scrape_seed",
            ) as mock_direct_scrape, patch(
                "automating_wf.engine.pipeline.rank_pinclicks_keywords",
                return_value=[],
            ):
                collect_pinclicks_data_sync(
                    opts=opts,
                    selected_keywords=["patio furniture"],
                    run_id="20260217_120000",
                )

        self.assertFalse(mock_direct_scrape.called)
        self.assertTrue(mock_subprocess.called)
        self.assertEqual(mock_subprocess.call_args.args[0]["action"], "scrape_pinclicks")

    def test_run_winner_generation_returns_generation_results_and_progress(self) -> None:
        opts = _opts()
        winners = [
            {"keyword": "alpha", "trend_rank": 1, "pinclicks_rank": 1},
            {"keyword": "beta", "trend_rank": 2, "pinclicks_rank": 2},
        ]
        progress_events: list[tuple[int, int, dict]] = []

        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "pinclicks_exports" / "alpha").mkdir(parents=True, exist_ok=True)
            (run_dir / "pinclicks_exports" / "beta").mkdir(parents=True, exist_ok=True)
            (run_dir / "pinclicks_exports" / "alpha" / "seed_scrape_result.json").write_text("{}")
            (run_dir / "pinclicks_exports" / "beta" / "seed_scrape_result.json").write_text("{}")

            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline._resolve_blog_name_from_suffix",
                return_value="The Sunday Patio",
            ), patch(
                "automating_wf.engine.pipeline.validate_board_mapping_for_blog",
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._latest_status_by_seed",
                return_value={},
            ), patch(
                "automating_wf.engine.pipeline._load_seed_scrape_result",
                return_value=SeedScrapeResult(
                    blog_suffix="THE_SUNDAY_PATIO",
                    seed_keyword="alpha",
                    source_url="https://app.pinclicks.com/pins",
                    source_file="seed_scrape_result.json",
                    records=[],
                    scraped_at="2026-02-17T10:00:00Z",
                ),
            ), patch(
                "automating_wf.engine.pipeline._process_winner",
                side_effect=[
                    {"keyword": "alpha", "status": "completed", "title": "Alpha", "post_url": "https://a"},
                    {"keyword": "beta", "status": "failed", "error": "boom", "failure_stage": "article_failed"},
                ],
            ) as mock_process_winner:
                results = run_winner_generation_sync(
                    opts=opts,
                    winners=winners,
                    run_id="20260217_120000",
                    on_progress=lambda current, total, item: progress_events.append((current, total, item)),
                )

        self.assertEqual(len(results.completed), 1)
        self.assertEqual(len(results.partial), 0)
        self.assertEqual(len(results.failed_pre_publish), 1)
        self.assertEqual(len(results.failed), 1)
        self.assertTrue(results.csv_path.endswith("pinterest_bulk_upload_the_sunday_patio.csv"))
        self.assertEqual(len(progress_events), 2)
        self.assertTrue(all(call.kwargs.get("publish_status") == opts.publish_status for call in mock_process_winner.call_args_list))

    def test_run_winner_generation_classifies_csv_failed_as_partial(self) -> None:
        opts = _opts()
        winners = [{"keyword": "alpha", "trend_rank": 1, "pinclicks_rank": 1}]

        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "pinclicks_exports" / "alpha").mkdir(parents=True, exist_ok=True)
            (run_dir / "pinclicks_exports" / "alpha" / "seed_scrape_result.json").write_text("{}")

            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline._resolve_blog_name_from_suffix",
                return_value="The Sunday Patio",
            ), patch(
                "automating_wf.engine.pipeline.validate_board_mapping_for_blog",
            ), patch(
                "automating_wf.engine.pipeline._load_manifest_entries",
                return_value=[],
            ), patch(
                "automating_wf.engine.pipeline._latest_status_by_seed",
                return_value={},
            ), patch(
                "automating_wf.engine.pipeline._load_seed_scrape_result",
                return_value=SeedScrapeResult(
                    blog_suffix="THE_SUNDAY_PATIO",
                    seed_keyword="alpha",
                    source_url="https://app.pinclicks.com/pins",
                    source_file="seed_scrape_result.json",
                    records=[],
                    scraped_at="2026-02-17T10:00:00Z",
                ),
            ), patch(
                "automating_wf.engine.pipeline._process_winner",
                return_value={
                    "keyword": "alpha",
                    "status": "failed",
                    "failure_stage": "csv_failed",
                    "error": "board missing",
                    "post_url": "https://example.com/alpha",
                },
            ):
                results = run_winner_generation_sync(
                    opts=opts,
                    winners=winners,
                    run_id="20260217_120000",
                )

        self.assertEqual(len(results.completed), 0)
        self.assertEqual(len(results.partial), 1)
        self.assertEqual(len(results.failed_pre_publish), 0)
        self.assertEqual(len(results.failed), 1)
        self.assertEqual(results.partial[0]["keyword"], "alpha")
        self.assertEqual(results.partial[0]["status"], "partial")

    def test_run_engine_preserves_cli_shape_and_calls_phases_in_order(self) -> None:
        opts = _opts()
        opts.seed_keywords = ["one", "two", "three"]
        call_order: list[str] = []

        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with patch(
                "automating_wf.engine.pipeline.EngineRunOptions.from_env",
                return_value=opts,
            ), patch(
                "automating_wf.engine.pipeline.collect_trends_candidates_sync",
                side_effect=lambda _opts_arg: (
                    call_order.append("phase1")
                    or TrendCandidates(
                        run_id="20260217_120000",
                        run_dir=str(run_dir),
                        ranked_keywords=[{"keyword": "kw1"}],
                        raw_trends_count=3,
                    )
                ),
            ), patch(
                "automating_wf.engine.pipeline.collect_pinclicks_data_sync",
                side_effect=lambda **_kwargs: (
                    call_order.append("phase2")
                    or type(
                        "PinClicksResultStub",
                        (),
                        {"winners": [{"keyword": "kw1", "trend_rank": 1, "pinclicks_rank": 1}], "run_id": "20260217_120000"},
                    )()
                ),
            ), patch(
                "automating_wf.engine.pipeline.run_winner_generation_sync",
                side_effect=lambda **_kwargs: call_order.append("phase3"),
            ), patch(
                "automating_wf.engine.pipeline._build_summary",
                return_value={"status_counts": {"csv_appended": 1}},
            ):
                summary = run_engine(
                    blog_suffix="THE_SUNDAY_PATIO",
                    resume="resume_run",
                    max_seeds=2,
                    headed=True,
                )

        self.assertEqual(call_order, ["phase1", "phase2", "phase3"])
        self.assertEqual(opts.seed_keywords, ["one", "two"])
        self.assertTrue(opts.headed)
        self.assertEqual(opts.resume_run_id, "resume_run")
        self.assertEqual(summary["status_counts"]["csv_appended"], 1)

    def test_replay_pending_csv_sync_reports_recovered_and_failed(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            run_id = "20260217_120000"
            manifest_path = run_dir / "manifest.jsonl"
            seed_one = {
                "run_id": run_id,
                "blog_suffix": "THE_WEEKEND_FOLIO",
                "seed_keyword": "seed one",
                "status": "csv_failed",
                "event_time": "2026-02-17T12:00:00Z",
                "details": {
                    "pending_csv_row": {
                        "Title": "One",
                        "Description": "Desc",
                        "Link": "https://example.com/one/",
                        "Media URL": "https://example.com/one.jpg",
                        "Pinterest board": "Weekend Lifestyle Ideas",
                        "Publish date": "",
                        "Thumbnail": "",
                        "Keywords": "",
                    },
                    "csv_path": "pinterest_bulk_upload_the_weekend_folio.csv",
                },
            }
            seed_two = {
                "run_id": run_id,
                "blog_suffix": "THE_WEEKEND_FOLIO",
                "seed_keyword": "seed two",
                "status": "csv_failed",
                "event_time": "2026-02-17T12:00:01Z",
                "details": {
                    "pending_csv_row": {
                        "Title": "Two",
                        "Description": "Desc",
                        "Link": "https://example.com/two/",
                        "Media URL": "https://example.com/two.jpg",
                        "Pinterest board": "Weekend Lifestyle Ideas",
                        "Publish date": "",
                        "Thumbnail": "",
                        "Keywords": "",
                    },
                    "csv_path": "pinterest_bulk_upload_the_weekend_folio.csv",
                },
            }
            manifest_path.write_text(
                "\n".join(json.dumps(item) for item in (seed_one, seed_two)) + "\n",
                encoding="utf-8",
            )

            with patch(
                "automating_wf.engine.pipeline._resolve_phase_run_dir",
                return_value=run_dir,
            ), patch(
                "automating_wf.engine.pipeline.validate_board_mapping_for_blog",
            ), patch(
                "automating_wf.engine.pipeline.append_csv_row",
                side_effect=[
                    {"status": "appended", "publish_date": "2026-02-17T13:00:00", "row": {}},
                    RuntimeError("csv write failed"),
                ],
            ):
                result = replay_pending_csv_sync(
                    run_id=run_id,
                    blog_suffix="THE_WEEKEND_FOLIO",
                )

        self.assertEqual(int(result["pending_before"]), 2)
        self.assertEqual(int(result["recovered_count"]), 1)
        self.assertEqual(int(result["failed_count"]), 1)
        self.assertIn("seed one", result["recovered_keywords"])
        self.assertIn("seed two", result["failed_keywords"])


class ScraperSubprocessHelperTests(unittest.TestCase):
    def test_run_scraper_subprocess_raises_on_nonzero_exit(self) -> None:
        with patch(
            "automating_wf.engine.pipeline.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "scraper_subprocess"],
                returncode=1,
                stdout="",
                stderr="boom",
            ),
        ):
            with self.assertRaises(RuntimeError):
                _run_scraper_subprocess({"action": "scrape_trends"})

    def test_run_scraper_subprocess_raises_on_invalid_json(self) -> None:
        with patch(
            "automating_wf.engine.pipeline.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "scraper_subprocess"],
                returncode=0,
                stdout="not-json",
                stderr="",
            ),
        ):
            with self.assertRaises(RuntimeError):
                _run_scraper_subprocess({"action": "scrape_trends"})

    def test_run_scraper_subprocess_raises_on_scraper_error_payload(self) -> None:
        with patch(
            "automating_wf.engine.pipeline.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "scraper_subprocess"],
                returncode=0,
                stdout='{"ok": false, "error": "bad"}',
                stderr="",
            ),
        ):
            with self.assertRaises(RuntimeError):
                _run_scraper_subprocess({"action": "scrape_trends"})


if __name__ == "__main__":
    unittest.main()
