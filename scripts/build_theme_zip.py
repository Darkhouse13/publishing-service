from __future__ import annotations

import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
THEME_FOLDER = REPO_ROOT / "assets" / "theme" / "the-sunday-patio"
OUTPUT_ZIP = REPO_ROOT / "artifacts" / "theme" / "the-sunday-patio.zip"
REQUIRED_FILES = (
    "style.css",
    "functions.php",
    "header.php",
    "footer.php",
    "sidebar.php",
    "index.php",
    "archive.php",
    "single.php",
    "page.php",
)


def validate_files() -> list[Path]:
    missing: list[Path] = []
    for filename in REQUIRED_FILES:
        candidate = THEME_FOLDER / filename
        if not candidate.is_file():
            missing.append(candidate)
    return missing


def build_zip() -> None:
    missing_files = validate_files()
    if missing_files:
        print("Missing required theme files:", file=sys.stderr)
        for missing in missing_files:
            print(f"- {missing}", file=sys.stderr)
        raise SystemExit(1)

    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in REQUIRED_FILES:
            source = THEME_FOLDER / filename
            arcname = (Path("the-sunday-patio") / filename).as_posix()
            archive.write(source, arcname)

    print(f"Created: {OUTPUT_ZIP.resolve()}")
    print("Included files:")
    for filename in REQUIRED_FILES:
        print(f"- {THEME_FOLDER.as_posix()}/{filename}")


def main() -> None:
    build_zip()


if __name__ == "__main__":
    main()
