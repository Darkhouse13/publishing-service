import unittest

from automating_wf.content.generators import GenerationError, parse_article_response, parse_vibe_response


class GeneratorsParserTests(unittest.TestCase):
    def test_parses_clean_json(self) -> None:
        raw = (
            '{"title":"A Title","article_markdown":"Intro paragraph","hero_image_prompt":"hero",'
            '"detail_image_prompt":"detail","seo_title":"SEO Title","meta_description":"Meta",'
            '"focus_keyword":"focus keyword"}'
        )
        parsed = parse_article_response(raw)
        self.assertEqual(parsed["title"], "A Title")
        self.assertEqual(parsed["article_markdown"], "Intro paragraph")
        self.assertEqual(parsed["content_markdown"], "Intro paragraph")

    def test_parses_fenced_json(self) -> None:
        raw = """```json
{
  "title": "Fenced Title",
  "article_markdown": "Body",
  "hero_image_prompt": "hero shot",
  "detail_image_prompt": "detail shot",
  "seo_title": "Fenced SEO",
  "meta_description": "Fenced meta",
  "focus_keyword": "fenced focus"
}
```"""
        parsed = parse_article_response(raw)
        self.assertEqual(parsed["title"], "Fenced Title")
        self.assertEqual(parsed["hero_image_prompt"], "hero shot")
        self.assertEqual(parsed["content_markdown"], "Body")

    def test_parses_embedded_json(self) -> None:
        raw = (
            "Here is your result:\n"
            '{"title":"Embedded","article_markdown":"Body","hero_image_prompt":"hero",'
            '"detail_image_prompt":"detail","seo_title":"SEO Embedded",'
            '"meta_description":"Meta Embedded","focus_keyword":"embedded focus"}\n'
            "Thanks."
        )
        parsed = parse_article_response(raw)
        self.assertEqual(parsed["title"], "Embedded")

    def test_raises_for_missing_key(self) -> None:
        raw = (
            '{"title":"Missing","article_markdown":"Body","hero_image_prompt":"hero",'
            '"detail_image_prompt":"detail","seo_title":"SEO","meta_description":"Meta"}'
        )
        with self.assertRaises(GenerationError):
            parse_article_response(raw)

    def test_parses_clean_vibe_json(self) -> None:
        raw = '{"vibes":["Dark Desk Setup Blueprint","Warm Task Lighting Layering"]}'
        parsed = parse_vibe_response(raw, max_count=12)
        self.assertEqual(parsed, ["Dark Desk Setup Blueprint", "Warm Task Lighting Layering"])

    def test_parses_fenced_vibe_json(self) -> None:
        raw = """```json
{
  "vibes": ["Cozy Crochet Evening Basket", "Tiny Yarn Corner Makeover"]
}
```"""
        parsed = parse_vibe_response(raw, max_count=12)
        self.assertEqual(parsed[0], "Cozy Crochet Evening Basket")

    def test_parses_embedded_vibe_json(self) -> None:
        raw = (
            "Generated list:\n"
            '{"vibes":["Cable Management for Dark Desk Rigs","Ambient Keyboard Glow Guide"]}\n'
            "done"
        )
        parsed = parse_vibe_response(raw, max_count=12)
        self.assertIn("Ambient Keyboard Glow Guide", parsed)

    def test_raises_when_vibes_key_missing(self) -> None:
        raw = '{"topics":["A","B"]}'
        with self.assertRaises(GenerationError):
            parse_vibe_response(raw, max_count=12)

    def test_vibe_validation_dedup_and_max_count(self) -> None:
        raw = (
            '{"vibes":["A", "Dark Mode Desk Setup Essentials", '
            '"dark mode desk setup essentials", 12, "", '
            '"Cozy Yarn Basket Organization", '
            '"Soft Lamp Pairing for Evening Focus"]}'
        )
        parsed = parse_vibe_response(raw, max_count=2)
        self.assertEqual(
            parsed,
            ["Dark Mode Desk Setup Essentials", "Cozy Yarn Basket Organization"],
        )


if __name__ == "__main__":
    unittest.main()
