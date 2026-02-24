import unittest

from automating_wf.config.blogs import suggest_primary_category


class CategoryAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.categories = [
            "Backyard Gardening",
            "Backyard Ideas",
            "Curb Appeal",
            "Grilling & Entertaining",
            "Outdoor Living",
        ]

    def test_gardening_content_suggests_backyard_gardening(self) -> None:
        category = suggest_primary_category(
            title="Container Gardening for Sunny Patio Corners",
            content_markdown="Use compost-rich soil and prune plants regularly for healthy growth.",
            category_names=self.categories,
        )
        self.assertEqual(category, "Backyard Gardening")

    def test_grilling_content_suggests_grilling_and_entertaining(self) -> None:
        category = suggest_primary_category(
            title="Backyard BBQ Hosting Checklist",
            content_markdown="Set up your grill station and guest seating for easy weekend hosting.",
            category_names=self.categories,
        )
        self.assertEqual(category, "Grilling & Entertaining")

    def test_low_signal_falls_back_to_outdoor_living(self) -> None:
        category = suggest_primary_category(
            title="Weekend Patio Reset",
            content_markdown="Quick tips for refreshing your space before guests arrive.",
            category_names=self.categories,
        )
        self.assertEqual(category, "Outdoor Living")

    def test_backyard_ideas_is_not_auto_suggested(self) -> None:
        category = suggest_primary_category(
            title="General Backyard Ideas",
            content_markdown="A broad mix of thoughts without clear niche terms.",
            category_names=self.categories,
        )
        self.assertNotEqual(category, "Backyard Ideas")
        self.assertEqual(category, "Outdoor Living")


if __name__ == "__main__":
    unittest.main()
