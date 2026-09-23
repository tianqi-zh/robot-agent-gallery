#!/usr/bin/env python3
"""Stage the GitHub Pages essay and links to the Hugging Face video gallery."""
from pathlib import Path
import shutil
import tempfile

from blog_validation import ValidationError, local_asset, read_json, require

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_site"
PUBLIC_FILES = (
    "index.html", "blog.js", "blog.css", ".nojekyll",
    "gallery-hosting.json", "gallery-hosting.js", "gallery-redirect.js",
    "METHODOLOGY.md", "LIBERO_ALIGNMENT.md", "assets/favicon.svg",
    "data/libero-alignment.json", "data/libero-alignment-episodes.csv",
    "data/libero-blog-media.json", "data/libero-human-review.json",
    "data/robotwin-alignment-summary.json", "data/robotwin-instruction-examples.json",
    "media/blog/overview/blog-showcase-v2.mp4", "media/blog/overview/blog-showcase-v2.jpg",
)
GALLERY_PAGES = (
    "gallery/index.html",
    *(f"gallery/{name}/index.html" for name in (
        "libero", "robotwin", "robotwin_nvidia10", "robocasa", "robodojo"
    )),
)


def blog_media_files():
    """Return only the videos and posters declared by the essay's evidence data."""
    libero = read_json(ROOT / "data/libero-blog-media.json")
    robotwin = read_json(ROOT / "data/robotwin-alignment-summary.json")
    require(isinstance(libero, dict) and isinstance(libero.get("clips"), dict)
            and libero["clips"], "Missing LIBERO blog clips")
    require(isinstance(robotwin, dict) and isinstance(robotwin.get("cases"), list)
            and robotwin["cases"], "Missing RoboTwin blog cases")
    assets = set()
    for clip in (*libero["clips"].values(), *robotwin["cases"]):
        require(isinstance(clip, dict), "Invalid blog clip")
        for kind, suffix in (("video", ".mp4"), ("poster", ".jpg")):
            relative = clip.get(kind)
            require(isinstance(relative, str) and relative.startswith("media/")
                    and relative.endswith(suffix), f"Blog {kind} must be a media/ {suffix} asset")
            local_asset(ROOT, relative, f"blog {kind}")
            assets.add(relative)
    return tuple(sorted(assets))


def main():
    # Copy the essay's media allowlist; the full gallery and its catalog stay in HF.
    # Validate every source before replacing an existing successful build.
    for name in (*PUBLIC_FILES, *GALLERY_PAGES):
        source = ROOT / name
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent != ROOT):
            raise SystemExit(f"Symlinks are not public assets: {name}")
        if not source.is_file():
            raise SystemExit(f"Missing required public file: {name}")
    try:
        media_files = blog_media_files()
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc
    if DESTINATION.is_symlink():
        raise SystemExit("Refusing a symlink at the build destination")
    with tempfile.TemporaryDirectory(prefix=".blog-build-", dir=ROOT) as temporary:
        stage = Path(temporary) / "site"
        stage.mkdir()
        for name in (*PUBLIC_FILES, *GALLERY_PAGES, *media_files):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        files = [path for path in stage.rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in files)
        if size >= 50_000_000:
            raise SystemExit(f"Blog exceeds the 50 MB safety margin: {size} bytes")
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        stage.rename(DESTINATION)
    print(f"Staged {len(files)} blog files, including {len(media_files)} example media assets, "
          f"{size / 1_000_000:.1f} MB, in _site/; the full video gallery is hosted on Hugging Face")


if __name__ == "__main__":
    main()
