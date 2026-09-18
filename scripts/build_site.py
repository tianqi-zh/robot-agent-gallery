#!/usr/bin/env python3
"""Stage only public gallery assets for GitHub Pages, without a JS build step."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_site"
PUBLIC_FILES = ("index.html", "app.js", "styles.css", ".nojekyll", "METHODOLOGY.md")
PUBLIC_DIRECTORIES = ("assets", "data", "media")


def main():
    for name in PUBLIC_FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing required public file: {name}")
    for name in ("data", "media"):
        if not (ROOT / name).is_dir():
            raise SystemExit(f"Missing required public directory: {name}")
    if DESTINATION.is_symlink():
        raise SystemExit("Refusing a symlink at the build destination")
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    DESTINATION.mkdir()
    for name in PUBLIC_FILES:
        shutil.copy2(ROOT / name, DESTINATION / name)
    for name in PUBLIC_DIRECTORIES:
        source = ROOT / name
        if source.exists():
            if any(path.is_symlink() for path in source.rglob("*")):
                raise SystemExit(f"Symlinks are not public assets: {name}")
            shutil.copytree(source, DESTINATION / name)
    files = [path for path in DESTINATION.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    if size >= 950_000_000:
        raise SystemExit(f"Published site exceeds the 950 MB safety margin: {size} bytes")
    print(f"Staged {len(files)} files, {size / 1_000_000:.1f} MB, in _site/")


if __name__ == "__main__":
    main()
