import unittest

from automating_wf.config.blogs import suggest_primary_category


# These tests validate the suggest_primary_category scoring logic using
# explicit category_keywords so they are independent of the live blog config.
PATIO_CATEGORY_KEYWORDS = {
    "outdoor living": [
        "patio", "outdoor", "deck", "backyard setup", "lounging", "outdoor furniture",
    ],
    "curb appeal": ["curb", "front yard", "entryway", "facade", "mailbox", "pathway"],
    "backyard gardening": [
        "garden", "gardening", "plant", "soil", "pruning", "compost", "container", "perennial",
    ],
    "grilling & entertaining": [
        "grill", "bbq", "barbecue", "smoker", "fire pit", "hosting", "guests", "party",
    ],
}
RECIPE_CATEGORY_KEYWORDS = {
    "recipes": [],
    "breakfast & brunch": [
        "breakfast",
        "brunch",
        "eggs",
        "omelet",
        "omelette",
        "pancakes",
        "waffles",
        "smoothie",
        "french toast",
    ],
    "quick lunches": [
        "lunch",
        "salad",
        "sandwich",
        "wrap",
        "grain bowl",
        "soup",
        "meal prep lunch",
    ],
    "weeknight dinner": [
        "weeknight",
        "dinner",
        "one-pan",
        "sheet pan",
        "skillet",
        "30-minute dinner",
        "pasta",
    ],
    "desserts": [
        "dessert",
        "cake",
        "cookie",
        "brownies",
        "pie",
        "ice cream",
        "chocolate",
    ],
    "spring produce": [
        "spring",
        "asparagus",
        "peas",
        "ramps",
        "radish",
        "rhubarb",
    ],
}


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
            category_keywords=PATIO_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Backyard Gardening")

    def test_grilling_content_suggests_grilling_and_entertaining(self) -> None:
        category = suggest_primary_category(
            title="Backyard BBQ Hosting Checklist",
            content_markdown="Set up your grill station and guest seating for easy weekend hosting.",
            category_names=self.categories,
            category_keywords=PATIO_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Grilling & Entertaining")

    def test_low_signal_falls_back_to_outdoor_living(self) -> None:
        category = suggest_primary_category(
            title="Weekend Patio Reset",
            content_markdown="Quick tips for refreshing your space before guests arrive.",
            category_names=self.categories,
            fallback_category="Outdoor Living",
            category_keywords=PATIO_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Outdoor Living")

    def test_backyard_ideas_is_not_auto_suggested(self) -> None:
        category = suggest_primary_category(
            title="General Backyard Ideas",
            content_markdown="A broad mix of thoughts without clear niche terms.",
            category_names=self.categories,
            fallback_category="Outdoor Living",
            deprioritized_category="Backyard Ideas",
            category_keywords=PATIO_CATEGORY_KEYWORDS,
        )
        self.assertNotEqual(category, "Backyard Ideas")
        self.assertEqual(category, "Outdoor Living")


class RecipeCategoryAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.categories = [
            "Breakfast & Brunch",
            "Desserts",
            "Quick Lunches",
            "Recipes",
            "Spring Produce",
            "Weeknight Dinner",
        ]

    def test_weeknight_recipe_prefers_specific_category_over_recipes(self) -> None:
        category = suggest_primary_category(
            title="One-Pan Lemon Chicken for Busy Weeknights",
            content_markdown=(
                "This sheet pan dinner is a fast 30-minute dinner with pantry staples."
            ),
            category_names=self.categories,
            fallback_category="Recipes",
            deprioritized_category="Recipes",
            category_keywords=RECIPE_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Weeknight Dinner")

    def test_spring_recipe_maps_to_seasonal_category(self) -> None:
        category = suggest_primary_category(
            title="Shaved Asparagus Salad with Peas and Mint",
            content_markdown="A bright spring salad built around tender asparagus and peas.",
            category_names=self.categories,
            fallback_category="Recipes",
            deprioritized_category="Recipes",
            category_keywords=RECIPE_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Spring Produce")

    def test_low_signal_recipe_falls_back_to_recipes(self) -> None:
        category = suggest_primary_category(
            title="How to Stock a Better Pantry",
            content_markdown="A practical guide to kitchen staples and storage habits.",
            category_names=self.categories,
            fallback_category="Recipes",
            deprioritized_category="Recipes",
            category_keywords=RECIPE_CATEGORY_KEYWORDS,
        )
        self.assertEqual(category, "Recipes")


if __name__ == "__main__":
    unittest.main()
