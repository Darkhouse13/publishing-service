import json
import re
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import Mock, patch

import uploader


class UploaderFlowTests(unittest.TestCase):
    def test_strip_duplicate_leading_h1_atx(self) -> None:
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown="# My Draft\n\nParagraph one.\n",
            title="My Draft",
        )
        self.assertTrue(stripped)
        self.assertEqual(sanitized, "Paragraph one.\n")

    def test_strip_duplicate_leading_h1_setext(self) -> None:
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown="My Draft\n===\n\nParagraph one.\n",
            title="My Draft",
        )
        self.assertTrue(stripped)
        self.assertEqual(sanitized, "Paragraph one.\n")

    def test_strip_duplicate_leading_h1_preserves_non_matching_h1(self) -> None:
        markdown = "# Another Heading\n\nParagraph one.\n"
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown=markdown,
            title="My Draft",
        )
        self.assertFalse(stripped)
        self.assertEqual(sanitized, markdown)

    def test_strip_duplicate_leading_h1_preserves_h2(self) -> None:
        markdown = "## My Draft\n\nParagraph one.\n"
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown=markdown,
            title="My Draft",
        )
        self.assertFalse(stripped)
        self.assertEqual(sanitized, markdown)

    def test_strip_duplicate_leading_h1_matches_normalized_text(self) -> None:
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown="# My  Draft: What's New?\n\nParagraph one.\n",
            title="My Draft Whats New",
        )
        self.assertTrue(stripped)
        self.assertEqual(sanitized, "Paragraph one.\n")

    def test_strip_duplicate_leading_h1_leaves_markdown_without_heading(self) -> None:
        markdown = "Paragraph one.\n\nParagraph two.\n"
        sanitized, stripped = uploader.strip_duplicate_leading_h1(
            content_markdown=markdown,
            title="My Draft",
        )
        self.assertFalse(stripped)
        self.assertEqual(sanitized, markdown)

    def test_markdown_to_html(self) -> None:
        try:
            html = uploader.markdown_to_html(
                "### Step 1\n\n**Tools:**\n* Shovel\n* Tape measure\n\nParagraph body."
            )
        except uploader.WordPressUploadError as exc:
            self.skipTest(str(exc))

        self.assertIn("<h3>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<li>", html)
        self.assertIn("<p>Paragraph body.</p>", html)

    def test_inject_detail_image_after_first_paragraph(self) -> None:
        content_html = "<p>Intro paragraph.</p><p>Second paragraph.</p>"
        updated = uploader.inject_detail_image_after_first_paragraph(
            content_html=content_html,
            detail_image_url="https://example.com/detail.jpg",
            alt_text="detail",
        )

        intro_index = updated.find("</p>")
        detail_index = updated.find("https://example.com/detail.jpg")
        self.assertGreater(detail_index, intro_index)
        self.assertIn("midnight-engine-detail", updated)

    def test_publish_post_payload_correctness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hero_path = Path(tmp_dir) / "hero.jpg"
            detail_path = Path(tmp_dir) / "detail.jpg"
            hero_path.write_bytes(b"hero-bytes")
            detail_path.write_bytes(b"detail-bytes")

            mock_post_response = Mock()
            mock_post_response.status_code = 201
            mock_post_response.json.return_value = {
                "id": 321,
                "link": "https://example.com/?p=321",
                "status": "draft",
                "slug": "my-draft",
            }
            mock_post_response.text = '{"id":321}'

            with patch(
                "uploader._get_wp_config",
                return_value=("https://example.com", "wp_user", "wp_key"),
            ), patch(
                "uploader.upload_media",
                side_effect=[
                    {"id": 101, "source_url": "https://example.com/uploads/hero.jpg"},
                    {"id": 202, "source_url": "https://example.com/uploads/detail.jpg"},
                ],
            ) as mock_upload_media, patch(
                "uploader.inject_cross_blog_backlinks",
                return_value=("Paragraph one.\n\nParagraph two.", []),
            ), patch(
                "uploader.ensure_required_markdown_links",
                return_value=("Paragraph one.\n\nParagraph two.", []),
            ), patch(
                "uploader.requests.post", return_value=mock_post_response
            ) as mock_requests_post:
                result = uploader.publish_post(
                    title="My Draft",
                    content_markdown="Paragraph one.\n\nParagraph two.",
                    hero_path=hero_path,
                    detail_path=detail_path,
                    target_suffix="THE_SUNDAY_PATIO",
                    focus_keyword="patio gardening",
                    meta_description="A practical seasonal patio gardening guide.",
                    seo_title="Patio Gardening Guide for Every Season",
                    status="draft",
                    category_id=7,
                )

            self.assertEqual(mock_upload_media.call_count, 2)
            self.assertEqual(mock_requests_post.call_count, 1)
            self.assertEqual(
                mock_upload_media.call_args_list[0].kwargs.get("target_suffix"),
                "THE_SUNDAY_PATIO",
            )
            self.assertEqual(
                mock_upload_media.call_args_list[1].kwargs.get("target_suffix"),
                "THE_SUNDAY_PATIO",
            )
            self.assertIn(
                "patio gardening",
                str(mock_upload_media.call_args_list[0].kwargs.get("alt_text", "")).casefold(),
            )
            self.assertIn(
                "patio gardening",
                str(mock_upload_media.call_args_list[1].kwargs.get("alt_text", "")).casefold(),
            )

            request_args, request_kwargs = mock_requests_post.call_args
            self.assertEqual(request_args[0], "https://example.com/wp-json/wp/v2/posts")

            payload = request_kwargs["json"]
            self.assertEqual(payload["title"], "My Draft")
            self.assertEqual(payload["slug"], uploader.build_post_slug("patio gardening", "My Draft"))
            self.assertEqual(payload["featured_media"], 101)
            self.assertEqual(payload["status"], "draft")
            self.assertEqual(payload["categories"], [7])
            self.assertEqual(
                payload["meta"],
                {
                    "rank_math_title": "Patio Gardening Guide for Every Season",
                    "rank_math_description": "A practical seasonal patio gardening guide.",
                    "rank_math_focus_keyword": "patio gardening",
                },
            )
            self.assertIn("https://example.com/uploads/detail.jpg", payload["content"])
            self.assertIn('alt="patio gardening - My Draft detail image"', payload["content"])

            self.assertEqual(result["post_id"], 321)
            self.assertEqual(result["post_slug"], "my-draft")
            self.assertEqual(result["hero_media_id"], 101)
            self.assertEqual(result["detail_media_id"], 202)
            self.assertEqual(result["category_ids"], [7])
            self.assertIn("publish_warnings", result)

    def test_publish_post_strips_duplicate_leading_h1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hero_path = Path(tmp_dir) / "hero.jpg"
            detail_path = Path(tmp_dir) / "detail.jpg"
            hero_path.write_bytes(b"hero-bytes")
            detail_path.write_bytes(b"detail-bytes")

            mock_post_response = Mock()
            mock_post_response.status_code = 201
            mock_post_response.json.return_value = {
                "id": 444,
                "link": "https://example.com/?p=444",
                "status": "draft",
                "slug": "my-draft",
            }
            mock_post_response.text = '{"id":444}'

            with patch(
                "uploader._get_wp_config",
                return_value=("https://example.com", "wp_user", "wp_key"),
            ), patch(
                "uploader.upload_media",
                side_effect=[
                    {"id": 101, "source_url": "https://example.com/uploads/hero.jpg"},
                    {"id": 202, "source_url": "https://example.com/uploads/detail.jpg"},
                ],
            ), patch(
                "uploader.inject_cross_blog_backlinks",
                return_value=("Paragraph one.", []),
            ), patch(
                "uploader.ensure_required_markdown_links",
                return_value=("Paragraph one.", []),
            ), patch("uploader.requests.post", return_value=mock_post_response) as mock_requests_post:
                uploader.publish_post(
                    title="My Draft",
                    content_markdown="# My Draft\n\nParagraph one.",
                    hero_path=hero_path,
                    detail_path=detail_path,
                    target_suffix="THE_SUNDAY_PATIO",
                    focus_keyword="patio gardening",
                    meta_description="A practical seasonal patio gardening guide.",
                    seo_title="Patio Gardening Guide for Every Season",
                    status="draft",
                    category_id=7,
                )

            _, request_kwargs = mock_requests_post.call_args
            payload = request_kwargs["json"]
            self.assertNotIn("<h1", payload["content"])
            self.assertIn("<p>Paragraph one.</p>", payload["content"])

    def test_publish_post_returns_slug_fallback_when_api_slug_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hero_path = Path(tmp_dir) / "hero.jpg"
            detail_path = Path(tmp_dir) / "detail.jpg"
            hero_path.write_bytes(b"hero-bytes")
            detail_path.write_bytes(b"detail-bytes")

            mock_post_response = Mock()
            mock_post_response.status_code = 201
            mock_post_response.json.return_value = {
                "id": 555,
                "link": "https://example.com/?p=555",
                "status": "draft",
            }
            mock_post_response.text = '{"id":555}'

            with patch(
                "uploader._get_wp_config",
                return_value=("https://example.com", "wp_user", "wp_key"),
            ), patch(
                "uploader.upload_media",
                side_effect=[
                    {"id": 101, "source_url": "https://example.com/uploads/hero.jpg"},
                    {"id": 202, "source_url": "https://example.com/uploads/detail.jpg"},
                ],
            ), patch(
                "uploader.inject_cross_blog_backlinks",
                return_value=("Paragraph one.", []),
            ), patch(
                "uploader.ensure_required_markdown_links",
                return_value=("Paragraph one.", []),
            ), patch("uploader.requests.post", return_value=mock_post_response):
                result = uploader.publish_post(
                    title="My Draft",
                    content_markdown="Paragraph one.",
                    hero_path=hero_path,
                    detail_path=detail_path,
                    target_suffix="THE_SUNDAY_PATIO",
                    focus_keyword="patio gardening",
                    meta_description="A practical seasonal patio gardening guide.",
                    seo_title="Patio Gardening Guide for Every Season",
                    status="draft",
                    category_id=7,
                )

        self.assertEqual(result["post_slug"], "patio-gardening")

    def test_build_post_slug_uses_focus_keyword_only_and_hyphenates(self) -> None:
        slug = uploader.build_post_slug(
            focus_keyword="Low-maintenance perennial flowers for year-round color",
            title="Your Seasonal Gardening Plan for Lasting Backyard Color",
            max_length=60,
        )
        self.assertEqual(slug, "low-maintenance-perennial-flowers-for-year-round-color")
        self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_ensure_required_markdown_links_adds_internal_and_external_when_missing(self) -> None:
        sources_json = json.dumps(
            {
                "THE_SUNDAY_PATIO": [
                    {"anchor": "USDA planting guidance", "url": "https://planthardiness.ars.usda.gov/"}
                ]
            }
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch(
            "uploader.list_categories",
            return_value=[{"id": 7, "name": "Outdoor Living", "slug": "outdoor-living"}],
        ), patch.dict(environ, {uploader.SEO_EXTERNAL_SOURCES_ENV: sources_json}, clear=True):
            updated, warnings = uploader.ensure_required_markdown_links(
                article_markdown="A plain paragraph without links.",
                target_suffix="THE_SUNDAY_PATIO",
                category_id=7,
            )

        self.assertIn(
            "[Explore more on this topic](https://yoursundaypatio.com/category/outdoor-living/)",
            updated,
        )
        self.assertIn(
            "[USDA planting guidance](https://planthardiness.ars.usda.gov/)",
            updated,
        )
        self.assertEqual(warnings, [])

    def test_ensure_required_markdown_links_does_not_add_when_links_already_exist(self) -> None:
        markdown = (
            "Read [more here](https://yoursundaypatio.com/category/outdoor-living/) and "
            "see [this authority source](https://www.osha.gov/ergonomics)."
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ):
            updated, warnings = uploader.ensure_required_markdown_links(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
                category_id=7,
            )

        self.assertEqual(updated, markdown)
        self.assertEqual(warnings, [])

    def test_ensure_required_markdown_links_missing_external_sources_emits_warning(self) -> None:
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch(
            "uploader.list_categories",
            return_value=[{"id": 7, "name": "Outdoor Living", "slug": "outdoor-living"}],
        ), patch.dict(environ, {}, clear=True):
            updated, warnings = uploader.ensure_required_markdown_links(
                article_markdown="A plain paragraph without links.",
                target_suffix="THE_SUNDAY_PATIO",
                category_id=7,
            )

        self.assertIn(
            "[Explore more on this topic](https://yoursundaypatio.com/category/outdoor-living/)",
            updated,
        )
        self.assertTrue(any(uploader.SEO_EXTERNAL_SOURCES_ENV in warning for warning in warnings))

    def test_ensure_required_markdown_links_falls_back_to_homepage_when_category_missing(self) -> None:
        sources_json = json.dumps(
            {"default": [{"anchor": "official guidance", "url": "https://www.consumerreports.org/"}]}
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch(
            "uploader.list_categories",
            return_value=[{"id": 7, "name": "Outdoor Living", "slug": "outdoor-living"}],
        ), patch.dict(environ, {uploader.SEO_EXTERNAL_SOURCES_ENV: sources_json}, clear=True):
            updated, warnings = uploader.ensure_required_markdown_links(
                article_markdown="A plain paragraph without links.",
                target_suffix="THE_SUNDAY_PATIO",
                category_id=999,
            )

        self.assertIn("[Explore more on this topic](https://yoursundaypatio.com/)", updated)
        self.assertTrue(any("homepage as internal link fallback" in warning for warning in warnings))

    def test_ensure_required_markdown_links_invalid_external_sources_json_warns(self) -> None:
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch(
            "uploader.list_categories",
            return_value=[{"id": 7, "name": "Outdoor Living", "slug": "outdoor-living"}],
        ), patch.dict(environ, {uploader.SEO_EXTERNAL_SOURCES_ENV: "not-json"}, clear=True):
            _, warnings = uploader.ensure_required_markdown_links(
                article_markdown="A plain paragraph without links.",
                target_suffix="THE_SUNDAY_PATIO",
                category_id=7,
            )
        self.assertTrue(any("not valid JSON" in warning for warning in warnings))

    def test_inject_cross_blog_backlinks_replaces_first_instance_per_trigger(self) -> None:
        mapping_json = json.dumps(
            {"patio furniture": "https://yourmidnightdesk.com/patio-furniture-workspace"}
        )
        markdown = "Patio furniture ideas are practical. patio furniture styling also matters."
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertEqual(len(re.findall(r"\[.*?\]\(https://yourmidnightdesk.com/", updated)), 1)
        self.assertIn("patio furniture styling", updated.casefold())
        self.assertEqual(warnings, [])

    def test_inject_cross_blog_backlinks_appends_fallback_when_no_trigger_match(self) -> None:
        mapping_json = json.dumps(
            {
                "patio furniture": "https://theweekendfolio.com/patio-design",
                "dark mode desk setup": "https://yourmidnightdesk.com/dark-mode-guide",
            }
        )
        markdown = "A plain paragraph without configured trigger phrases."
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertIn(
            f"[{uploader.SISTER_BLOG_FALLBACK_ANCHOR}](https://theweekendfolio.com/patio-design)",
            updated,
        )
        self.assertEqual(warnings, [])

    def test_inject_cross_blog_backlinks_skips_fallback_if_sibling_link_already_present(self) -> None:
        mapping_json = json.dumps(
            {"patio furniture": "https://theweekendfolio.com/patio-design"}
        )
        markdown = "Already linked: [sister post](https://theweekendfolio.com/existing-post)."
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertEqual(updated, markdown)
        self.assertNotIn(uploader.SISTER_BLOG_FALLBACK_ANCHOR, updated)
        self.assertEqual(warnings, [])

    def test_inject_cross_blog_backlinks_warns_when_no_eligible_sibling_urls_for_guarantee(self) -> None:
        mapping_json = json.dumps(
            {"patio furniture": "https://yoursundaypatio.com/patio-furniture-layout-ideas"}
        )
        markdown = "A plain paragraph without links."
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertEqual(updated, markdown)
        self.assertTrue(any("current blog domain" in warning for warning in warnings))

    def test_inject_cross_blog_backlinks_skips_headings_code_and_existing_links(self) -> None:
        mapping_json = json.dumps(
            {
                "dark mode desk setup": "https://yourmidnightdesk.com/dark-mode-guide",
                "patio furniture": "https://theweekendfolio.com/patio-design",
            }
        )
        markdown = (
            "## Dark Mode Desk Setup Checklist\n\n"
            "```python\n"
            "print('dark mode desk setup')\n"
            "```\n\n"
            "Already linked [patio furniture](https://example.com/existing).\n\n"
            "A plain paragraph about patio furniture trends."
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, _ = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertIn("## Dark Mode Desk Setup Checklist", updated)
        self.assertIn("print('dark mode desk setup')", updated)
        self.assertIn("[patio furniture](https://example.com/existing)", updated)
        self.assertIn("[patio furniture](https://theweekendfolio.com/patio-design)", updated)

    def test_inject_cross_blog_backlinks_caps_to_three_and_skips_same_domain(self) -> None:
        mapping_json = json.dumps(
            {
                "phrase one": "https://theweekendfolio.com/a",
                "phrase two": "https://theweekendfolio.com/b",
                "phrase three": "https://theweekendfolio.com/c",
                "phrase four": "https://theweekendfolio.com/d",
                "same domain phrase": "https://yoursundaypatio.com/self",
            }
        )
        markdown = (
            "Phrase one appears here.\n\n"
            "Phrase two appears here.\n\n"
            "Phrase three appears here.\n\n"
            "Phrase four appears here.\n\n"
            "Same domain phrase appears here."
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        total_links = len(re.findall(r"\[[^\]]+\]\(https://theweekendfolio.com/", updated))
        self.assertEqual(total_links, 3)
        self.assertIn("same domain phrase appears here", updated.casefold())
        self.assertTrue(any("current blog domain" in warning for warning in warnings))

    def test_inject_cross_blog_backlinks_missing_map_emits_warning(self) -> None:
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown="A paragraph without links.",
                target_suffix="THE_SUNDAY_PATIO",
            )
        self.assertEqual(updated, "A paragraph without links.")
        self.assertTrue(any(uploader.CROSS_BLOG_LINK_MAP_ENV in warning for warning in warnings))

    def test_ensure_alt_text_has_focus_keyword_prefixes_when_missing(self) -> None:
        value = uploader._ensure_alt_text_has_focus_keyword(
            alt_text="My Draft hero image",
            focus_keyword="patio gardening",
        )
        self.assertEqual(value, "patio gardening - My Draft hero image")

    def test_cross_blog_backlinks_handle_split_style_plain_paragraphs(self) -> None:
        mapping_json = json.dumps(
            {"privacy screen outdoor": "https://theweekendfolio.com/privacy-screen-guide"}
        )
        markdown = (
            "Paragraph one stays plain and has no trigger phrase.\n\n"
            "This split paragraph still includes privacy screen outdoor for backlink detection."
        )
        with patch("uploader.load_dotenv"), patch(
            "uploader._get_wp_config",
            return_value=("https://yoursundaypatio.com", "user", "key"),
        ), patch.dict(environ, {uploader.CROSS_BLOG_LINK_MAP_ENV: mapping_json}, clear=True):
            updated, warnings = uploader.inject_cross_blog_backlinks(
                article_markdown=markdown,
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertIn(
            "[privacy screen outdoor](https://theweekendfolio.com/privacy-screen-guide)",
            updated.casefold(),
        )
        self.assertEqual(warnings, [])

    def test_ensure_category_uses_existing_case_insensitive_match(self) -> None:
        with patch(
            "uploader.list_categories",
            return_value=[
                {"id": 2, "name": "Outdoor Living", "slug": "outdoor-living"},
                {"id": 3, "name": "Curb Appeal", "slug": "curb-appeal"},
            ],
        ), patch("uploader.requests.post") as mock_post:
            category_id = uploader.ensure_category(
                "outdoor living",
                target_suffix="THE_SUNDAY_PATIO",
            )
        self.assertEqual(category_id, 2)
        mock_post.assert_not_called()

    def test_ensure_category_creates_when_missing(self) -> None:
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 99, "name": "Seasonal Care"}
        mock_response.text = '{"id":99}'

        with patch(
            "uploader.list_categories",
            return_value=[{"id": 2, "name": "Outdoor Living", "slug": "outdoor-living"}],
        ), patch(
            "uploader._get_wp_config",
            return_value=("https://example.com", "wp_user", "wp_key"),
        ), patch(
            "uploader.requests.post", return_value=mock_response
        ) as mock_post:
            category_id = uploader.ensure_category(
                "Seasonal Care",
                target_suffix="THE_SUNDAY_PATIO",
            )

        self.assertEqual(category_id, 99)
        request_args, request_kwargs = mock_post.call_args
        self.assertEqual(request_args[0], "https://example.com/wp-json/wp/v2/categories")
        self.assertEqual(request_kwargs["json"], {"name": "Seasonal Care"})

    def test_resolve_category_id_prefers_typed_new_name(self) -> None:
        with patch("uploader.ensure_category", return_value=44) as mock_ensure:
            category_id = uploader.resolve_category_id(
                selected_name="Outdoor Living",
                typed_new_name="Seasonal Care",
                target_suffix="THE_SUNDAY_PATIO",
            )
        self.assertEqual(category_id, 44)
        mock_ensure.assert_called_once_with(
            "Seasonal Care",
            target_suffix="THE_SUNDAY_PATIO",
        )

    def test_get_wp_config_requires_scoped_variables(self) -> None:
        with patch("uploader.load_dotenv"), patch.dict(environ, {}, clear=True):
            with self.assertRaises(uploader.WordPressUploadError) as exc:
                uploader._get_wp_config("THE_WEEKEND_FOLIO")
        self.assertIn("WP_URL_THE_WEEKEND_FOLIO", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
