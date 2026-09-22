"""Verify Pages staging excludes videos, gallery code, and gallery-only catalogs."""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("build_site_under_test", SCRIPTS / "build_site.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "DESTINATION", tmp_path / "_site")
    for name in (*build.PUBLIC_FILES, *build.GALLERY_PAGES):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"synthetic {name}\n")
    return tmp_path, tmp_path / "_site"


def contents(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def test_blog_build_needs_no_local_media_or_gallery_runtime(workspace):
    root, destination = workspace
    before = contents(root)
    build.main()
    assert contents(destination) == before
    assert all((root / name).read_bytes() == payload for name, payload in before.items())
    assert not (destination / "media").exists()
    assert len(list((destination / "gallery").rglob("index.html"))) == 6


def test_gallery_media_and_private_files_never_enter_pages(workspace):
    root, destination = workspace
    expected = contents(root)
    for name in ("app.js", "styles.css", "gallery/gallery.css", "gallery/new/index.html",
                 "data/gallery.json", "data/task-demos.json", "data/export-report.json",
                 "data/episodes.csv", "media/libero/episode.mp4", "media/robotwin/poster.jpg",
                 "media/demos/demo.mp4", "assets/unpublished.png", ".env", "README.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("gallery-only or private data")
    destination.mkdir()
    (destination / "old-media.mp4").write_bytes(b"stale media from previous deployment")
    before = {name: payload for name, payload in contents(root).items() if not name.startswith("_site/")}
    build.main()
    assert contents(destination) == expected
    assert {name: payload for name, payload in contents(root).items() if not name.startswith("_site/")} == before
    assert not any(path.suffix in (".mp4", ".jpg") for path in destination.rglob("*"))


@pytest.mark.parametrize("missing", ["gallery-hosting.json", "gallery-redirect.js", "blog.js",
                                     "data/robotwin-alignment-summary.json", "gallery/robotwin/index.html"])
def test_missing_required_asset_preserves_previous_build(workspace, missing):
    root, destination = workspace
    (root / missing).unlink()
    destination.mkdir()
    (destination / "previous.html").write_text("previous successful build")
    with pytest.raises(SystemExit, match="Missing required public file"):
        build.main()
    assert contents(destination) == {"previous.html": b"previous successful build"}


def test_symlinked_public_asset_is_rejected(workspace):
    root, destination = workspace
    asset = root / "assets/favicon.svg"
    asset.unlink()
    secret = root / "private.txt"
    secret.write_text("private")
    asset.symlink_to(secret)
    with pytest.raises(SystemExit, match="Symlinks are not public assets"):
        build.main()
    assert not destination.exists()


def test_symlinked_destination_is_not_followed(workspace):
    root, destination = workspace
    target = root / "keep"
    target.mkdir()
    (target / "sentinel.txt").write_text("untouched")
    destination.symlink_to(target, target_is_directory=True)
    with pytest.raises(SystemExit, match="Refusing a symlink"):
        build.main()
    assert (target / "sentinel.txt").read_text() == "untouched"
