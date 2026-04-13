from __future__ import annotations

from typing import Any, Callable


VIBE_SUGGESTION_COUNT = 12
RECIPE_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "recipes": [],
    "breakfast & brunch": [
        "breakfast",
        "brunch",
        "eggs",
        "omelet",
        "omelette",
        "pancakes",
        "waffles",
        "granola",
        "smoothie",
        "french toast",
        "muffins",
        "avocado toast",
    ],
    "quick lunches": [
        "lunch",
        "salad",
        "sandwich",
        "wrap",
        "grain bowl",
        "bowl",
        "soup",
        "meal prep lunch",
        "desk lunch",
        "midday meal",
        "15-minute lunch",
        "20-minute lunch",
    ],
    "weeknight dinner": [
        "weeknight",
        "dinner",
        "one-pan",
        "one pot",
        "one-pot",
        "sheet pan",
        "skillet",
        "30-minute dinner",
        "family dinner",
        "pasta",
        "chicken dinner",
        "salmon dinner",
    ],
    "sunday supper": [
        "sunday supper",
        "sunday dinner",
        "slow-cooked",
        "slow cooked",
        "braise",
        "braised",
        "roast",
        "family-style",
        "gathering",
        "shared table",
        "centerpiece",
    ],
    "appetizers": [
        "appetizer",
        "starter",
        "snack",
        "dip",
        "crostini",
        "canape",
        "bite-sized",
        "party platter",
        "charcuterie",
        "small plates",
    ],
    "desserts": [
        "dessert",
        "cake",
        "cookie",
        "brownies",
        "tart",
        "pie",
        "pudding",
        "ice cream",
        "chocolate",
        "sweet treat",
    ],
    "vegetarian": [
        "vegetarian",
        "meatless",
        "veggie",
        "vegetable-forward",
        "lentils",
        "chickpeas",
        "beans",
        "paneer",
        "mushroom",
    ],
    "vegan": [
        "vegan",
        "plant-based",
        "dairy-free",
        "egg-free",
        "cashew cream",
        "tempeh",
        "tofu",
        "coconut milk",
        "no butter",
    ],
    "gluten-free": [
        "gluten-free",
        "gluten free",
        "rice flour",
        "almond flour",
        "cornstarch",
        "celiac",
        "without flour",
    ],
    "low carb": [
        "low carb",
        "keto",
        "cauliflower rice",
        "zucchini noodles",
        "lettuce wraps",
        "high protein",
        "low-sugar",
    ],
    "spring produce": [
        "spring",
        "asparagus",
        "peas",
        "ramps",
        "radish",
        "artichoke",
        "rhubarb",
        "strawberries",
        "fava",
    ],
    "summer grilling": [
        "grill",
        "grilled",
        "grilling",
        "barbecue",
        "bbq",
        "skewers",
        "corn on the cob",
        "cookout",
        "flame-kissed",
    ],
    "autumn baking": [
        "autumn",
        "fall baking",
        "pumpkin",
        "apple",
        "pear",
        "cinnamon",
        "loaf cake",
        "crumble",
        "coffee cake",
    ],
    "winter comfort": [
        "winter",
        "comfort food",
        "cozy",
        "stew",
        "chili",
        "casserole",
        "soup",
        "pot roast",
        "warming bowl",
    ],
}

BLOG_CONFIGS: dict[str, dict[str, Any]] = {
    "The Weekend Folio": {
        "profile_prompt": (
            "Lifestyle-weekend editorial blog focused on weekend routines, home and "
            "lifestyle planning, practical guides, local leisure, and balanced "
            "self-improvement."
        ),
        "wp_env_suffix": "THE_WEEKEND_FOLIO",
        "prompt_type": "standard",
        "fallback_category": "Weekend Living",
        "deprioritized_category": "Uncategorized",
        "category_keywords": {
            "weekend living": ["weekend", "routine", "reset", "life admin", "planning"],
            "home": ["home", "declutter", "kitchen", "living room", "organization"],
            "food & recipes": ["recipe", "meal", "cook", "brunch", "dinner"],
            "travel": ["trip", "city break", "itinerary", "destination", "staycation"],
        },
    },
    "Your Midnight Desk": {
        "profile_prompt": (
            "Recipe and food blog featuring easy-to-follow home-cooked recipes, "
            "meal planning ideas, weeknight dinners, baking, comfort food, "
            "and seasonal cooking inspiration."
        ),
        "wp_env_suffix": "YOUR_MIDNIGHT_DESK",
        "prompt_type": "recipe",
        "fallback_category": "Recipes",
        "deprioritized_category": "Recipes",
        "category_keywords": RECIPE_CATEGORY_KEYWORDS,
    },
    "The Sunday Patio": {
        "profile_prompt": (
            "Recipe and food blog featuring easy-to-follow home-cooked recipes, "
            "meal planning ideas, weeknight dinners, baking, comfort food, "
            "and seasonal cooking inspiration."
        ),
        "wp_env_suffix": "THE_SUNDAY_PATIO",
        "prompt_type": "recipe",
        "fallback_category": "Recipes",
        "deprioritized_category": "Recipes",
        "category_keywords": RECIPE_CATEGORY_KEYWORDS,
    },
}
DEFAULT_BLOG_PROFILE = "The Sunday Patio"
CATEGORY_TOKEN_STOPWORDS = {"and", "backyard", "food", "ideas", "living", "low", "outdoor", "quick", "recipes"}


def resolve_blog_config(selected_blog: str) -> dict[str, Any]:
    if selected_blog not in BLOG_CONFIGS:
        raise ValueError(f"Unknown blog selection: {selected_blog}")
    return BLOG_CONFIGS[selected_blog]


def resolve_blog_profile(selected_blog: str) -> str:
    return str(resolve_blog_config(selected_blog)["profile_prompt"])


def resolve_prompt_type(selected_blog: str) -> str:
    return str(resolve_blog_config(selected_blog).get("prompt_type", "standard"))


def resolve_target_suffix(selected_blog: str) -> str:
    suffix = str(resolve_blog_config(selected_blog)["wp_env_suffix"]).strip()
    if not suffix:
        raise ValueError(f"Blog '{selected_blog}' is missing wp_env_suffix.")
    return suffix


def fetch_vibes_for_blog(
    selected_blog: str,
    generator: Callable[..., list[str]],
    count: int = VIBE_SUGGESTION_COUNT,
) -> list[str]:
    return generator(blog_profile=resolve_blog_profile(selected_blog), count=count)


def _sorted_category_names(category_names: list[str], deprioritized_category: str = "") -> list[str]:
    deprioritized_folded = deprioritized_category.casefold()
    return sorted(
        [name.strip() for name in category_names if isinstance(name, str) and name.strip()],
        key=lambda name: (
            bool(deprioritized_folded and name.casefold() == deprioritized_folded),
            name.casefold(),
        ),
    )


def _preferred_fallback_category(
    category_names: list[str],
    fallback_category: str = "",
    deprioritized_category: str = "",
) -> str:
    if not category_names:
        return ""
    fallback_folded = fallback_category.casefold()
    deprioritized_folded = deprioritized_category.casefold()
    if fallback_folded:
        for name in category_names:
            if name.casefold() == fallback_folded:
                return name
    for name in category_names:
        if not deprioritized_folded or name.casefold() != deprioritized_folded:
            return name
    return category_names[0]


def suggest_primary_category(
    title: str,
    content_markdown: str,
    category_names: list[str],
    fallback_category: str = "Outdoor Living",
    deprioritized_category: str = "Backyard Ideas",
    category_keywords: dict[str, list[str]] | None = None,
) -> str:
    sorted_categories = _sorted_category_names(category_names, deprioritized_category)
    if not sorted_categories:
        return ""

    fallback = _preferred_fallback_category(
        sorted_categories,
        fallback_category=fallback_category,
        deprioritized_category=deprioritized_category,
    )
    title_text = (title or "").casefold()
    body_text = (content_markdown or "").casefold()
    if category_keywords is None:
        default_keywords = resolve_blog_config(DEFAULT_BLOG_PROFILE).get(
            "category_keywords", {}
        )
        keyword_map = dict(default_keywords)
    else:
        keyword_map = category_keywords
    deprioritized_folded = deprioritized_category.casefold()

    best_name = ""
    best_score = 0
    for category_name in sorted_categories:
        category_folded = category_name.casefold()
        if deprioritized_folded and category_folded == deprioritized_folded:
            continue

        score = 0
        tokens = [
            token
            for token in category_folded.replace("&", " ").replace("/", " ").split()
            if token and token not in CATEGORY_TOKEN_STOPWORDS
        ]
        for token in tokens:
            if token in title_text:
                score += 2
            if token in body_text:
                score += 1

        for keyword in keyword_map.get(category_folded, []):
            if keyword in title_text:
                score += 4
            if keyword in body_text:
                score += 2

        if score > best_score:
            best_score = score
            best_name = category_name

    if best_name and best_score > 0:
        return best_name
    return fallback
