"""Package the add-on as mieru.ankiaddon, the zip format Anki installs from a file."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "mieru"
OUTPUT = ROOT / "mieru.ankiaddon"
# meta.json holds the developer's own settings (such as their Pixabay key) once Anki
# has run the add-on from a symlinked checkout.
EXCLUDED = {"__pycache__", "meta.json"}


def main() -> None:
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            relative = path.relative_to(SOURCE)
            if path.is_file() and not EXCLUDED.intersection(relative.parts):
                archive.write(path, relative.as_posix())
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
