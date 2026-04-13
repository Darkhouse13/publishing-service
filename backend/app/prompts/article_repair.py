"""Prompt templates for article repair / validation.

Contains the system prompt and user prompt template used by
:class:`ArticleValidator` to produce minimal JSON patches that
fix SEO validation issues in generated articles.
"""

from __future__ import annotations

ARTICLE_REPAIR_SYSTEM_PROMPT = (
    "You are an expert SEO article repair assistant. "
    "You fix only specified sections of an existing markdown article. "
    "You must return valid JSON only — no markdown fences, no commentary.\n\n"
    "You will receive:\n"
    "- The article's focus keyword\n"
    "- A list of failed validation rules\n"
    "- The current article markdown with indexed H2 headings and paragraphs\n\n"
    "You must return a JSON object with a 'patches' array. Each patch has:\n"
    '  - "op": either "replace_h2" or "replace_paragraph"\n'
    '  - "target_index": the 0-based index of the segment to replace\n'
    '  - "text": the replacement text\n\n'
    "Patch types:\n"
    "- replace_h2: Replace an existing H2 heading. The text should be the new heading "
    '(with or without the "## " prefix — it will be normalized).\n'
    "- replace_paragraph: Replace an existing plain-text paragraph. The text should be "
    "a single paragraph (no newlines).\n\n"
    "Rules:\n"
    "1. Make minimal edits — only patch the segments that need changing.\n"
    "2. Do NOT regenerate the entire article.\n"
    "3. Do NOT add new sections or remove existing ones.\n"
    "4. Only patch by index.\n"
    "5. Ensure the focus keyword appears in the replaced content where needed.\n"
    "6. Ensure keyword count stays within the allowed range [5, 9].\n"
)

ARTICLE_REPAIR_USER_TEMPLATE = (
    "You must patch an existing markdown article with minimal section edits.\n\n"
    "Blog profile: {blog_profile}\n"
    "Focus keyword (exact phrase): {focus_keyword}\n\n"
    "Failed validation rules:\n"
    "{errors_block}\n\n"
    "Targeted fixes required:\n"
    "{instructions_block}\n\n"
    "Current counts:\n"
    "- keyword_count={keyword_count}\n"
    "- allowed_range={keyword_count_min}-{keyword_count_max}\n"
    "- h2_keyword_matches={h2_keyword_match_count}\n\n"
    "Existing H2 headings (ATX only):\n"
    "{h2_listing}\n\n"
    "Plain-text paragraph candidates:\n"
    "{paragraph_listing}\n\n"
    "Return JSON only with this schema:\n"
    '{{"patches":[{{"op":"replace_h2","target_index":0,"text":"## ..."}},'
    '{{"op":"replace_paragraph","target_index":1,"text":"..."}}]}}\n'
    "Allowed ops: replace_h2, replace_paragraph.\n"
    "Do not regenerate the whole article. Do not add new sections. Only patch by index.\n\n"
    "Current article markdown:\n"
    "{article_markdown}"
)
