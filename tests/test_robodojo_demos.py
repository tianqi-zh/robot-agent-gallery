"""Protect exact-task/source attribution, download integrity, and full videos."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_robodojo_demos as demos


def task(name):
    return {"id": f"robodojo_{name.lower()}", "nativeTaskName": name,
            "instruction": "An evaluation instruction is not demo source metadata.", "episodes": []}


def source(name="push_T", payload=b"pinned source video"):
    return demos.Candidate(name, f"{demos.PREFIX}/{name}/{demos.VIDEO_SUFFIX}",
                           len(payload), hashlib.sha256(payload).hexdigest())


def metadata(*candidates):
    return {"repo": demos.REPO_ID, "revision": demos.REVISION, "files": [
        {"path": item.relative_path, "size": item.size, "lfs": {"size": item.size, "oid": item.digest}}
        for item in candidates]}


def test_native_names_cannot_collapse_to_duplicate_gallery_ids():
    with pytest.raises(ValueError, match="duplicate gallery task"):
        demos.select_sources([task("push_T"), task("push_t")], metadata(source("push_T")))


def test_exact_task_mapping_retains_unavailable_records():
    selected, missing = demos.select_sources(
        [task("push_T"), task("general_pickup")], metadata(source("push_T"), source("dlc")))
    assert list(selected) == ["robodojo_push_t"]
    assert selected["robodojo_push_t"].task_name == "push_T"
    assert [row["taskId"] for row in missing] == ["robodojo_general_pickup"]
    assert missing[0]["status"] == "unavailable"
    assert "video" not in missing[0]
    selected, missing = demos.select_sources([task("push_t")], metadata(source("push_T")))
    assert not selected and len(missing) == 1


@pytest.mark.parametrize("corruption", ["revision", "repo", "size", "digest", "traversal", "duplicate", "incomplete"])
def test_rejects_unpinned_or_inconsistent_source_metadata(corruption):
    value = metadata(source())
    if corruption in {"revision", "repo"}:
        value[corruption] = "different-source"
    elif corruption == "size":
        value["files"][0]["lfs"]["size"] += 1
    elif corruption == "digest":
        value["files"][0]["lfs"]["oid"] = "invalid"
    elif corruption == "traversal":
        value["files"][0]["path"] = "data/RoboDojo/../../other/video.mp4"
    elif corruption == "duplicate":
        value["files"].append(deepcopy(value["files"][0]))
    else:
        value["summary"] = {"files": 20}
    with pytest.raises(ValueError):
        demos.select_sources([task("push_T")], value)


def test_present_task_without_selected_video_is_an_error():
    value = metadata(source())
    value["files"][0]["path"] = value["files"][0]["path"].replace("cam_head", "cam_left_wrist")
    with pytest.raises(ValueError, match="selected episode"):
        demos.select_sources([task("push_T")], value)


def test_instruction_receipt_binds_same_task_episode_and_pinned_hdf5():
    candidate = source()
    value = metadata(candidate)
    hdf5_path = f"{demos.PREFIX}/push_T/arx_x5/data/{demos.EPISODE}.hdf5"
    value["files"].append({"path": hdf5_path, "size": 12345, "lfs": {"oid": "a" * 64, "size": 12345}})
    receipt = {"repo": demos.REPO_ID, "revision": demos.REVISION, "records": [
        {"taskName": "push_T", "sourcePath": hdf5_path, "sourceBytes": 12345, "sourceSha256": "a" * 64,
         "instructions": {"instruction": "The actual training instruction."}}]}
    selected = {"robodojo_push_t": candidate}
    instructions = demos.load_instructions(receipt, value, selected)
    assert instructions["robodojo_push_t"]["instruction"] == "The actual training instruction."
    for key, replacement in [("sourceSha256", "b" * 64), ("sourceBytes", 12),
                              ("sourcePath", hdf5_path.replace("0000000", "0000001"))]:
        changed = deepcopy(receipt)
        changed["records"][0][key] = replacement
        with pytest.raises(ValueError, match="selected pinned HDF5"):
            demos.load_instructions(changed, value, selected)


class Response(BytesIO):
    def __init__(self, body, *, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Length": str(len(body)), **(headers or {})}


@pytest.mark.parametrize("honor_range", [True, False])
def test_partial_download_resumes_or_replaces_when_range_ignored(tmp_path, monkeypatch, honor_range):
    payload = b"verified payload bytes"
    candidate = source(payload=payload)
    destination = tmp_path / candidate.relative_path
    destination.parent.mkdir(parents=True)
    partial = destination.with_suffix(".mp4.part")
    partial.write_bytes(payload[:8])

    def opening(request, timeout):
        assert request.get_header("Range") == "bytes=8-"
        assert f"/resolve/{demos.REVISION}/" in request.full_url
        if honor_range:
            return Response(payload[8:], status=206, headers={"Content-Range": f"bytes 8-{len(payload)-1}/{len(payload)}"})
        return Response(payload)

    monkeypatch.setattr(demos, "urlopen", opening)
    assert demos.download(candidate, tmp_path) == destination
    assert destination.read_bytes() == payload and not partial.exists()
    monkeypatch.setattr(demos, "urlopen", lambda *a, **kw: pytest.fail("Valid cached bytes should not download"))
    assert demos.download(candidate, tmp_path) == destination


def test_wrong_download_hash_never_publishes_and_retries(tmp_path, monkeypatch):
    payload = b"correct content"
    candidate = source(payload=payload)
    bodies = iter([b"x" * len(payload), payload])
    monkeypatch.setattr(demos, "urlopen", lambda *args, **kwargs: Response(next(bodies)))
    monkeypatch.setattr(demos.time, "sleep", lambda _: None)
    destination = demos.download(candidate, tmp_path, retries=2)
    assert destination.read_bytes() == payload


def test_wrong_range_does_not_append_or_publish(tmp_path, monkeypatch):
    payload = b"correct content"
    candidate = source(payload=payload)
    destination = tmp_path / candidate.relative_path
    destination.parent.mkdir(parents=True)
    partial = destination.with_suffix(".mp4.part")
    partial.write_bytes(payload[:4])
    monkeypatch.setattr(demos, "urlopen", lambda *args, **kwargs:
                        Response(payload[4:], status=206, headers={"Content-Range": "bytes 0-10/15"}))
    with pytest.raises(RuntimeError, match="Content-Range"):
        demos.download(candidate, tmp_path, retries=1)
    assert partial.read_bytes() == payload[:4]
    assert not destination.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg tools required")
@pytest.mark.parametrize("codec", ["libx264", "mpeg4"])
def test_export_preserves_full_video_and_does_not_copy_evaluation_instruction(tmp_path, codec):
    dataset_root, gallery_root = tmp_path / "dataset", tmp_path / "gallery"
    original_path = dataset_root / source().relative_path
    original_path.parent.mkdir(parents=True)
    demos.run("ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
              "color=c=blue:s=64x48:r=25", "-frames:v", "7", "-c:v", codec,
              "-pix_fmt", "yuv420p", "-threads", "1", str(original_path))
    candidate = source(payload=original_path.read_bytes())
    gallery_task = task("push_T")
    before = deepcopy(gallery_task)
    record = demos.export_task(gallery_task, candidate, dataset_root, gallery_root)
    assert gallery_task == before
    assert "instruction" not in record
    assert (record["frames"], record["fps"], record["width"], record["height"]) == (7, 25, 64, 48)
    assert record["durationSeconds"] == 7 / 25
    assert record["source"]["sourceSha256"] == candidate.digest
    assert record["source"]["relativePath"] == candidate.relative_path
    assert demos.faststart(gallery_root / record["video"])
    with pytest.raises(ValueError, match="selected source"):
        demos.export_task(task("swap_T"), candidate, dataset_root, gallery_root)
