import json
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from pinterest_design import (
    ImageDesignError,
    PIN_HEIGHT,
    PIN_WIDTH,
    generate_pinterest_image,
    resolve_font_path,
)
from pinterest_models import BrainOutput


class PinterestDesignTests(unittest.TestCase):
    @staticmethod
    def _brain_output(title: str = "7 Patio Setup Ideas for Small Backyards") -> BrainOutput:
        return BrainOutput(
            primary_keyword="patio setup",
            image_generation_prompt="Photorealistic patio scene",
            pin_text_overlay="7 Patio Setup Ideas",
            pin_title=title,
            pin_description="Practical patio setup ideas.",
            cluster_label="Outdoor Living",
        )

    def test_resolve_font_path_uses_blog_mapping_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_font = Path(tmp_dir) / "font.ttf"
            fake_font.write_bytes(b"font")
            env_value = (
                '{"THE_SUNDAY_PATIO":"'
                + str(fake_font).replace("\\", "\\\\")
                + '"}'
            )
            with patch.dict(environ, {"PINTEREST_FONT_MAP_JSON": env_value}, clear=False), patch(
                "pinterest_design._is_scalable_font_path",
                return_value=True,
            ):
                resolved = resolve_font_path("THE_SUNDAY_PATIO")
            self.assertEqual(resolved, fake_font)

    def test_resolve_font_path_uses_os_fallback_when_env_map_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fallback_font = Path(tmp_dir) / "fallback.ttf"
            fallback_font.write_bytes(b"font")
            with patch("pinterest_design._load_font_map", return_value={}), patch(
                "pinterest_design._pillow_packaged_fallback_font_path",
                return_value=None,
            ), patch(
                "pinterest_design._iter_os_font_candidates",
                return_value=[(fallback_font, "os_windows")],
            ), patch(
                "pinterest_design._is_scalable_font_path",
                return_value=True,
            ):
                resolved = resolve_font_path("THE_SUNDAY_PATIO")
            self.assertEqual(resolved, fallback_font)

    def test_generate_pinterest_image_center_strip_metadata_and_dimensions(self) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "base.jpg"
            Image.new("RGB", (1800, 1200), color=(120, 120, 120)).save(base)
            output_dir = Path(tmp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch("pinterest_design._build_base_image", return_value=base) as mock_build, patch.dict(
                environ,
                {
                    "PINTEREST_PIN_TEMPLATE_MODE": "center_strip",
                    "PINTEREST_PIN_TEMPLATE_FAILURE_POLICY": "template_or_none",
                },
                clear=False,
            ):
                output = generate_pinterest_image(
                    brain_output=self._brain_output(),
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    run_dir=output_dir,
                )

            self.assertEqual(mock_build.call_count, 1)
            with Image.open(output) as image:
                self.assertEqual(image.size, (PIN_WIDTH, PIN_HEIGHT))

            metadata = json.loads((output_dir / "pin_design_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["dimensions"], {"width": PIN_WIDTH, "height": PIN_HEIGHT})
            self.assertEqual(metadata["template_mode"], "center_strip")
            self.assertEqual(metadata["background_composition"], "continuous_base")
            self.assertTrue(metadata["text_rendered"])
            self.assertEqual(metadata["headline_text_source"], "pin_title")
            self.assertTrue(str(metadata["headline_text_rendered"]).strip())
            self.assertTrue(str(metadata["byline_text_rendered"]).strip())

    def test_generate_pinterest_image_long_title_is_truncated_but_rendered(self) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "base.jpg"
            Image.new("RGB", (1800, 1200), color=(150, 150, 150)).save(base)
            output_dir = Path(tmp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)

            long_title = (
                "This is a very long pinterest headline title that should be cropped to fit the center strip "
                "without breaking readability or layout guarantees"
            )
            with patch("pinterest_design._build_base_image", return_value=base), patch.dict(
                environ,
                {
                    "PINTEREST_PIN_TEMPLATE_MODE": "center_strip",
                    "PINTEREST_PIN_TEMPLATE_FAILURE_POLICY": "template_or_none",
                },
                clear=False,
            ):
                generate_pinterest_image(
                    brain_output=self._brain_output(long_title),
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    run_dir=output_dir,
                )

            metadata = json.loads((output_dir / "pin_design_metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(metadata["text_rendered"])
            lines = str(metadata["headline_text_rendered"]).splitlines()
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(any(line.strip() for line in lines))

    def test_generate_pinterest_image_missing_font_uses_no_text_fallback_when_policy_template_or_none(self) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "base.jpg"
            Image.new("RGB", (1800, 1200), color=(120, 120, 120)).save(base)
            output_dir = Path(tmp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch("pinterest_design._build_base_image", return_value=base), patch(
                "pinterest_design._resolve_font_path_with_source",
                return_value=(None, "missing", ["env:default:C:/missing.ttf"]),
            ), patch.dict(
                environ,
                {
                    "PINTEREST_PIN_TEMPLATE_MODE": "center_strip",
                    "PINTEREST_PIN_TEMPLATE_FAILURE_POLICY": "template_or_none",
                },
                clear=False,
            ):
                output = generate_pinterest_image(
                    brain_output=self._brain_output(),
                    blog_suffix="THE_SUNDAY_PATIO",
                    blog_name="The Sunday Patio",
                    run_dir=output_dir,
                )

            with Image.open(output) as image:
                self.assertEqual(image.size, (PIN_WIDTH, PIN_HEIGHT))
            metadata = json.loads((output_dir / "pin_design_metadata.json").read_text(encoding="utf-8"))
            self.assertFalse(metadata["text_rendered"])
            self.assertIn("No scalable font", str(metadata["text_fallback_reason"]))

    def test_generate_pinterest_image_missing_font_raises_when_policy_fail(self) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "base.jpg"
            Image.new("RGB", (1800, 1200), color=(120, 120, 120)).save(base)
            output_dir = Path(tmp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch("pinterest_design._build_base_image", return_value=base), patch(
                "pinterest_design._resolve_font_path_with_source",
                return_value=(None, "missing", ["env:default:C:/missing.ttf"]),
            ), patch.dict(
                environ,
                {
                    "PINTEREST_PIN_TEMPLATE_MODE": "center_strip",
                    "PINTEREST_PIN_TEMPLATE_FAILURE_POLICY": "fail",
                },
                clear=False,
            ):
                with self.assertRaises(ImageDesignError) as exc:
                    generate_pinterest_image(
                        brain_output=self._brain_output(),
                        blog_suffix="THE_SUNDAY_PATIO",
                        blog_name="The Sunday Patio",
                        run_dir=output_dir,
                    )
        self.assertIn("No scalable font", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
