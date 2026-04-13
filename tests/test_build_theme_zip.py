import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import build_theme_zip


class BuildThemeZipTests(unittest.TestCase):
    def _create_theme(self, repo_root: Path, slug: str, *, include_all_required: bool = True) -> Path:
        theme_root = repo_root / "assets" / "theme" / slug
        for relative in build_theme_zip.REQUIRED_FILES:
            if not include_all_required and relative == "header.php":
                continue
            file_path = theme_root / relative
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"placeholder for {relative}", encoding="utf-8")

        extra_asset = theme_root / "assets" / "images" / "demo.txt"
        extra_asset.parent.mkdir(parents=True, exist_ok=True)
        extra_asset.write_text("demo asset", encoding="utf-8")
        return theme_root

    def test_build_zip_includes_recursive_assets_under_theme_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._create_theme(repo_root, "sample-theme")
            output_zip = repo_root / "artifacts" / "theme" / "sample-theme.zip"

            with patch.object(build_theme_zip, "REPO_ROOT", repo_root):
                built_path = build_theme_zip.build_zip("sample-theme", output_zip)

            self.assertEqual(built_path, output_zip)
            self.assertTrue(output_zip.exists())

            with zipfile.ZipFile(output_zip) as archive:
                names = set(archive.namelist())

            self.assertIn("sample-theme/style.css", names)
            self.assertIn("sample-theme/functions.php", names)
            self.assertIn("sample-theme/assets/js/theme.js", names)
            self.assertIn("sample-theme/assets/images/demo.txt", names)

    def test_build_zip_fails_when_required_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._create_theme(repo_root, "broken-theme", include_all_required=False)
            output_zip = repo_root / "artifacts" / "theme" / "broken-theme.zip"

            with patch.object(build_theme_zip, "REPO_ROOT", repo_root):
                with self.assertRaises(FileNotFoundError) as ctx:
                    build_theme_zip.build_zip("broken-theme", output_zip)

            self.assertIn("header.php", str(ctx.exception))

    def test_parse_args_accepts_theme_and_output(self) -> None:
        args = build_theme_zip.parse_args(["--theme", "custom-theme", "--output", "artifacts/theme/custom.zip"])
        self.assertEqual(args.theme, "custom-theme")
        self.assertEqual(args.output, "artifacts/theme/custom.zip")

    def test_main_uses_default_theme_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._create_theme(repo_root, build_theme_zip.DEFAULT_THEME)
            default_output = repo_root / "artifacts" / "theme" / f"{build_theme_zip.DEFAULT_THEME}.zip"

            with patch.object(build_theme_zip, "REPO_ROOT", repo_root), patch.object(
                build_theme_zip,
                "DEFAULT_OUTPUT",
                default_output,
            ):
                result = build_theme_zip.main([])

            self.assertEqual(result, 0)
            self.assertTrue(default_output.exists())
