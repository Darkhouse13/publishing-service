import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from os import environ
from unittest.mock import patch

from automating_wf.content.generators import ArticleValidationError
from automating_wf.engine.pipeline import (
    RUN_OPTIONS_NAME,
    TRENDS_TOP_KEYWORDS_FILE,
    _build_summary,
    _build_csv_keywords,
    _is_valid_trend_keyword,
    _load_cached_top_keywords,
    _process_winner,
    _replay_pending_csv,
    build_public_permalink,
)
from automating_wf.models.pinterest import BrainOutput, SeedScrapeResult
from automating_wf.content.validator import ArticleValidationFinalError


class PinterestEngineTests(unittest.TestCase):
    @staticmethod
    def _sample_scrape_result() -> SeedScrapeResult:
        return SeedScrapeResult(
            blog_suffix="THE_SUNDAY_PATIO",
            seed_keyword="backyard fence ideas",
            source_url="https://app.pinclicks.com/pins",
            records=[],
            scraped_at="2026-02-16T20:00:00Z",
            source_file="",
        )

    @staticmethod
    def _sample_brain_output() -> BrainOutput:
        return BrainOutput(
            primary_keyword="backyard fence ideas",
            image_generation_prompt="Photorealistic backyard fence scene",
            pin_text_overlay="Backyard Fence Ideas",
            pin_title="Backyard Fence Ideas",
            pin_description="Pin description",
            cluster_label="Backyard Fencing",
            supporting_terms=["privacy fence", "backyard"],
            seasonal_angle="",
        )

    def test_is_valid_trend_keyword_rejects_numeric_only(self) -> None:
        self.assertFalse(_is_valid_trend_keyword("50"))
        self.assertFalse(_is_valid_trend_keyword("  123.4  "))
        self.assertTrue(_is_valid_trend_keyword("patio"))
        self.assertTrue(_is_valid_trend_keyword("patio furniture"))

    def test_build_public_permalink_defaults_to_site_slug_pattern(self) -> None:
        with patch.dict(
            environ,
            {"WP_URL_THE_SUNDAY_PATIO": "https://yoursundaypatio.com"},
            clear=False,
        ):
            permalink = build_public_permalink(
                blog_suffix="THE_SUNDAY_PATIO",
                post_slug="small-patio-ideas",
            )
        self.assertEqual(permalink, "https://yoursundaypatio.com/small-patio-ideas/")

    def test_build_public_permalink_uses_override_template(self) -> None:
        with patch.dict(
            environ,
            {
                "WP_URL_THE_SUNDAY_PATIO": "https://yoursundaypatio.com",
                "WP_PUBLIC_POST_URL_TEMPLATE_THE_SUNDAY_PATIO": "{site_url}/blog/{slug}/",
            },
            clear=False,
        ):
            permalink = build_public_permalink(
                blog_suffix="THE_SUNDAY_PATIO",
                post_slug="small-patio-ideas",
            )
        self.assertEqual(permalink, "https://yoursundaypatio.com/blog/small-patio-ideas/")

    def test_load_cached_top_keywords_filters_invalid_keywords(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            trends_dir = run_dir / "trends_analysis"
            trends_dir.mkdir(parents=True, exist_ok=True)
            payload = [
                {"keyword": "50", "rank": 1},
                {"keyword": " patio furniture ", "rank": 2},
                {"keyword": "", "rank": 3},
            ]
            (trends_dir / TRENDS_TOP_KEYWORDS_FILE).write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            cached = _load_cached_top_keywords(run_dir)

        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["keyword"], "patio furniture")

    def test_process_winner_no_fal_calls_when_article_generation_fails(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            scrape_result = self._sample_scrape_result()
            brain_output = self._sample_brain_output()

            with patch(
                "automating_wf.engine.pipeline.analyze_seed",
                return_value=brain_output,
            ), patch(
                "automating_wf.engine.pipeline.resolve_blog_profile",
                return_value="Patio blog profile",
            ), patch(
                "automating_wf.engine.pipeline.generate_article",
                side_effect=RuntimeError("article_validation: failed"),
            ), patch(
                "automating_wf.engine.pipeline.generate_pinterest_image"
            ) as mock_generate_pin_image, patch(
                "automating_wf.engine.pipeline.generate_image"
            ) as mock_generate_writer_image, patch(
                "automating_wf.engine.pipeline._append_manifest"
            ) as mock_append_manifest:
                _process_winner(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    scrape_result=scrape_result,
                    trend_rank=5,
                    pinclicks_rank=2,
                    repair_system_prompt="Fix only requested sections.",
                )

        self.assertFalse(mock_generate_pin_image.called)
        self.assertFalse(mock_generate_writer_image.called)
        statuses = [call.args[1].status for call in mock_append_manifest.call_args_list]
        self.assertIn("winner_processed", statuses)
        self.assertIn("article_failed", statuses)

    def test_process_winner_calls_generate_article_before_generate_pinterest_image(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            scrape_result = self._sample_scrape_result()
            brain_output = self._sample_brain_output()
            call_order: list[str] = []
            pin_call_kwargs: list[dict[str, object]] = []

            article_payload = {
                "title": "Backyard Fence Ideas",
                "article_markdown": "Paragraph one with backyard fence ideas.",
                "content_markdown": "Paragraph one with backyard fence ideas.",
                "hero_image_prompt": "Hero image prompt",
                "detail_image_prompt": "Detail image prompt",
                "seo_title": "Backyard Fence Ideas 2026",
                "meta_description": "Meta description",
                "focus_keyword": "backyard fence ideas",
            }

            def _generate_article(*_args, **_kwargs):
                call_order.append("generate_article")
                return article_payload

            def _generate_pin_image(*_args, **_kwargs):
                call_order.append("generate_pinterest_image")
                pin_call_kwargs.append(dict(_kwargs))
                return run_dir / "pin.jpg"

            def _generate_writer_image(*_args, **kwargs):
                call_order.append(f"generate_image_{kwargs.get('image_kind', 'unknown')}")
                return run_dir / f"{kwargs.get('image_kind', 'image')}.jpg"

            with patch(
                "automating_wf.engine.pipeline.analyze_seed",
                return_value=brain_output,
            ), patch(
                "automating_wf.engine.pipeline.resolve_blog_profile",
                return_value="Patio blog profile",
            ), patch(
                "automating_wf.engine.pipeline.generate_article",
                side_effect=_generate_article,
            ), patch(
                "automating_wf.engine.pipeline.validate_article_with_repair",
                return_value=type("ValidatorResultStub", (), {"article_payload": article_payload})(),
            ), patch(
                "automating_wf.engine.pipeline.generate_pinterest_image",
                side_effect=_generate_pin_image,
            ), patch(
                "automating_wf.engine.pipeline.generate_image",
                side_effect=_generate_writer_image,
            ), patch(
                "automating_wf.engine.pipeline._resolve_category_id_for_article",
                return_value=4,
            ), patch(
                "automating_wf.engine.pipeline.publish_post",
                return_value={
                    "post_id": 101,
                    "post_url": "https://thesundaypatio.com/?p=101",
                    "post_slug": "backyard-fence-ideas",
                    "status": "draft",
                    "hero_media_id": 1,
                    "detail_media_id": 2,
                    "category_ids": [4],
                    "publish_warnings": [],
                },
            ), patch(
                "automating_wf.engine.pipeline.upload_media",
                return_value={"id": 202, "source_url": "https://thesundaypatio.com/pin.jpg"},
            ), patch(
                "automating_wf.engine.pipeline.build_public_permalink",
                return_value="https://thesundaypatio.com/backyard-fence-ideas/",
            ), patch(
                "automating_wf.engine.pipeline.resolve_board_name",
                return_value="Patio Inspiration",
            ), patch(
                "automating_wf.engine.pipeline.append_csv_row",
                return_value={"publish_date": "2026-02-17 00:45"},
            ) as mock_append_csv_row, patch(
                "automating_wf.engine.pipeline._append_manifest"
            ):
                _process_winner(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    scrape_result=scrape_result,
                    trend_rank=5,
                    pinclicks_rank=2,
                    repair_system_prompt="Fix only requested sections.",
                    csv_first_publish_at="2026-03-16 09:30",
                    csv_cadence_minutes=180,
                )

        self.assertIn("generate_article", call_order)
        self.assertIn("generate_pinterest_image", call_order)
        self.assertLess(
            call_order.index("generate_article"),
            call_order.index("generate_pinterest_image"),
        )
        self.assertTrue(pin_call_kwargs)
        self.assertEqual(pin_call_kwargs[0].get("blog_name"), "The Sunday Patio")
        self.assertEqual(mock_append_csv_row.call_args.kwargs["initial_publish_date"], "2026-03-16 09:30")
        self.assertEqual(mock_append_csv_row.call_args.kwargs["cadence_minutes"], 180)

    def test_process_winner_marks_article_failed_when_validator_exhausts_retries(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            scrape_result = self._sample_scrape_result()
            brain_output = self._sample_brain_output()
            article_payload = {
                "title": "Backyard Fence Ideas",
                "article_markdown": "Paragraph one with backyard fence ideas.",
                "content_markdown": "Paragraph one with backyard fence ideas.",
                "hero_image_prompt": "Hero image prompt",
                "detail_image_prompt": "Detail image prompt",
                "seo_title": "Backyard Fence Ideas 2026",
                "meta_description": "Meta description",
                "focus_keyword": "backyard fence ideas",
            }

            with patch(
                "automating_wf.engine.pipeline.analyze_seed",
                return_value=brain_output,
            ), patch(
                "automating_wf.engine.pipeline.resolve_blog_profile",
                return_value="Patio blog profile",
            ), patch(
                "automating_wf.engine.pipeline.generate_article",
                return_value=article_payload,
            ), patch(
                "automating_wf.engine.pipeline.validate_article_with_repair",
                side_effect=ArticleValidationFinalError(
                    "validator failed",
                    errors=["missing h2 keyword"],
                    attempts_used=2,
                    attempts=[{"attempt": 1}, {"attempt": 2}],
                ),
            ), patch(
                "automating_wf.engine.pipeline.generate_pinterest_image"
            ) as mock_generate_pin_image, patch(
                "automating_wf.engine.pipeline.generate_image"
            ) as mock_generate_writer_image, patch(
                "automating_wf.engine.pipeline.publish_post"
            ) as mock_publish_post, patch(
                "automating_wf.engine.pipeline.upload_media"
            ) as mock_upload_media, patch(
                "automating_wf.engine.pipeline._append_manifest"
            ) as mock_append_manifest:
                result = _process_winner(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    scrape_result=scrape_result,
                    trend_rank=5,
                    pinclicks_rank=2,
                    repair_system_prompt="Fix only requested sections.",
                )

        self.assertEqual(result["failure_stage"], "article_failed")
        self.assertFalse(mock_generate_pin_image.called)
        self.assertFalse(mock_generate_writer_image.called)
        self.assertFalse(mock_publish_post.called)
        self.assertFalse(mock_upload_media.called)
        statuses = [call.args[1].status for call in mock_append_manifest.call_args_list]
        self.assertIn("article_failed", statuses)
        self.assertNotIn("wp_failed", statuses)

    def test_process_winner_uses_best_effort_payload_when_generation_validation_exhausts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            scrape_result = self._sample_scrape_result()
            brain_output = self._sample_brain_output()
            fallback_payload = {
                "title": "Backyard Fence Ideas",
                "article_markdown": "Paragraph one with backyard fence ideas.",
                "content_markdown": "Paragraph one with backyard fence ideas.",
                "hero_image_prompt": "Hero image prompt",
                "detail_image_prompt": "Detail image prompt",
                "seo_title": "Backyard Fence Ideas 2026",
                "meta_description": "Meta description",
                "focus_keyword": "backyard fence ideas",
            }

            with patch(
                "automating_wf.engine.pipeline.analyze_seed",
                return_value=brain_output,
            ), patch(
                "automating_wf.engine.pipeline.resolve_blog_profile",
                return_value="Patio blog profile",
            ), patch(
                "automating_wf.engine.pipeline.generate_article",
                side_effect=ArticleValidationError(
                    "article_validation: failed",
                    errors=["missing h2 keyword"],
                    payload=fallback_payload,
                ),
            ), patch(
                "automating_wf.engine.pipeline.validate_article_with_repair",
                return_value=type("ValidatorResultStub", (), {"article_payload": fallback_payload})(),
            ) as mock_validator, patch(
                "automating_wf.engine.pipeline.generate_pinterest_image",
                return_value=run_dir / "pin.jpg",
            ) as mock_generate_pin_image, patch(
                "automating_wf.engine.pipeline.generate_image",
                side_effect=[run_dir / "hero.jpg", run_dir / "detail.jpg"],
            ), patch(
                "automating_wf.engine.pipeline._resolve_category_id_for_article",
                return_value=4,
            ), patch(
                "automating_wf.engine.pipeline.publish_post",
                return_value={
                    "post_id": 101,
                    "post_url": "https://thesundaypatio.com/?p=101",
                    "post_slug": "backyard-fence-ideas",
                    "status": "draft",
                    "hero_media_id": 1,
                    "detail_media_id": 2,
                    "category_ids": [4],
                    "publish_warnings": [],
                },
            ), patch(
                "automating_wf.engine.pipeline.upload_media",
                return_value={"id": 202, "source_url": "https://thesundaypatio.com/pin.jpg"},
            ), patch(
                "automating_wf.engine.pipeline.build_public_permalink",
                return_value="https://thesundaypatio.com/backyard-fence-ideas/",
            ), patch(
                "automating_wf.engine.pipeline.resolve_board_name",
                return_value="Patio Inspiration",
            ), patch(
                "automating_wf.engine.pipeline.append_csv_row",
                return_value={"publish_date": "2026-02-17 00:45"},
            ), patch(
                "automating_wf.engine.pipeline._append_manifest"
            ) as mock_append_manifest:
                result = _process_winner(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    scrape_result=scrape_result,
                    trend_rank=5,
                    pinclicks_rank=2,
                    repair_system_prompt="Fix only requested sections.",
                )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(mock_generate_pin_image.called)
        self.assertEqual(mock_validator.call_args.kwargs["article_payload"], fallback_payload)
        statuses = [call.args[1].status for call in mock_append_manifest.call_args_list]
        self.assertIn("wp_published", statuses)

    def test_build_csv_keywords_dedupes_and_normalizes(self) -> None:
        value = _build_csv_keywords(
            primary_keyword=" backyard patio ideas ",
            supporting_terms=[
                "Backyard Patio Ideas",
                "  privacy,screen outdoor ",
                "",
                "outdoor living",
            ],
        )
        self.assertEqual(value, "backyard patio ideas, privacy screen outdoor, outdoor living")

    def test_replay_pending_csv_supports_legacy_pending_row_keys(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            csv_path = run_dir / "legacy.csv"
            latest_by_seed = {
                "seed one": {
                    "status": "csv_failed",
                    "primary_keyword": "primary one",
                    "idempotency_key": "id-1",
                    "details": {
                        "pending_csv_row": {
                            "Title": "Legacy Title",
                            "Description": "Legacy Desc",
                            "Link": "https://example.com/legacy/",
                            "Image URL": "https://example.com/uploads/legacy.jpg",
                            "Pinterest Board": "Legacy Board",
                            "Publish Date": "2026-02-17 00:45",
                        },
                        "csv_path": str(csv_path),
                        "csv_first_publish_at": "2026-02-18 09:30",
                        "csv_cadence_minutes": 180,
                    },
                }
            }

            with patch(
                "automating_wf.engine.pipeline.append_csv_row",
                return_value={"status": "appended", "publish_date": "2026-02-17T00:45:00", "row": {}},
            ) as mock_append_csv_row, patch("automating_wf.engine.pipeline._append_manifest"):
                _replay_pending_csv(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    latest_by_seed=latest_by_seed,
                )

        row_arg = mock_append_csv_row.call_args.kwargs["row"]
        self.assertEqual(row_arg.image_url, "https://example.com/uploads/legacy.jpg")
        self.assertEqual(row_arg.pinterest_board, "Legacy Board")
        self.assertEqual(row_arg.publish_date, "2026-02-17 00:45")
        self.assertEqual(row_arg.thumbnail, "")
        self.assertEqual(row_arg.keywords, "")
        self.assertEqual(mock_append_csv_row.call_args.kwargs["initial_publish_date"], "2026-02-18 09:30")
        self.assertEqual(mock_append_csv_row.call_args.kwargs["cadence_minutes"], 180)

    def test_replay_pending_csv_supports_pinterest_pending_row_keys(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            csv_path = run_dir / "new.csv"
            latest_by_seed = {
                "seed two": {
                    "status": "csv_failed",
                    "primary_keyword": "primary two",
                    "idempotency_key": "id-2",
                    "details": {
                        "pending_csv_row": {
                            "Title": "New Title",
                            "Description": "New Desc",
                            "Link": "https://example.com/new/",
                            "Media URL": "https://example.com/uploads/new.jpg",
                            "Pinterest board": "New Board",
                            "Publish date": "2026-02-17T08:00:00",
                            "Thumbnail": "",
                            "Keywords": "keyword one, keyword two",
                        },
                        "csv_path": str(csv_path),
                    },
                }
            }

            with patch(
                "automating_wf.engine.pipeline.append_csv_row",
                return_value={"status": "appended", "publish_date": "2026-02-17T08:00:00", "row": {}},
            ) as mock_append_csv_row, patch("automating_wf.engine.pipeline._append_manifest"):
                _replay_pending_csv(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_SUNDAY_PATIO",
                    latest_by_seed=latest_by_seed,
                )

        row_arg = mock_append_csv_row.call_args.kwargs["row"]
        self.assertEqual(row_arg.image_url, "https://example.com/uploads/new.jpg")
        self.assertEqual(row_arg.pinterest_board, "New Board")
        self.assertEqual(row_arg.publish_date, "2026-02-17T08:00:00")
        self.assertEqual(row_arg.keywords, "keyword one, keyword two")
        self.assertIsNone(mock_append_csv_row.call_args.kwargs["initial_publish_date"])

    def test_replay_pending_csv_resolves_missing_board_from_mapping(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            csv_path = run_dir / "new.csv"
            latest_by_seed = {
                "seed three": {
                    "status": "csv_failed",
                    "primary_keyword": "garage workshop organization",
                    "idempotency_key": "id-3",
                    "details": {
                        "pending_csv_row": {
                            "Title": "Missing Board",
                            "Description": "Desc",
                            "Link": "https://example.com/missing-board/",
                            "Media URL": "https://example.com/uploads/missing-board.jpg",
                            "Pinterest board": "",
                            "Publish date": "",
                            "Keywords": "garage workshop organization, storage",
                        },
                        "csv_path": str(csv_path),
                    },
                }
            }

            with patch(
                "automating_wf.engine.pipeline.resolve_board_name",
                return_value="Weekend Lifestyle Ideas",
            ), patch(
                "automating_wf.engine.pipeline.append_csv_row",
                return_value={"status": "appended", "publish_date": "2026-02-17T08:00:00", "row": {}},
            ) as mock_append_csv_row, patch("automating_wf.engine.pipeline._append_manifest"):
                _replay_pending_csv(
                    run_id="20260216_201847",
                    run_dir=run_dir,
                    blog_suffix="THE_WEEKEND_FOLIO",
                    latest_by_seed=latest_by_seed,
                )

        row_arg = mock_append_csv_row.call_args.kwargs["row"]
        self.assertEqual(row_arg.pinterest_board, "Weekend Lifestyle Ideas")

    def test_build_summary_includes_csv_schedule_from_run_options(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / RUN_OPTIONS_NAME).write_text(
                json.dumps(
                    {
                        "blog_suffix": "THE_SUNDAY_PATIO",
                        "csv_first_publish_at": "2099-01-01 09:30",
                        "csv_cadence_minutes": 180,
                    }
                ),
                encoding="utf-8",
            )

            summary = _build_summary(run_dir, blog_suffix="THE_SUNDAY_PATIO")

        self.assertEqual(summary["csv_schedule"]["first_publish_at"], "2099-01-01 09:30")
        self.assertEqual(summary["csv_schedule"]["cadence_minutes"], 180)
        self.assertTrue(summary["csv_schedule"]["preview_slots"])


if __name__ == "__main__":
    unittest.main()
