import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from generators import ArticleValidationError
from single_article_flow import (
    SingleArticleDraftError,
    generate_single_article_draft,
)
from validator import ArticleValidationFinalError, ArticleValidatorError


def _payload() -> dict[str, str]:
    return {
        "title": "Smart Patio Workflow Guide",
        "article_markdown": "smart patio workflow intro.\n\n## Why smart patio workflow matters\n\nBody paragraph.",
        "content_markdown": "smart patio workflow intro.\n\n## Why smart patio workflow matters\n\nBody paragraph.",
        "hero_image_prompt": "Hero prompt",
        "detail_image_prompt": "Detail prompt",
        "seo_title": "Smart Patio Workflow 2026",
        "meta_description": "A practical guide to smart patio workflow.",
        "focus_keyword": "smart patio workflow",
    }


def _validator_result(
    payload: dict[str, str],
    *,
    repaired: bool,
    attempts_used: int,
):
    return type(
        "ValidatorResultStub",
        (),
        {
            "article_payload": payload,
            "repaired": repaired,
            "attempts_used": attempts_used,
        },
    )()


class SingleArticleFlowTests(unittest.TestCase):
    def test_generate_single_article_draft_success(self) -> None:
        article_payload = _payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                return_value=article_payload,
            ), patch(
                "single_article_flow.validate_article_with_repair",
                return_value=_validator_result(article_payload, repaired=False, attempts_used=0),
            ) as mock_validate, patch(
                "single_article_flow.generate_image",
                side_effect=[tmp_path / "hero.png", tmp_path / "detail.png"],
            ) as mock_generate_image:
                result = generate_single_article_draft(
                    topic="Smart Patio Workflow",
                    vibe="Practical",
                    blog_profile="Outdoor blog",
                    out_dir=tmp_path,
                    repair_system_prompt="Fix only requested sections.",
                    validator_artifact_root=tmp_path / "validator_root",
                )
                validator_artifact_dir = mock_validate.call_args.kwargs["artifact_dir"]
                self.assertTrue(validator_artifact_dir.exists())

        self.assertEqual(result.article_payload["title"], article_payload["title"])
        self.assertEqual(result.hero_image_path.name, "hero.png")
        self.assertEqual(result.detail_image_path.name, "detail.png")
        self.assertFalse(result.validator_repaired)
        self.assertEqual(result.validator_attempts_used, 0)
        self.assertEqual(mock_generate_image.call_count, 2)
        self.assertEqual(validator_artifact_dir.name, "smart_patio_workflow")

    def test_generate_single_article_draft_uses_best_effort_payload_fallback(self) -> None:
        article_payload = _payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                side_effect=ArticleValidationError(
                    "article_validation failed",
                    errors=["keyword count low"],
                    payload=article_payload,
                ),
            ), patch(
                "single_article_flow.validate_article_with_repair",
                return_value=_validator_result(article_payload, repaired=True, attempts_used=1),
            ) as mock_validate, patch(
                "single_article_flow.generate_image",
                side_effect=[tmp_path / "hero.png", tmp_path / "detail.png"],
            ):
                result = generate_single_article_draft(
                    topic="Smart Patio Workflow",
                    vibe="Practical",
                    blog_profile="Outdoor blog",
                    out_dir=tmp_path,
                    repair_system_prompt="Fix only requested sections.",
                )

        self.assertTrue(result.validator_repaired)
        self.assertEqual(result.validator_attempts_used, 1)
        self.assertEqual(mock_validate.call_args.kwargs["article_payload"], article_payload)

    def test_generate_single_article_draft_raises_on_generation_failure_without_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                side_effect=ArticleValidationError(
                    "article_validation failed",
                    errors=["missing h2 keyword"],
                    payload=None,
                ),
            ), patch("single_article_flow.validate_article_with_repair") as mock_validate, patch(
                "single_article_flow.generate_image"
            ) as mock_generate_image:
                with self.assertRaises(SingleArticleDraftError) as exc:
                    generate_single_article_draft(
                        topic="Smart Patio Workflow",
                        vibe="Practical",
                        blog_profile="Outdoor blog",
                        out_dir=tmp_path,
                        repair_system_prompt="Fix only requested sections.",
                    )

        self.assertEqual(exc.exception.failure_stage, "article_failed")
        self.assertIn("missing h2 keyword", exc.exception.generation_errors)
        self.assertFalse(mock_validate.called)
        self.assertFalse(mock_generate_image.called)

    def test_generate_single_article_draft_raises_on_validator_final_failure(self) -> None:
        article_payload = _payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                return_value=article_payload,
            ), patch(
                "single_article_flow.validate_article_with_repair",
                side_effect=ArticleValidationFinalError(
                    "validator failed",
                    errors=["density invalid"],
                    attempts_used=2,
                    attempts=[{"attempt": 1}, {"attempt": 2}],
                    last_payload=article_payload,
                ),
            ), patch("single_article_flow.generate_image") as mock_generate_image:
                with self.assertRaises(SingleArticleDraftError) as exc:
                    generate_single_article_draft(
                        topic="Smart Patio Workflow",
                        vibe="Practical",
                        blog_profile="Outdoor blog",
                        out_dir=tmp_path,
                        repair_system_prompt="Fix only requested sections.",
                    )

        self.assertEqual(exc.exception.failure_stage, "article_failed")
        self.assertIn("density invalid", exc.exception.validator_errors)
        self.assertEqual(len(exc.exception.validator_attempts), 2)
        self.assertEqual(exc.exception.payload, article_payload)
        self.assertFalse(mock_generate_image.called)

    def test_generate_single_article_draft_raises_on_validator_setup_failure(self) -> None:
        article_payload = _payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                return_value=article_payload,
            ), patch(
                "single_article_flow.validate_article_with_repair",
                side_effect=ArticleValidatorError("Missing prompt"),
            ), patch("single_article_flow.generate_image") as mock_generate_image:
                with self.assertRaises(SingleArticleDraftError) as exc:
                    generate_single_article_draft(
                        topic="Smart Patio Workflow",
                        vibe="Practical",
                        blog_profile="Outdoor blog",
                        out_dir=tmp_path,
                        repair_system_prompt="Fix only requested sections.",
                    )

        self.assertEqual(exc.exception.failure_stage, "article_failed")
        self.assertIn("Missing prompt", exc.exception.validator_errors[0])
        self.assertFalse(mock_generate_image.called)

    def test_generate_single_article_draft_loads_prompt_when_missing(self) -> None:
        article_payload = _payload()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch(
                "single_article_flow.generate_article",
                return_value=article_payload,
            ), patch(
                "single_article_flow.load_repair_system_prompt",
                return_value="Loaded prompt",
            ) as mock_load_prompt, patch(
                "single_article_flow.validate_article_with_repair",
                return_value=_validator_result(article_payload, repaired=False, attempts_used=0),
            ) as mock_validate, patch(
                "single_article_flow.generate_image",
                side_effect=[tmp_path / "hero.png", tmp_path / "detail.png"],
            ):
                generate_single_article_draft(
                    topic="Smart Patio Workflow",
                    vibe="Practical",
                    blog_profile="Outdoor blog",
                    out_dir=tmp_path,
                )

        self.assertEqual(mock_load_prompt.call_count, 1)
        self.assertEqual(
            mock_validate.call_args.kwargs["repair_system_prompt"],
            "Loaded prompt",
        )


if __name__ == "__main__":
    unittest.main()
