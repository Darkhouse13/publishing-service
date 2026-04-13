import unittest
from unittest.mock import patch

from automating_wf.engine.pipeline import _resolve_category_id_for_article


class PipelineCategoryResolutionTests(unittest.TestCase):
    def test_recipe_article_resolves_to_specific_matching_category(self) -> None:
        categories = [
            {"id": 14, "name": "Recipes"},
            {"id": 16, "name": "Quick Lunches"},
            {"id": 17, "name": "Weeknight Dinner"},
            {"id": 20, "name": "Desserts"},
        ]
        article_payload = {
            "title": "One-Pan Lemon Chicken for Busy Weeknights",
            "article_markdown": (
                "This easy sheet pan dinner is a fast 30-minute dinner for a busy evening."
            ),
        }

        with patch(
            "automating_wf.engine.pipeline.list_categories",
            return_value=categories,
        ), patch(
            "automating_wf.engine.pipeline.resolve_category_id",
            return_value=17,
        ) as mock_resolve:
            category_id = _resolve_category_id_for_article(
                target_suffix="YOUR_MIDNIGHT_DESK",
                blog_name="Your Midnight Desk",
                article_payload=article_payload,
            )

        self.assertEqual(category_id, 17)
        self.assertEqual(
            mock_resolve.call_args.kwargs,
            {
                "selected_name": "Weeknight Dinner",
                "typed_new_name": "",
                "target_suffix": "YOUR_MIDNIGHT_DESK",
            },
        )

    def test_recipe_article_falls_back_to_recipes_when_signal_is_generic(self) -> None:
        categories = [
            {"id": 14, "name": "Recipes"},
            {"id": 15, "name": "Breakfast & Brunch"},
            {"id": 20, "name": "Desserts"},
        ]
        article_payload = {
            "title": "How to Stock a Better Pantry",
            "content_markdown": "A practical guide to kitchen staples and storage habits.",
        }

        with patch(
            "automating_wf.engine.pipeline.list_categories",
            return_value=categories,
        ), patch(
            "automating_wf.engine.pipeline.resolve_category_id",
            return_value=14,
        ) as mock_resolve:
            category_id = _resolve_category_id_for_article(
                target_suffix="YOUR_MIDNIGHT_DESK",
                blog_name="Your Midnight Desk",
                article_payload=article_payload,
            )

        self.assertEqual(category_id, 14)
        self.assertEqual(mock_resolve.call_args.kwargs["selected_name"], "Recipes")

    def test_returns_none_when_no_categories_exist(self) -> None:
        with patch("automating_wf.engine.pipeline.list_categories", return_value=[]):
            category_id = _resolve_category_id_for_article(
                target_suffix="YOUR_MIDNIGHT_DESK",
                blog_name="Your Midnight Desk",
                article_payload={"title": "Any Recipe", "article_markdown": "Content"},
            )

        self.assertIsNone(category_id)


if __name__ == "__main__":
    unittest.main()
