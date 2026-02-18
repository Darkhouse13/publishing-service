import unittest
from unittest.mock import Mock

from app import (
    _init_session_state,
    fetch_vibes_for_blog,
    missing_seo_publish_fields,
    maybe_autofill_topic,
    reconcile_topic_flags,
    resolve_target_suffix,
    resolve_blog_profile,
    sanitize_article_markdown_for_preview,
)


class _SessionState(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


class _StStub:
    def __init__(self) -> None:
        self.session_state = _SessionState()


class VibeWorkflowTests(unittest.TestCase):
    def test_blog_scope_calls_generator_with_expected_profile(self) -> None:
        mock_generator = Mock(return_value=["Topic A", "Topic B"])

        weekend_result = fetch_vibes_for_blog("The Weekend Folio", mock_generator, count=12)
        midnight_result = fetch_vibes_for_blog("Your Midnight Desk", mock_generator, count=12)
        sunday_result = fetch_vibes_for_blog("The Sunday Patio", mock_generator, count=12)
        self.assertEqual(weekend_result, ["Topic A", "Topic B"])
        self.assertEqual(midnight_result, ["Topic A", "Topic B"])
        self.assertEqual(sunday_result, ["Topic A", "Topic B"])

        self.assertEqual(mock_generator.call_count, 3)
        weekend_profile = resolve_blog_profile("The Weekend Folio")
        midnight_profile = resolve_blog_profile("Your Midnight Desk")
        sunday_profile = resolve_blog_profile("The Sunday Patio")
        self.assertEqual(
            mock_generator.call_args_list[0].kwargs,
            {"blog_profile": weekend_profile, "count": 12},
        )
        self.assertEqual(
            mock_generator.call_args_list[1].kwargs,
            {"blog_profile": midnight_profile, "count": 12},
        )
        self.assertEqual(
            mock_generator.call_args_list[2].kwargs,
            {"blog_profile": sunday_profile, "count": 12},
        )

    def test_init_session_state_defaults_to_sunday_patio(self) -> None:
        st_stub = _StStub()
        _init_session_state(st_stub)
        self.assertEqual(st_stub.session_state.selected_blog, "The Sunday Patio")

    def test_target_suffix_resolution_for_each_blog(self) -> None:
        self.assertEqual(resolve_target_suffix("The Sunday Patio"), "THE_SUNDAY_PATIO")
        self.assertEqual(resolve_target_suffix("The Weekend Folio"), "THE_WEEKEND_FOLIO")
        self.assertEqual(resolve_target_suffix("Your Midnight Desk"), "YOUR_MIDNIGHT_DESK")

    def test_autofill_when_topic_is_not_custom(self) -> None:
        topic, autofilled = maybe_autofill_topic(
            selected_vibe="Ambient Monitor Lighting Blueprint",
            current_topic="",
            topic_is_custom=False,
        )
        self.assertEqual(topic, "Ambient Monitor Lighting Blueprint")
        self.assertEqual(autofilled, "Ambient Monitor Lighting Blueprint")

    def test_manual_edit_locks_topic_against_overwrite(self) -> None:
        original_topic, autofilled = maybe_autofill_topic(
            selected_vibe="Dark Keyboard Setup",
            current_topic="",
            topic_is_custom=False,
        )
        topic_is_custom, last_autofilled = reconcile_topic_flags(
            previous_topic=original_topic,
            current_topic="Dark Keyboard Setup for Focus Nights",
            topic_is_custom=False,
            last_autofilled_topic=autofilled,
        )

        self.assertTrue(topic_is_custom)
        overwritten_topic, new_autofilled = maybe_autofill_topic(
            selected_vibe="Desk Cable Route Guide",
            current_topic="Dark Keyboard Setup for Focus Nights",
            topic_is_custom=topic_is_custom,
        )
        self.assertEqual(overwritten_topic, "Dark Keyboard Setup for Focus Nights")
        self.assertEqual(new_autofilled, "")
        self.assertEqual(last_autofilled, autofilled)

    def test_clearing_topic_reenables_autofill(self) -> None:
        topic_is_custom, last_autofilled = reconcile_topic_flags(
            previous_topic="Manual Topic",
            current_topic="",
            topic_is_custom=True,
            last_autofilled_topic="Old Autofill",
        )
        self.assertFalse(topic_is_custom)
        self.assertEqual(last_autofilled, "")

        topic, autofilled = maybe_autofill_topic(
            selected_vibe="Cozy Yarn Storage Wall",
            current_topic="",
            topic_is_custom=topic_is_custom,
        )
        self.assertEqual(topic, "Cozy Yarn Storage Wall")
        self.assertEqual(autofilled, "Cozy Yarn Storage Wall")

    def test_preview_sanitizer_strips_duplicate_h1(self) -> None:
        sanitized, stripped = sanitize_article_markdown_for_preview(
            title="My Draft",
            content_markdown="# My Draft\n\nParagraph one.",
        )
        self.assertTrue(stripped)
        self.assertEqual(sanitized, "Paragraph one.")

    def test_preview_sanitizer_preserves_non_matching_h1(self) -> None:
        markdown = "# Different\n\nParagraph one."
        sanitized, stripped = sanitize_article_markdown_for_preview(
            title="My Draft",
            content_markdown=markdown,
        )
        self.assertFalse(stripped)
        self.assertEqual(sanitized, markdown)

    def test_missing_seo_publish_fields_detects_required_keys(self) -> None:
        missing = missing_seo_publish_fields(
            {
                "article_markdown": "Body",
                "seo_title": "SEO Title",
                "meta_description": "Meta description",
                "focus_keyword": "",
            }
        )
        self.assertEqual(missing, ["focus_keyword"])


if __name__ == "__main__":
    unittest.main()
