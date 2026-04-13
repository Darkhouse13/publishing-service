from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_THEME = "yourmidnightdesk"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "theme" / f"{DEFAULT_THEME}.zip"
REQUIRED_FILES = (
    "style.css",
    "functions.php",
    "header.php",
    "footer.php",
    "front-page.php",
    "index.php",
    "archive.php",
    "single.php",
    "page.php",
    "search.php",
    "404.php",
    "sidebar.php",
    "inc/core.php",
    "inc/customizer.php",
    "inc/meta.php",
    "assets/js/theme.js",
)
IGNORED_NAMES = {"Thumbs.db", ".DS_Store"}


def resolve_theme_folder(theme_slug: str) -> Path:
    return REPO_ROOT / "assets" / "theme" / theme_slug


def validate_theme(theme_folder: Path) -> list[Path]:
    missing: list[Path] = []
    for relative_path in REQUIRED_FILES:
        candidate = theme_folder / relative_path
        if not candidate.is_file():
            missing.append(candidate)
    return missing


def iter_theme_files(theme_folder: Path) -> list[Path]:
    files: list[Path] = []
    for candidate in sorted(theme_folder.rglob("*")):
        if not candidate.is_file():
            continue
        if candidate.name in IGNORED_NAMES:
            continue
        files.append(candidate)
    return files


def build_zip(theme_slug: str, output_zip: Path) -> Path:
    theme_folder = resolve_theme_folder(theme_slug)
    if not theme_folder.is_dir():
        raise FileNotFoundError(f"Theme folder not found: {theme_folder}")

    missing_files = validate_theme(theme_folder)
    if missing_files:
        formatted = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(f"Missing required theme files:\n{formatted}")

    theme_files = iter_theme_files(theme_folder)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in theme_files:
            relative_path = source.relative_to(theme_folder).as_posix()
            archive.write(source, arcname=(Path(theme_slug) / relative_path).as_posix())

    return output_zip


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an uploadable WordPress theme zip.")
    parser.add_argument(
        "--theme",
        default=DEFAULT_THEME,
        help=f"Theme folder slug under assets/theme (default: {DEFAULT_THEME}).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Zip output path (default: {DEFAULT_OUTPUT}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_zip = Path(args.output).expanduser()
    if not output_zip.is_absolute():
        output_zip = (REPO_ROOT / output_zip).resolve()

    try:
        built_path = build_zip(theme_slug=str(args.theme).strip(), output_zip=output_zip)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Created: {built_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
