"""CategoryResolver — Category auto-assignment scoring algorithm.

Pure function service (no providers needed). Scores categories by:
1. **Keyword matches** in ``category_keywords``: title +4, body +2 per match.
2. **Category name token matches**: title +2, body +1 per token.

The deprioritized category is always skipped. When no category scores
above 0, the ``fallback_category`` is returned.

Ported from ``src/automating_wf/config/blogs.py::suggest_primary_category``
but rewritten cleanly: no ``os.getenv`` / ``load_dotenv``, no provider deps.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords — tokens from category names that are too generic to score
# ---------------------------------------------------------------------------

CATEGORY_TOKEN_STOPWORDS: frozenset[str] = frozenset(
    {
        "and",
        "backyard",
        "food",
        "ideas",
        "living",
        "low",
        "outdoor",
        "quick",
        "recipes",
    }
)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

KEYWORD_TITLE_WEIGHT: int = 4
KEYWORD_BODY_WEIGHT: int = 2
TOKEN_TITLE_WEIGHT: int = 2
TOKEN_BODY_WEIGHT: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize_category_name(name: str) -> list[str]:
    """Split a category name into scorable tokens.

    The name is lowercased, ``&`` and ``/`` are replaced with spaces,
    and stopwords are removed.

    Args:
        name: Category name (e.g. ``"Food & Drinks"``).

    Returns:
        A list of non-stopword tokens.
    """
    folded = name.casefold()
    parts = folded.replace("&", " ").replace("/", " ").split()
    return [t for t in parts if t and t not in CATEGORY_TOKEN_STOPWORDS]


# ---------------------------------------------------------------------------
# CategoryResolver
# ---------------------------------------------------------------------------


class CategoryResolver:
    """Score and resolve categories based on keyword and token matches.

    This is a pure-function service — it does **not** depend on any external
    providers, database, or I/O.

    Parameters:
        category_keywords: Mapping from lowercased category name to a list
            of keywords associated with that category.
        fallback_category: Category returned when nothing scores above 0.
        deprioritized_category: Category always excluded from results.
    """

    def __init__(
        self,
        *,
        category_keywords: dict[str, list[str]],
        fallback_category: str = "",
        deprioritized_category: str = "",
    ) -> None:
        self._category_keywords = category_keywords
        self._fallback_category = fallback_category
        self._deprioritized_category = deprioritized_category

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_all(
        self,
        *,
        title: str | None,
        content_markdown: str | None,
        category_names: Sequence[str],
    ) -> dict[str, int]:
        """Compute scores for every category.

        Args:
            title: Article title (may be ``None``).
            content_markdown: Article body text (may be ``None``).
            category_names: Iterable of candidate category names.

        Returns:
            A dict mapping each category name to its integer score.
            Deprioritized categories are excluded.
        """
        title_text = (title or "").casefold()
        body_text = (content_markdown or "").casefold()
        deprioritized_folded = self._deprioritized_category.casefold()

        scores: dict[str, int] = {}

        # Sort categories for deterministic tie-breaking (alphabetical)
        sorted_names = sorted(
            [n.strip() for n in category_names if isinstance(n, str) and n.strip()],
            key=lambda n: n.casefold(),
        )

        for category_name in sorted_names:
            category_folded = category_name.casefold()

            # Skip deprioritized category
            if deprioritized_folded and category_folded == deprioritized_folded:
                continue

            score = 0

            # --- Token scoring from category name ---
            tokens = _tokenize_category_name(category_name)
            for token in tokens:
                if token in title_text:
                    score += TOKEN_TITLE_WEIGHT
                if token in body_text:
                    score += TOKEN_BODY_WEIGHT

            # --- Keyword scoring from category_keywords ---
            for keyword in self._category_keywords.get(category_folded, []):
                keyword_folded = keyword.casefold()
                if keyword_folded in title_text:
                    score += KEYWORD_TITLE_WEIGHT
                if keyword_folded in body_text:
                    score += KEYWORD_BODY_WEIGHT

            scores[category_name] = score

        return scores

    def resolve(
        self,
        *,
        title: str | None,
        content_markdown: str | None,
        category_names: Sequence[str],
    ) -> str:
        """Return the best-matching category name.

        Scoring rules:
        1. Each keyword in ``category_keywords`` matching the title scores +4,
           body scores +2.
        2. Each category-name token matching the title scores +2, body +1.
        3. The deprioritized category is always excluded.
        4. If no category scores > 0, returns ``fallback_category``.
        5. Returns the highest-scoring category (alphabetical first on tie).

        Args:
            title: Article title.
            content_markdown: Article body text.
            category_names: Candidate category names.

        Returns:
            The resolved category name (or ``fallback_category``).
        """
        if not category_names:
            logger.debug("No categories provided; returning fallback.")
            return self._fallback_category

        scores = self.score_all(
            title=title,
            content_markdown=content_markdown,
            category_names=category_names,
        )

        best_name = ""
        best_score = 0

        for name, score in scores.items():
            if score > best_score:
                best_score = score
                best_name = name

        if best_score > 0 and best_name:
            logger.debug(
                "Resolved category '%s' with score %d.", best_name, best_score
            )
            return best_name

        logger.debug("No category scored > 0; returning fallback '%s'.", self._fallback_category)
        return self._fallback_category


# ---------------------------------------------------------------------------
# Convenience function (matches original API from blogs.py)
# ---------------------------------------------------------------------------


def suggest_primary_category(
    *,
    title: str | None,
    content_markdown: str | None,
    category_names: list[str],
    fallback_category: str = "",
    deprioritized_category: str = "",
    category_keywords: dict[str, list[str]] | None = None,
) -> str:
    """Resolve the best category for an article (pure function).

    This is the primary entry point for category resolution. It creates a
    :class:`CategoryResolver` and delegates to :meth:`CategoryResolver.resolve`.

    Args:
        title: Article title.
        content_markdown: Article body markdown.
        category_names: Candidate category names.
        fallback_category: Returned when nothing matches.
        deprioritized_category: Always excluded from results.
        category_keywords: Mapping from category name to keyword list.

    Returns:
        The resolved category name.
    """
    resolver = CategoryResolver(
        category_keywords=category_keywords or {},
        fallback_category=fallback_category,
        deprioritized_category=deprioritized_category,
    )
    return resolver.resolve(
        title=title,
        content_markdown=content_markdown,
        category_names=category_names,
    )
