from __future__ import annotations

from typing import Any, Callable


VIBE_SUGGESTION_COUNT = 12

BLOG_CONFIGS: dict[str, dict[str, Any]] = {
    "The Weekend Folio": {
        "profile_prompt": (
            "Lifestyle-weekend editorial blog focused on weekend routines, home and "
            "lifestyle planning, practical guides, local leisure, and balanced "
            "self-improvement."
        ),
        "wp_env_suffix": "THE_WEEKEND_FOLIO",
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
            "Dark mode productivity and desk-setup blog focused on workspaces, "
            "lighting, peripherals, software workflows, and intentional deep-work "
            "routines."
        ),
        "wp_env_suffix": "YOUR_MIDNIGHT_DESK",
        "fallback_category": "Desk Setup",
        "deprioritized_category": "Uncategorized",
        "category_keywords": {
            "desk setup": ["desk", "workspace", "monitor", "chair", "ergonomic"],
            "productivity": ["productivity", "focus", "workflow", "routine", "deep work"],
            "gear": ["keyboard", "mouse", "microphone", "peripheral", "laptop"],
            "lighting": ["lighting", "rgb", "lamp", "ambient", "backlight"],
        },
    },
    "The Sunday Patio": {
        "profile_prompt": (
            "Outdoor living blog focused on patios, backyard lifestyle, seasonal "
            "gardening, outdoor entertaining, and practical weekend DIY improvements."
        ),
        "wp_env_suffix": "THE_SUNDAY_PATIO",
        "fallback_category": "Outdoor Living",
        "deprioritized_category": "Backyard Ideas",
        "category_keywords": {
            "outdoor living": [
                "patio",
                "outdoor",
                "deck",
                "backyard setup",
                "lounging",
                "outdoor furniture",
            ],
            "curb appeal": ["curb", "front yard", "entryway", "facade", "mailbox", "pathway"],
            "backyard gardening": [
                "garden",
                "gardening",
                "plant",
                "soil",
                "pruning",
                "compost",
                "container",
                "perennial",
            ],
            "grilling & entertaining": [
                "grill",
                "bbq",
                "barbecue",
                "smoker",
                "fire pit",
                "hosting",
                "guests",
                "party",
            ],
        },
    },
}
DEFAULT_BLOG_PROFILE = "The Sunday Patio"
CATEGORY_TOKEN_STOPWORDS = {"and", "backyard", "outdoor", "ideas", "living"}


def resolve_blog_config(selected_blog: str) -> dict[str, Any]:
    if selected_blog not in BLOG_CONFIGS:
        raise ValueError(f"Unknown blog selection: {selected_blog}")
    return BLOG_CONFIGS[selected_blog]


def resolve_blog_profile(selected_blog: str) -> str:
    return str(resolve_blog_config(selected_blog)["profile_prompt"])


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
