#!/usr/bin/env python3
"""Stage the GitHub Pages essay and links to the Hugging Face video gallery."""
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_site"
PUBLIC_FILES = (
    "index.html", "blog.js", "blog.css", ".nojekyll",
    "gallery-hosting.json", "gallery-hosting.js", "gallery-redirect.js",
    "METHODOLOGY.md", "LIBERO_ALIGNMENT.md", "assets/favicon.svg",
    "data/libero-alignment.json", "data/libero-alignment-episodes.csv",
    "data/libero-blog-media.json", "data/libero-human-review.json",
    "data/robotwin-alignment-summary.json",
)
GALLERY_PAGES = (
    "gallery/index.html",
    *(f"gallery/{name}/index.html" for name in (
        "libero", "robotwin", "robotwin_nvidia10", "robocasa", "robodojo"
    )),
)


def main():
    # An explicit allowlist keeps gallery runtimes, catalogs, and all media in HF.
    # Validate every source before replacing an existing successful build.
    for name in (*PUBLIC_FILES, *GALLERY_PAGES):
        source = ROOT / name
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent != ROOT):
            raise SystemExit(f"Symlinks are not public assets: {name}")
        if not source.is_file():
            raise SystemExit(f"Missing required public file: {name}")
    if DESTINATION.is_symlink():
        raise SystemExit("Refusing a symlink at the build destination")
    with tempfile.TemporaryDirectory(prefix=".blog-build-", dir=ROOT) as temporary:
        stage = Path(temporary) / "site"
        stage.mkdir()
        for name in (*PUBLIC_FILES, *GALLERY_PAGES):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        files = [path for path in stage.rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in files)
        if size >= 25_000_000:
            raise SystemExit(f"Blog exceeds the 25 MB safety margin: {size} bytes")
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        stage.rename(DESTINATION)
    print(f"Staged {len(files)} blog files, {size / 1_000_000:.1f} MB, in _site/; video gallery and media are hosted on Hugging Face")


if __name__ == "__main__":
    main()
