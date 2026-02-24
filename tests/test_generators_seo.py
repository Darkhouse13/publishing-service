import json
import unittest
from os import environ
from unittest.mock import Mock, patch

from automating_wf.content.generators import (
    ArticleValidationError,
    KEYWORD_COUNT_MAX,
    KEYWORD_COUNT_MIN,
    MIN_ARTICLE_WORD_COUNT,
    derive_focus_keyword,
    generate_article,
    run_hard_validations,
    run_soft_fixes,
    validate_article_seo,
)


def _build_article_payload(
    article_markdown: str,
    focus_keyword: str = "smart patio workflow",
    seo_title: str = "Smart Patio Workflow 2026 Guide",
    meta_description: str = "A practical guide to smart patio workflow for real homes.",
) -> dict[str, str]:
    return {
        "title": "Smart Patio Workflow Guide",
        "article_markdown": article_markdown,
        "hero_image_prompt": "Hero prompt",
        "detail_image_prompt": "Detail prompt",
        "seo_title": seo_title,
        "meta_description": meta_description,
        "focus_keyword": focus_keyword,
    }


def _valid_article_markdown(focus_keyword: str = "smart patio workflow") -> str:
    first_paragraph = (
        f"{focus_keyword} helps homeowners create structured plans without guesswork and keeps work focused "
        "on practical results. A repeatable system improves decision quality and prevents expensive rework."
    )
    h2_heading = f"## Why {focus_keyword} Improves Results"
    keyword_body_paragraph_one = (
        f"Using {focus_keyword} during weekly planning sessions helps prioritize improvements and sequence tasks "
        "in a realistic way. This process keeps homeowners aligned with budgets and timelines."
    )
    keyword_body_paragraph_two = (
        f"Teams that review {focus_keyword} regularly spot gaps early and maintain steady execution through "
        "seasonal shifts. This consistency reduces delays and confusion."
    )
    keyword_body_paragraph_three = (
        f"A documented {focus_keyword} checklist turns vague plans into measurable steps and supports better "
        "handoffs across projects. Consistency creates durable outcomes."
    )
    filler_paragraph = (
        "Practical planning, measured execution, and small iterative improvements help readers build confidence "
        "while reducing waste during project delivery. Careful note taking, realistic timelines, clear ownership, "
        "and frequent check-ins keep each task manageable and maintain momentum throughout changing conditions."
    )
    filler_blocks = [filler_paragraph for _ in range(16)]
    conclusion_h2 = "## Final Thoughts"
    conclusion_paragraph = (
        f"Consistent use of {focus_keyword} turns scattered effort into dependable progress and helps every step "
        "deliver long-term value."
    )

    parts = [
        first_paragraph,
        h2_heading,
        keyword_body_paragraph_one,
        keyword_body_paragraph_two,
        keyword_body_paragraph_three,
        *filler_blocks,
        conclusion_h2,
        conclusion_paragraph,
    ]
    return "\n\n".join(parts)


def _response_with_content(content: str) -> Mock:
    response = Mock()
    choice = Mock()
    choice.message.content = content
    response.choices = [choice]
    return response


class GeneratorsSeoValidationTests(unittest.TestCase):
    def test_run_hard_validations_passes_valid_markdown(self) -> None:
        payload = _build_article_payload(_valid_article_markdown())
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertEqual(errors, [])

    def test_run_hard_validations_fails_word_count_under_minimum(self) -> None:
        payload = _build_article_payload(
            "smart patio workflow starts here.\n\n## smart patio workflow\n\nUseful tips."
        )
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(
            any(f"word count must be >= {MIN_ARTICLE_WORD_COUNT}" in error for error in errors)
        )

    def test_run_hard_validations_word_count_599_fails_threshold(self) -> None:
        payload = _build_article_payload(_valid_article_markdown())
        with patch("automating_wf.content.generators._count_words", return_value=599):
            errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(
            any(f"word count must be >= {MIN_ARTICLE_WORD_COUNT}" in error for error in errors)
        )

    def test_run_hard_validations_word_count_600_passes_threshold_gate(self) -> None:
        payload = _build_article_payload(_valid_article_markdown())
        with patch("automating_wf.content.generators._count_words", return_value=600):
            errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertFalse(
            any(f"word count must be >= {MIN_ARTICLE_WORD_COUNT}" in error for error in errors)
        )

    def test_run_hard_validations_enforces_fixed_keyword_bounds(self) -> None:
        markdown = (
            _valid_article_markdown()
            + "\n\n"
            + " ".join(["smart patio workflow"] * (KEYWORD_COUNT_MAX + 3))
        )
        payload = _build_article_payload(markdown)
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(
            any(
                f"outside allowed range {KEYWORD_COUNT_MIN}–{KEYWORD_COUNT_MAX}" in error
                for error in errors
            )
        )

    def test_run_hard_validations_fails_first_paragraph_keyword_requirement(self) -> None:
        markdown = _valid_article_markdown().replace(
            "smart patio workflow helps homeowners create structured plans without guesswork and keeps work focused on practical results.",
            "A practical workflow helps homeowners create structured plans without guesswork and keeps work focused on practical results.",
            1,
        )
        payload = _build_article_payload(markdown)
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(any("first paragraph" in error for error in errors))

    def test_run_hard_validations_fails_h2_keyword_requirement(self) -> None:
        markdown = _valid_article_markdown().replace(
            "## Why smart patio workflow Improves Results",
            "## Why Better Planning Improves Results",
            1,
        )
        payload = _build_article_payload(markdown)
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(any("H2 heading" in error for error in errors))

    def test_run_hard_validations_fails_when_seo_title_has_no_number(self) -> None:
        payload = _build_article_payload(
            _valid_article_markdown(),
            seo_title="Smart Patio Workflow Guide",
        )
        errors = run_hard_validations(payload, payload["focus_keyword"])
        self.assertTrue(any("seo_title must include at least one number" in error for error in errors))

    def test_validate_article_seo_wrapper_uses_focus_keyword(self) -> None:
        payload = _build_article_payload(_valid_article_markdown())
        self.assertEqual(validate_article_seo(payload), [])


class GeneratorsSeoSoftFixTests(unittest.TestCase):
    def test_run_soft_fixes_truncates_and_injects_keyword_in_seo_title(self) -> None:
        focus_keyword = "compact patio storage"
        payload = _build_article_payload(
            _valid_article_markdown(focus_keyword),
            focus_keyword=focus_keyword,
            seo_title="A very long SEO title without the main keyword but with number 2026 and extra words",
        )
        fixed = run_soft_fixes(payload, focus_keyword)
        self.assertLessEqual(len(fixed["seo_title"]), 60)
        self.assertIn(focus_keyword, fixed["seo_title"].casefold())

    def test_run_soft_fixes_meta_description_bounds_and_keyword(self) -> None:
        focus_keyword = "compact patio storage"
        payload = _build_article_payload(
            _valid_article_markdown(focus_keyword),
            focus_keyword=focus_keyword,
            meta_description="Short description.",
        )
        fixed = run_soft_fixes(payload, focus_keyword)
        self.assertGreaterEqual(len(fixed["meta_description"]), 120)
        self.assertLessEqual(len(fixed["meta_description"]), 155)
        self.assertIn(focus_keyword, fixed["meta_description"].casefold())

    def test_run_soft_fixes_removes_duplicate_leading_h1(self) -> None:
        focus_keyword = "compact patio storage"
        payload = _build_article_payload(
            f"# Smart Patio Workflow Guide\n\n{_valid_article_markdown(focus_keyword)}",
            focus_keyword=focus_keyword,
        )
        fixed = run_soft_fixes(payload, focus_keyword)
        self.assertFalse(fixed["article_markdown"].lstrip().startswith("# Smart Patio Workflow Guide"))

    def test_run_soft_fixes_splits_plain_text_paragraphs_over_four_sentences(self) -> None:
        focus_keyword = "smart patio workflow"
        overlong_paragraph = (
            "This plan is clear. It is practical. It is measurable. It is affordable. It is easy to execute."
        )
        markdown = (
            f"{focus_keyword} makes planning easier for homeowners and keeps projects predictable.\n\n"
            f"## Why {focus_keyword} matters\n\n"
            f"{overlong_paragraph}"
        )
        payload = _build_article_payload(markdown, focus_keyword=focus_keyword)
        fixed = run_soft_fixes(payload, focus_keyword)
        self.assertIn("affordable.\n\nIt is easy to execute.", fixed["article_markdown"])


class GeneratorsSeoRetryTests(unittest.TestCase):
    def test_generate_article_retries_with_feedback_and_succeeds(self) -> None:
        invalid_markdown = (
            "smart patio workflow starts here.\n\n## Why smart patio workflow\n\nShort body only."
        )
        valid_markdown = _valid_article_markdown()
        invalid_json = json.dumps(_build_article_payload(invalid_markdown))
        valid_json = json.dumps(_build_article_payload(valid_markdown))

        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = [
            _response_with_content(invalid_json),
            _response_with_content(valid_json),
        ]

        with patch("automating_wf.content.generators._build_deepseek_client", return_value=(mock_client, "deepseek-chat")), patch.dict(
            environ,
            {"DEEPSEEK_ARTICLE_ATTEMPTS": "3"},
            clear=False,
        ):
            result = generate_article(
                topic="Smart patio planning",
                vibe="Practical",
                blog_profile="Outdoor planning",
                focus_keyword="smart patio workflow",
            )

        self.assertEqual(result["focus_keyword"], "smart patio workflow")
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        retry_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
        retry_user_message = retry_messages[-1]["content"]
        self.assertIn("Your previous attempt failed these validations", retry_user_message)

    def test_generate_article_fails_after_all_attempts_with_structured_errors(self) -> None:
        invalid_markdown = (
            "smart patio workflow starts here.\n\n## Why smart patio workflow\n\nShort body only."
        )
        invalid_json = json.dumps(_build_article_payload(invalid_markdown))

        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = [
            _response_with_content(invalid_json),
            _response_with_content(invalid_json),
            _response_with_content(invalid_json),
        ]

        with patch("automating_wf.content.generators._build_deepseek_client", return_value=(mock_client, "deepseek-chat")), patch.dict(
            environ,
            {"DEEPSEEK_ARTICLE_ATTEMPTS": "3"},
            clear=False,
        ):
            with self.assertRaises(ArticleValidationError) as exc:
                generate_article(
                    topic="Smart patio planning",
                    vibe="Practical",
                    blog_profile="Outdoor planning",
                    focus_keyword="smart patio workflow",
                )

        self.assertIn("after 3 attempts", str(exc.exception))
        self.assertTrue(exc.exception.errors)
        self.assertIsInstance(exc.exception.payload, dict)
        self.assertIn("article_markdown", exc.exception.payload)
        self.assertIn("content_markdown", exc.exception.payload)

    def test_generate_article_preserves_internal_placeholder_literal(self) -> None:
        valid_markdown = _valid_article_markdown("smart patio workflow")
        valid_json = json.dumps(_build_article_payload(valid_markdown))

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = _response_with_content(valid_json)

        with patch("automating_wf.content.generators._build_deepseek_client", return_value=(mock_client, "deepseek-chat")):
            generate_article(
                topic="Smart patio planning",
                vibe="Practical",
                blog_profile="Outdoor planning",
                focus_keyword="smart patio workflow",
            )

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        user_message = messages[-1]["content"]
        self.assertIn("{{INTERNAL_URL}}", user_message)
        self.assertNotIn("{INTERNAL_URL}", user_message.replace("{{INTERNAL_URL}}", ""))


class FocusKeywordDerivationTests(unittest.TestCase):
    def test_derive_focus_keyword_uses_phrase_for_keyword_like_topic(self) -> None:
        self.assertEqual(
            derive_focus_keyword("streamlit seo optimization"),
            "streamlit seo optimization",
        )

    def test_derive_focus_keyword_handles_sentence_like_topic(self) -> None:
        keyword = derive_focus_keyword(
            "Write an article about the benefits of using Streamlit for data science dashboards."
        )
        token_count = len(keyword.split())
        self.assertGreaterEqual(token_count, 2)
        self.assertLessEqual(token_count, 5)
        self.assertNotIn("write", keyword)
        self.assertNotIn("article", keyword)


if __name__ == "__main__":
    unittest.main()
