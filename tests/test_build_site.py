"""Exercise Pages staging with tiny synthetic files in temporary directories."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("build_site_under_test", SCRIPTS / "build_site.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

APP_SCRIPT = '<script src="app.js" defer></script>'
SOURCE_HTML = f"<!doctype html><html><body><main>Test gallery</main>{APP_SCRIPT}</body></html>\n"


@pytest.fixture
def workspace(monkeypatch):
    # No fixture reads/copies the real data, media, or existing _site directory.
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from release_media import RELEASE_HOSTING, remote_video_url

    with tempfile.TemporaryDirectory(prefix="gallery-build-test-") as temporary:
        root = Path(temporary)
        destination = root / "_site"
        monkeypatch.setattr(build, "ROOT", root)
        monkeypatch.setattr(build, "DESTINATION", destination)

        def write(relative, payload):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        for name in build.PUBLIC_FILES:
            write(name, SOURCE_HTML.encode() if name == "index.html" else f"synthetic {name}\n".encode())
        write("assets/icon.svg", b"synthetic icon, not a real image")
        for benchmark in ("libero", "robotwin"):
            write(f"media/{benchmark}/legacy.mp4", f"synthetic {benchmark} video".encode())
            write(f"media/{benchmark}/legacy.jpg", f"synthetic {benchmark} poster".encode())

        episodes = []
        for name in ("alpha", "beta"):
            identifier = f"robocasa_{name}_r00"
            episode = {"id": identifier, "video": f"media/robocasa/{identifier}.mp4",
                       "poster": f"media/robocasa/{identifier}.jpg",
                       "remoteVideo": remote_video_url(identifier)}
            write(episode["video"], f"synthetic local release video {name}".encode())
            write(episode["poster"], f"synthetic local poster {name}".encode())
            episodes.append(episode)

        # Prove the exclusion targets declared videos, not the whole directory
        # or every MP4 under media/robocasa.
        write("media/robocasa/unlisted.mp4", b"synthetic unrelated local video")
        gallery = {"benchmarks": [
            {"id": "libero", "tasks": []},
            {"id": "robotwin", "tasks": []},
            {"id": "robocasa", "videoHosting": copy.deepcopy(RELEASE_HOSTING),
             "tasks": [{"id": "robocasa_alpha", "episodes": [episodes[0]]},
                       {"id": "robocasa_beta", "episodes": [episodes[1]]}]},
        ]}

        def save():
            write("data/gallery.json", (json.dumps(gallery) + "\n").encode())

        save()
        yield root, destination, gallery, episodes, save


def source_files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and "_site" not in path.relative_to(root).parts}


def test_stages_only_declared_release_videos_remotely_without_changing_sources(workspace):
    root, destination, _, episodes, _ = workspace
    before = source_files(root)

    build.main()

    assert source_files(root) == before
    excluded = {episode["video"] for episode in episodes}
    staged = {path.relative_to(destination).as_posix(): path.read_bytes()
              for path in destination.rglob("*") if path.is_file()}
    assert set(staged) == set(before) - excluded
    for relative, payload in before.items():
        if relative in excluded:
            assert (root / relative).read_bytes() == payload
            assert not (destination / relative).exists()
        elif relative != "index.html":
            assert staged[relative] == payload

    html = staged["index.html"].decode()
    flag = "window.GALLERY_REMOTE_VIDEOS = true;"
    assert html.count(flag) == 1
    assert html.count(APP_SCRIPT) == 1
    assert html.index(flag) < html.index(APP_SCRIPT)
    assert (root / "index.html").read_text() == SOURCE_HTML


def test_without_robocasa_copies_local_media_and_does_not_inject_flag(workspace):
    root, destination, gallery, _, save = workspace
    gallery["benchmarks"] = [item for item in gallery["benchmarks"] if item["id"] != "robocasa"]
    save()
    before = source_files(root)

    build.main()

    assert source_files(root) == before
    staged = {path.relative_to(destination).as_posix(): path.read_bytes()
              for path in destination.rglob("*") if path.is_file()}
    assert staged == before
    assert "GALLERY_REMOTE_VIDEOS" not in (destination / "index.html").read_text()


@pytest.mark.parametrize("corruption", [
    "hosting_repository", "hosting_tag", "remote_repository", "remote_tag",
    "remote_episode", "remote_query", "video_absolute", "video_traversal", "video_benchmark",
])
def test_invalid_release_mapping_is_rejected_before_touching_existing_stage(workspace, corruption):
    root, destination, gallery, episodes, save = workspace
    benchmark = gallery["benchmarks"][-1]
    episode = episodes[0]
    if corruption == "hosting_repository":
        benchmark["videoHosting"]["repository"] = "different/repository"
    elif corruption == "hosting_tag":
        benchmark["videoHosting"]["tag"] = "different-release"
    elif corruption == "remote_repository":
        episode["remoteVideo"] = episode["remoteVideo"].replace("/tianqi-zh/robot-agent-gallery/", "/different/repository/")
    elif corruption == "remote_tag":
        episode["remoteVideo"] = episode["remoteVideo"].replace("/download/", "/download/different-tag/")
    elif corruption == "remote_episode":
        episode["remoteVideo"] = episodes[1]["remoteVideo"]
    elif corruption == "remote_query":
        episode["remoteVideo"] += "?unexpected=1"
    elif corruption == "video_absolute":
        episode["video"] = "/" + episode["video"]
    elif corruption == "video_traversal":
        episode["video"] = episode["video"].replace("media/robocasa/", "media/robocasa/../robocasa/")
    elif corruption == "video_benchmark":
        episode["video"] = episode["video"].replace("media/robocasa/", "media/libero/")
    save()
    before = source_files(root)
    destination.mkdir()
    sentinel = destination / "previous-build.txt"
    sentinel.write_bytes(b"retain previous staged output on invalid mapping")

    with pytest.raises(SystemExit, match="release video hosting|Invalid release video mapping"):
        build.main()

    assert source_files(root) == before
    assert {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()} == {sentinel.name}
    assert sentinel.read_bytes() == b"retain previous staged output on invalid mapping"
