import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from validator import (
    ArticleValidationFinalError,
    ArticleValidatorError,
    load_repair_system_prompt,
    validate_article_with_repair,
)


def _response_with_content(content: str) -> Mock:
    response = Mock()
    choice = Mock()
    choice.message.content = content
    response.choices = [choice]
    return response


def _valid_markdown(focus_keyword: str = "smart patio workflow") -> str:
    return "\n\n".join(
        [
            f"{focus_keyword} helps structure seasonal upgrades and keeps progress measurable.",
            f"## Why {focus_keyword} matters",
            (
                f"A documented {focus_keyword} process prevents rework and keeps each task "
                "aligned with budget constraints."
            ),
            f"## {focus_keyword} checklist",
            (
                f"Use this {focus_keyword} checklist each weekend to maintain momentum and "
                "finish updates consistently."
            ),
        ]
    )


def _missing_h2_keyword_markdown(focus_keyword: str = "smart patio workflow") -> str:
    return "\n\n".join(
        [
            f"{focus_keyword} helps structure seasonal upgrades and keeps progress measurable.",
            "## Why this matters",
            (
                f"A documented {focus_keyword} process prevents rework and keeps each task "
                f"aligned with budget constraints while the {focus_keyword} cadence stays stable."
            ),
            "## Weekly checklist",
            f"Follow this {focus_keyword} checklist so outcomes stay practical and repeatable.",
        ]
    )


def _low_density_markdown(focus_keyword: str = "smart patio workflow") -> str:
    return "\n\n".join(
        [
            f"{focus_keyword} keeps planning focused and actionable.",
            f"## Why {focus_keyword} matters",
            "A lightweight process prevents costly missteps and protects execution quality.",
            "This paragraph needs richer keyword coverage to satisfy validator density rules.",
        ]
    )


def _payload(markdown: str, focus_keyword: str = "smart patio workflow") -> dict[str, str]:
    return {
        "title": "Smart Patio Workflow Guide",
        "article_markdown": markdown,
        "content_markdown": markdown,
        "hero_image_prompt": "Hero prompt",
        "detail_image_prompt": "Detail prompt",
        "seo_title": "Smart Patio Workflow 2026",
        "meta_description": "A practical guide for smart patio workflow execution.",
        "focus_keyword": focus_keyword,
    }


class ArticleValidatorTests(unittest.TestCase):
    def test_pass_through_when_rules_already_pass(self) -> None:
        article_payload = _payload(_valid_markdown())
        with patch("validator._build_openai_client") as mock_client_builder:
            result = validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
            )

        self.assertTrue(result.passed)
        self.assertFalse(result.repaired)
        self.assertEqual(result.attempts_used, 0)
        self.assertEqual(result.rule_report.errors, [])
        mock_client_builder.assert_not_called()

    def test_repairs_missing_h2_keyword_in_first_attempt(self) -> None:
        article_payload = _payload(_missing_h2_keyword_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(
            json.dumps(
                {
                    "patches": [
                        {
                            "op": "replace_h2",
                            "target_index": 0,
                            "text": "## Why smart patio workflow matters",
                        }
                    ]
                }
            )
        )
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            result = validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
            )

        self.assertTrue(result.passed)
        self.assertTrue(result.repaired)
        self.assertEqual(result.attempts_used, 1)
        self.assertIn("## Why smart patio workflow matters", result.article_payload["article_markdown"])

    def test_repairs_low_keyword_density_in_first_attempt(self) -> None:
        article_payload = _payload(_low_density_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(
            json.dumps(
                {
                    "patches": [
                        {
                            "op": "replace_paragraph",
                            "target_index": 2,
                            "text": (
                                "This smart patio workflow paragraph closes density gaps so the "
                                "smart patio workflow remains consistent and measurable, and each "
                                "smart patio workflow step stays actionable."
                            ),
                        }
                    ]
                }
            )
        )
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            result = validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.attempts_used, 1)
        self.assertGreaterEqual(result.rule_report.keyword_count, result.rule_report.keyword_count_min)

    def test_invalid_patch_json_consumes_first_attempt_then_succeeds(self) -> None:
        article_payload = _payload(_missing_h2_keyword_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = [
            _response_with_content("not-json"),
            _response_with_content(
                json.dumps(
                    {
                        "patches": [
                            {
                                "op": "replace_h2",
                                "target_index": 0,
                                "text": "## Why smart patio workflow matters",
                            }
                        ]
                    }
                )
            ),
        ]
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            result = validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
                max_repair_attempts=2,
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.attempts_used, 2)
        self.assertEqual(len(result.attempts), 2)
        self.assertTrue(result.attempts[0].apply_error)
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)

    def test_out_of_range_patch_target_fails_attempt(self) -> None:
        article_payload = _payload(_missing_h2_keyword_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(
            json.dumps(
                {
                    "patches": [
                        {
                            "op": "replace_h2",
                            "target_index": 99,
                            "text": "## Why smart patio workflow matters",
                        }
                    ]
                }
            )
        )
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            with self.assertRaises(ArticleValidationFinalError) as exc:
                validate_article_with_repair(
                    article_payload=article_payload,
                    focus_keyword="smart patio workflow",
                    blog_profile="Outdoor living site.",
                    repair_system_prompt="Fix only requested sections.",
                    max_repair_attempts=1,
                )

        self.assertEqual(exc.exception.attempts_used, 1)
        self.assertTrue(any("H2 heading" in item for item in exc.exception.errors))

    def test_raises_after_two_failed_repair_attempts(self) -> None:
        article_payload = _payload(_missing_h2_keyword_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = [
            _response_with_content("not-json"),
            _response_with_content("still-not-json"),
        ]
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            with self.assertRaises(ArticleValidationFinalError) as exc:
                validate_article_with_repair(
                    article_payload=article_payload,
                    focus_keyword="smart patio workflow",
                    blog_profile="Outdoor living site.",
                    repair_system_prompt="Fix only requested sections.",
                    max_repair_attempts=2,
                )

        self.assertEqual(exc.exception.attempts_used, 2)
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)

    def test_prompt_is_targeted_to_failing_rules(self) -> None:
        article_payload = _payload(_low_density_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(
            json.dumps(
                {
                    "patches": [
                        {
                            "op": "replace_paragraph",
                            "target_index": 2,
                            "text": (
                                "This smart patio workflow paragraph closes density gaps so the "
                                "smart patio workflow remains consistent and measurable, and each "
                                "smart patio workflow step stays actionable."
                            ),
                        }
                    ]
                }
            )
        )
        with patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
            )

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        user_prompt = str(messages[-1]["content"])
        self.assertIn("Increase exact keyword occurrences", user_prompt)
        self.assertIn("do not regenerate the whole article", user_prompt.casefold())

    def test_writes_debug_artifacts_when_directory_is_provided(self) -> None:
        article_payload = _payload(_missing_h2_keyword_markdown())
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(
            json.dumps(
                {
                    "patches": [
                        {
                            "op": "replace_h2",
                            "target_index": 0,
                            "text": "## Why smart patio workflow matters",
                        }
                    ]
                }
            )
        )

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "validator._build_openai_client",
            return_value=(mock_client, "deepseek-chat"),
        ):
            artifact_dir = Path(tmp_dir)
            validate_article_with_repair(
                article_payload=article_payload,
                focus_keyword="smart patio workflow",
                blog_profile="Outdoor living site.",
                repair_system_prompt="Fix only requested sections.",
                artifact_dir=artifact_dir,
            )
            self.assertTrue((artifact_dir / "validator_rule_report.json").exists())
            self.assertTrue((artifact_dir / "validator_attempt_1.json").exists())
            self.assertTrue((artifact_dir / "validator_final.json").exists())

    def test_load_repair_system_prompt_prefers_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {"ARTICLE_VALIDATOR_REPAIR_PROMPT": "Env override prompt"},
            clear=False,
        ):
            prompt = load_repair_system_prompt()
        self.assertEqual(prompt, "Env override prompt")

    def test_load_repair_system_prompt_falls_back_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "article_validator_repair.md"
            prompt_path.write_text("File prompt", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"ARTICLE_VALIDATOR_REPAIR_PROMPT": ""},
                clear=False,
            ), patch("validator.REPAIR_PROMPT_FILE", prompt_path):
                prompt = load_repair_system_prompt()
        self.assertEqual(prompt, "File prompt")

    def test_load_repair_system_prompt_raises_when_env_and_file_are_missing(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "__missing_validator_prompt__.md"
        if missing_path.exists():
            missing_path.unlink()
        with patch.dict(
            os.environ,
            {"ARTICLE_VALIDATOR_REPAIR_PROMPT": ""},
            clear=False,
        ), patch("validator.REPAIR_PROMPT_FILE", missing_path):
            with self.assertRaises(ArticleValidatorError):
                load_repair_system_prompt()


if __name__ == "__main__":
    unittest.main()
