"""Prompt templates for article generation.

Contains the system prompt and user prompt template used by
:class:`ArticleGenerator` to produce SEO-optimised blog articles.
"""

from __future__ import annotations

ARTICLE_GENERATION_SYSTEM_PROMPT = (
    "You are an expert SEO blog writer. "
    "Return valid JSON only with no extra text or markdown fences."
)

ARTICLE_GENERATION_USER_PROMPT = (
    "Topic: {topic}\n"
    "Vibe/Style: {vibe}\n\n"
    "Blog Domain Context: {profile_prompt}\n\n"
    "You are an SEO content writer. Generate a blog article as a JSON object\n"
    "with these exact keys: title, article_markdown, hero_image_prompt,\n"
    "detail_image_prompt, seo_title, meta_description, focus_keyword.\n\n"
    "CONTENT RULES:\n"
    "1. Write 600–900 words (excluding headings and markdown syntax).\n"
    '2. Use the EXACT focus keyword "{focus_keyword}" between 5 and 9 times\n'
    "   in the body text. This count is non-negotiable — fewer or more will\n"
    "   be rejected.\n"
    "3. Start with a 2–4 sentence introductory paragraph. The focus keyword\n"
    "   MUST appear within the first two sentences.\n"
    "4. Use at least 3 H2 subheadings. At least one H2 MUST contain the\n"
    "   exact focus keyword.\n"
    "5. Every paragraph must be 2–4 sentences. No single-sentence paragraphs.\n"
    "   No paragraphs longer than 4 sentences.\n"
    "6. Do NOT begin the article with an H1 heading. The title is handled\n"
    "   separately by the system.\n"
    "7. Include exactly 1 internal markdown link: [anchor text]({{INTERNAL_URL}})\n"
    "   Use {{INTERNAL_URL}} as the literal placeholder — the system will\n"
    "   replace it.\n"
    "8. Include exactly 1 external markdown link to a relevant authority\n"
    '   source (e.g., official documentation, Wikipedia, .gov, .edu). Do\n'
    '   not add rel="nofollow".\n'
    '9. End with a concrete, actionable conclusion under an H2 heading such\n'
    '   as "## Final Thoughts" or "## Wrapping Up".\n\n'
    "SEO META RULES:\n"
    "10. seo_title: Begin with or place the focus keyword near the start.\n"
    "    Include exactly one number. Maximum 55 characters total.\n"
    "11. meta_description: MUST contain the focus keyword. Must be 130–150\n"
    "    characters. Write it as a compelling call-to-action.\n"
    '12. focus_keyword: Return the EXACT keyword provided: "{focus_keyword}"\n\n'
    "IMAGE PROMPTS:\n"
    "13. hero_image_prompt: A detailed prompt for generating a hero image\n"
    "    relevant to the article topic. No text in the image.\n"
    "14. detail_image_prompt: A detailed prompt for a secondary in-article\n"
    "    image. Include an alt-text suggestion that contains the focus keyword.\n\n"
    "OUTPUT FORMAT:\n"
    "Return ONLY valid JSON. No markdown code fences. No commentary outside\n"
    "the JSON object. The response must start with {{ and end with }}."
)
