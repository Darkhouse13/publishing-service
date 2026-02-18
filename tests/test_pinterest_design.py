import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from pinterest_design import PIN_HEIGHT, PIN_WIDTH, generate_pinterest_image, resolve_font_path
from pinterest_models import BrainOutput


class PinterestDesignTests(unittest.TestCase):
    def test_resolve_font_path_uses_blog_mapping_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_font = Path(tmp_dir) / "font.ttf"
            fake_font.write_bytes(b"font")
            env_value = (
                '{"THE_SUNDAY_PATIO":"'
                + str(fake_font).replace("\\", "\\\\")
                + '"}'
            )
            with patch.dict(environ, {"PINTEREST_FONT_MAP_JSON": env_value}, clear=False):
                resolved = resolve_font_path("THE_SUNDAY_PATIO")
            self.assertEqual(resolved, fake_font)

    def test_generate_pinterest_image_outputs_1000x1500(self) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "base.jpg"
            Image.new("RGB", (1800, 1200), color=(120, 120, 120)).save(base)
            output_dir = Path(tmp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch("pinterest_design._build_base_image", return_value=base):
                output = generate_pinterest_image(
                    brain_output=BrainOutput(
                        primary_keyword="patio setup",
                        image_generation_prompt="Photorealistic patio scene",
                        pin_text_overlay="7 Patio Setup Ideas",
                        pin_title="7 Patio Setup Ideas for Small Backyards",
                        pin_description="Practical patio setup ideas.",
                        cluster_label="Outdoor Living",
                    ),
                    blog_suffix="THE_SUNDAY_PATIO",
                    run_dir=output_dir,
                )

            with Image.open(output) as image:
                self.assertEqual(image.size, (PIN_WIDTH, PIN_HEIGHT))


if __name__ == "__main__":
    unittest.main()
