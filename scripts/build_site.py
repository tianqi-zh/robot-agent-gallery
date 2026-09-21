#!/usr/bin/env python3
"""Stage only public gallery assets for GitHub Pages, without a JS build step."""
from pathlib import Path
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_site"
PUBLIC_FILES = ("index.html", "blog.js", "blog.css", "app.js", "styles.css", ".nojekyll", "METHODOLOGY.md", "TRAINING_DEMOS.md", "LIBERO_ALIGNMENT.md")
PUBLIC_DIRECTORIES = ("assets", "data", "media", "gallery")
GALLERY_PAGES = ("gallery/index.html", *(f"gallery/{name}/index.html" for name in ("libero", "robotwin", "robocasa", "robodojo")))
GALLERY_ALIAS = "gallery/robotwin_nvidia10/index.html"
GALLERY_SCRIPT = re.compile(r'<script src="(?:\.\./)+app\.js" defer></script>')


def main():
    gallery = json.loads((ROOT / "data/gallery.json").read_text())
    external_videos = set()
    for benchmark in gallery["benchmarks"]:
        if benchmark["id"] == "robocasa":
            from release_media import RELEASE_HOSTING, remote_video_url
            if benchmark.get("videoHosting") != RELEASE_HOSTING:
                raise SystemExit("RoboCasa365 requires its declared release video hosting")
            for task in benchmark["tasks"]:
                for episode in task["episodes"]:
                    if (episode.get("remoteVideo") != remote_video_url(episode["id"])
                            or episode["video"] != f"media/robocasa/{episode['id']}.mp4"):
                        raise SystemExit("Invalid release video mapping")
                    external_videos.add(episode["video"])
    for name in (*PUBLIC_FILES, *GALLERY_PAGES, GALLERY_ALIAS, "gallery/gallery.css"):
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing required public file: {name}")
    for name in ("data", "media"):
        if not (ROOT / name).is_dir():
            raise SystemExit(f"Missing required public directory: {name}")
    for name in GALLERY_PAGES:
        if len(GALLERY_SCRIPT.findall((ROOT / name).read_text())) != 1:
            raise SystemExit(f"Cannot configure gallery runtime in {name}")
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
            def exclude_external(directory, filenames):
                return [filename for filename in filenames
                        if (Path(directory) / filename).relative_to(ROOT).as_posix() in external_videos]
            shutil.copytree(source, DESTINATION / name, ignore=exclude_external)
    if external_videos:
        for name in GALLERY_PAGES:
            page = DESTINATION / name
            html = page.read_text()
            page.write_text(GALLERY_SCRIPT.sub(lambda match: '<script>window.GALLERY_REMOTE_VIDEOS = true;</script>\n  ' + match[0], html))
    files = [path for path in DESTINATION.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    if size >= 1_500_000_000:
        raise SystemExit(f"Published site exceeds the 1.5 GB safety margin: {size} bytes")
    print(f"Staged {len(files)} files, {size / 1_000_000:.1f} MB, in _site/; {len(external_videos)} videos use release assets")


if __name__ == "__main__":
    main()
