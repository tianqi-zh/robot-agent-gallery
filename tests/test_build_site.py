"""Stage only the essay's examples, excluding the full gallery and other media."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
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
    clips = {"example": {"video": "media/libero/example.mp4", "poster": "media/libero/example.jpg"}}
    cases = [{"video": "media/robotwin/example.mp4", "poster": "media/robotwin/example.jpg"}]
    (tmp_path / "data/libero-blog-media.json").write_text(json.dumps({"clips": clips}))
    (tmp_path / "data/robotwin-alignment-summary.json").write_text(json.dumps({"cases": cases}))
    for clip in (*clips.values(), *cases):
        for name in clip.values():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"synthetic {name}".encode())
    return tmp_path, tmp_path / "_site"


def contents(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def test_blog_build_includes_declared_examples_without_gallery_runtime(workspace):
    root, destination = workspace
    before = contents(root)
    build.main()
    assert contents(destination) == before
    assert all((root / name).read_bytes() == payload for name, payload in before.items())
    assert len(list((destination / "media").rglob("*.mp4"))) == 3
    assert len(list((destination / "media").rglob("*.jpg"))) == 3
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
    assert not (destination / "media/libero/episode.mp4").exists()


def test_unreferenced_blog_clip_is_not_staged(workspace):
    root, destination = workspace
    manifest = root / "data/libero-blog-media.json"
    data = json.loads(manifest.read_text())
    data["clips"]["replacement"] = {"video": "media/libero/new.mp4", "poster": "media/libero/new.jpg"}
    del data["clips"]["example"]
    manifest.write_text(json.dumps(data))
    for name in data["clips"]["replacement"].values():
        (root / name).write_bytes(b"new example")
    build.main()
    assert (destination / "media/libero/new.mp4").read_bytes() == b"new example"
    assert (destination / "media/libero/new.jpg").is_file()
    assert not (destination / "media/libero/example.mp4").exists()
    assert not (destination / "media/libero/example.jpg").exists()
    assert (root / "media/libero/example.mp4").is_file()


def add_paired_robotwin_example(root):
    manifest = root / "data/robotwin-alignment-summary.json"
    data = json.loads(manifest.read_text())
    pair = {phase: {"video": f"media/blog/robotwin/pair-{phase}.mp4",
                    "poster": f"media/blog/robotwin/pair-{phase}.jpg"}
            for phase in ("before", "after")}
    data["selectedExamples"] = [{"episodeKey": "paired_r00", **pair}]
    manifest.write_text(json.dumps(data))
    for clip in pair.values():
        for name in clip.values():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"paired asset {name}".encode())
    return pair


def test_paired_robotwin_recordings_and_posters_are_staged(workspace):
    root, destination = workspace
    pair = add_paired_robotwin_example(root)
    before = contents(root)
    build.main()
    assert contents(destination) == before
    for clip in pair.values():
        for name in clip.values():
            assert (destination / name).read_bytes() == (root / name).read_bytes()


@pytest.mark.parametrize("phase", ["before", "after"])
def test_missing_paired_video_preserves_previous_build(workspace, phase):
    root, destination = workspace
    pair = add_paired_robotwin_example(root)
    (root / pair[phase]["video"]).unlink()
    destination.mkdir()
    (destination / "previous.html").write_text("previous successful build")
    with pytest.raises(SystemExit, match="Missing blog video"):
        build.main()
    assert contents(destination) == {"previous.html": b"previous successful build"}
    assert not list(root.glob(".blog-build-*"))


@pytest.mark.parametrize("missing", ["gallery-hosting.json", "gallery-redirect.js", "blog.js",
                                     "data/robotwin-alignment-summary.json", "gallery/robotwin/index.html",
                                     "media/blog/overview/blog-showcase-v4.mp4", "media/blog/overview/blog-showcase-v4.jpg"])
def test_missing_required_asset_preserves_previous_build(workspace, missing):
    root, destination = workspace
    (root / missing).unlink()
    destination.mkdir()
    (destination / "previous.html").write_text("previous successful build")
    with pytest.raises(SystemExit, match="Missing required public file"):
        build.main()
    assert contents(destination) == {"previous.html": b"previous successful build"}


@pytest.mark.parametrize("missing", ["media/libero/example.mp4", "media/libero/example.jpg",
                                     "media/robotwin/example.mp4", "media/robotwin/example.jpg"])
def test_missing_example_preserves_previous_build(workspace, missing):
    root, destination = workspace
    (root / missing).unlink()
    destination.mkdir()
    (destination / "previous.html").write_text("previous successful build")
    with pytest.raises(SystemExit, match="Missing blog"):
        build.main()
    assert contents(destination) == {"previous.html": b"previous successful build"}
    assert not list(root.glob(".blog-build-*"))


@pytest.mark.parametrize("invalid", ["../private.mp4", "media/../../private.mp4",
                                     "/media/private.mp4", "media//private.mp4",
                                     "media/./private.mp4", "media/dir\\private.mp4",
                                     "media/private.mp4?download=true", "assets/private.mp4"])
def test_invalid_media_path_never_enters_build(workspace, invalid):
    root, destination = workspace
    manifest = root / "data/libero-blog-media.json"
    data = json.loads(manifest.read_text())
    data["clips"]["example"]["video"] = invalid
    manifest.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="must be"):
        build.main()
    assert not destination.exists()


@pytest.mark.parametrize("parent_symlink", [False, True])
def test_symlinked_example_is_rejected(workspace, parent_symlink):
    root, destination = workspace
    asset = root / "media/libero/example.mp4"
    if parent_symlink:
        directory = root / "saved-media"
        asset.parent.rename(directory)
        asset.parent.symlink_to(directory, target_is_directory=True)
    else:
        secret = root / "private.mp4"
        secret.write_bytes(b"private")
        asset.unlink()
        asset.symlink_to(secret)
    with pytest.raises(SystemExit, match="Unsafe blog"):
        build.main()
    assert not destination.exists()


def test_symlinked_public_asset_is_rejected(workspace):
    root, destination = workspace
    asset = root / "blog.css"
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
