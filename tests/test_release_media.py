"""No network writes: release API and GitHub CLI are mocked in every test."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("release_media_under_test", SCRIPTS / "release_media.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def release_record(draft=False):
    tag = "untagged-abc123" if draft else release.RELEASE_TAG
    return {"id": 77, "tag_name": release.RELEASE_TAG, "draft": draft,
            "html_url": f"https://github.com/{release.RELEASE_REPOSITORY}/releases/tag/{tag}",
            "url": f"{release.API_ROOT}/releases/77", "assets_url": f"{release.API_ROOT}/releases/77/assets"}


def assets_for(expected, *, draft=False):
    assets = []
    for index, (name, item) in enumerate(expected.items(), 1):
        url = item["browser_download_url"]
        if draft:
            url = url.replace(release.RELEASE_TAG, "untagged-abc123")
        assets.append({"id": index, "name": name, "url": f"{release.API_ROOT}/releases/assets/{index}",
                       "size": item["size"], "digest": item["digest"], "browser_download_url": url,
                       "content_type": "video/mp4", "state": "uploaded"})
    return assets


def expected_assets():
    return {f"robocasa_task{i:03d}_r00.mp4": {"size": 100 + i, "digest": f"sha256:{i:064x}",
             "browser_download_url": release.remote_video_url(f"robocasa_task{i:03d}_r00")} for i in range(365)}


def api_reader(metadata, assets, calls):
    def read(url):
        calls.append(url)
        if url == f"{release.API_ROOT}/releases/tags/{release.RELEASE_TAG}":
            return copy.deepcopy(metadata)
        assert url.startswith(metadata["assets_url"] + "?per_page=100&page=")
        page = int(url.rsplit("=", 1)[1])
        return copy.deepcopy(assets[(page - 1) * 100:page * 100])
    return read


def test_public_api_fetch_reads_all_four_pages_without_auth(monkeypatch):
    expected = expected_assets()
    calls = []
    monkeypatch.setattr(release, "_public_json", api_reader(release_record(), assets_for(expected), calls))
    actual = release.fetch_release_assets()
    assert release.verify_assets(expected, actual) == []
    assert len(calls) == 5 and calls[-1].endswith("page=4")


@pytest.mark.parametrize("corruption", ["draft", "wrong_tag", "foreign_repo", "foreign_asset", "wrong_download_tag",
                                        "missing_digest", "duplicate", "incomplete", "unknown_asset", "unfinished", "too_large"])
def test_public_fetch_rejects_untrusted_or_incomplete_release(monkeypatch, corruption):
    metadata, assets = release_record(), assets_for(expected_assets())
    if corruption == "draft": metadata["draft"] = True
    elif corruption == "wrong_tag": metadata["tag_name"] = "other"
    elif corruption == "foreign_repo": metadata["assets_url"] = "https://api.github.com/repos/other/repo/releases/77/assets"
    elif corruption == "foreign_asset": assets[0]["url"] = "https://api.github.com/repos/other/repo/releases/assets/1"
    elif corruption == "wrong_download_tag": assets[0]["browser_download_url"] = assets[0]["browser_download_url"].replace(release.RELEASE_TAG, "wrong-tag")
    elif corruption == "missing_digest": assets[0]["digest"] = None
    elif corruption == "duplicate": assets[100] = copy.deepcopy(assets[0])
    elif corruption == "incomplete": assets.pop()
    elif corruption == "unknown_asset": assets[0]["name"] = "notes.txt"
    elif corruption == "unfinished": assets[0]["state"] = "starter"
    elif corruption == "too_large": assets[0]["size"] = release.MAX_ASSET_BYTES
    monkeypatch.setattr(release, "_public_json", api_reader(metadata, assets, []))
    with pytest.raises(release.ReleaseMediaError):
        release.fetch_release_assets()


@pytest.mark.parametrize("identifier", ["Robocasa_task_r00", "robocasa_Task_r00", "../task", "robocasa_x_r00?token=x", "robocasa_x_r00.mp4"])
def test_only_lowercase_episode_identifiers_form_urls(identifier):
    with pytest.raises(release.ReleaseMediaError):
        release.remote_video_url(identifier)


def test_api_redirects_are_refused_before_following_foreign_repository():
    with pytest.raises(release.ReleaseMediaError, match="redirects are refused"):
        release.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://github.com/other/repo")


def local_report(tmp_path):
    media, selections = [], []
    for benchmark, count in (("libero", 400), ("robotwin", 50), ("robocasa", 365)):
        for index in range(count):
            episode_id = f"{benchmark}_task{index:03d}_r00"
            payload = f"synthetic test bytes {episode_id}".encode()
            digest = __import__("hashlib").sha256(payload).hexdigest()
            item = {"episode": episode_id, "benchmark": benchmark, "video": f"media/{benchmark}/{episode_id}.mp4",
                    "videoBytes": len(payload), "videoSha256": digest, "sourceSha256": "f" * 64,
                    "verified": True, "codec": "h264", "pixelFormat": "yuv420p", "fastStart": True}
            media.append(item)
            if benchmark == "robocasa":
                path = tmp_path / item["video"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                selections.append({"episode": episode_id, "status": "failure", "steps": 1, "sourceVideoSha256": "f" * 64})
    report = {"schemaVersion": 1, "complete": True, "expectedEpisodes": 815, "verifiedEpisodes": 815,
              "videoHosting": {"robocasa": release.RELEASE_HOSTING}, "media": media,
              "runs": [{"benchmark": "robocasa", "auditKind": "robocasa_collection", "selectedEpisodes": 365,
                        "auditSha256": "a" * 64, "planSha256": "b" * 64, "attemptSelection": selections}]}
    path = tmp_path / "data/export-report.json"
    path.parent.mkdir()
    path.write_text(json.dumps(report))
    return path, report


def mocked_draft(monkeypatch, report_path, *, present=365, conflict=False, initially_missing=False):
    _, expected = release.load_expected_assets(report_path)
    all_assets = assets_for(expected, draft=True)
    current = all_assets[:present]
    if conflict and current:
        current[0]["digest"] = "sha256:" + "0" * 64
    writes = []
    metadata = release_record(True)
    state = {"exists": not initially_missing, "draft": True}
    monkeypatch.setattr(release, "_verify_collection_binding", lambda *args: None)

    def read(url, **kwargs):
        if url.startswith(f"{release.API_ROOT}/releases?per_page=100&page="):
            assert url.endswith("page=1")
            return [metadata] if state["exists"] else []
        if url == metadata["url"]:
            return metadata
        assert url.startswith(metadata["assets_url"] + "?per_page=100&page=")
        page = int(url.rsplit("=", 1)[1])
        return copy.deepcopy(current[(page - 1) * 100:page * 100])

    def gh(args, **kwargs):
        writes.append(args)
        assert "--clobber" not in args
        if args[:2] == ["release", "create"]:
            assert "--draft" in args
            state["exists"] = True
        elif args[:2] == ["release", "upload"]:
            name = Path(args[3]).name
            assert name not in {asset["name"] for asset in current}
            current.append(next(asset for asset in all_assets if asset["name"] == name))
        elif args[:2] == ["release", "edit"]:
            assert "--draft=false" in args
            state["draft"] = False
        else:
            raise AssertionError(args)
        return ""

    monkeypatch.setattr(release, "_authenticated_json", read)
    monkeypatch.setattr(release, "_gh", gh)
    monkeypatch.setattr(release, "fetch_release_assets", lambda: {item["name"]: item for item in assets_for(expected)})
    return writes, state


def test_upload_resumes_only_missing_assets_without_clobber(tmp_path, monkeypatch):
    path, _ = local_report(tmp_path)
    public_files_before = sorted(p.name for p in path.parent.iterdir())
    writes, _ = mocked_draft(monkeypatch, path, present=363)
    result = release.upload_or_publish(path, collection_audit="mock", source_root="mock")
    assert result == {"state": "draft", "verifiedAssets": 365, "uploadedAssets": 2}
    assert len(writes) == 2 and all(call[:2] == ["release", "upload"] for call in writes)
    again = release.upload_or_publish(path, collection_audit="mock", source_root="mock")
    assert again["uploadedAssets"] == 0 and len(writes) == 2
    assert sorted(p.name for p in path.parent.iterdir()) == public_files_before
    assert (tmp_path / ".gallery-cache/release-media.lock").is_file()


def test_missing_draft_is_created_without_publishing(tmp_path, monkeypatch):
    path, _ = local_report(tmp_path)
    writes, state = mocked_draft(monkeypatch, path, present=0, initially_missing=True)
    result = release.upload_or_publish(path, collection_audit="mock", source_root="mock")
    assert result["uploadedAssets"] == 365 and state["draft"] is True
    assert len(writes) == 366 and writes[0][:2] == ["release", "create"]


@pytest.mark.parametrize("corruption", ["remote_conflict", "missing_remote", "changed_local", "incomplete_report"])
def test_publish_refuses_any_incomplete_or_changed_evidence(tmp_path, monkeypatch, corruption):
    path, report = local_report(tmp_path)
    writes, state = mocked_draft(monkeypatch, path, present=364 if corruption == "missing_remote" else 365,
                                 conflict=corruption == "remote_conflict")
    if corruption == "changed_local":
        (tmp_path / report["media"][-1]["video"]).write_bytes(b"changed")
    elif corruption == "incomplete_report":
        report["complete"] = False
        path.write_text(json.dumps(report))
    with pytest.raises(release.ReleaseMediaError):
        release.upload_or_publish(path, collection_audit="mock", source_root="mock", publish=True)
    assert writes == [] and state["draft"] is True


def test_publish_requires_all_assets_then_rechecks_public_release(tmp_path, monkeypatch):
    path, _ = local_report(tmp_path)
    writes, state = mocked_draft(monkeypatch, path)
    result = release.upload_or_publish(path, collection_audit="mock", source_root="mock", publish=True)
    assert result["state"] == "published" and state["draft"] is False
    assert len(writes) == 1 and writes[0][:2] == ["release", "edit"]


def test_check_is_read_only_and_needs_no_local_videos(tmp_path, monkeypatch):
    path, report = local_report(tmp_path)
    public_files_before = sorted(p.name for p in path.parent.iterdir())
    _, expected = release.load_expected_assets(path)
    for item in report["media"]:
        if item["benchmark"] == "robocasa": (tmp_path / item["video"]).unlink()
    monkeypatch.setattr(release, "fetch_release_assets", lambda: {item["name"]: item for item in assets_for(expected)})
    monkeypatch.setattr(release, "_gh", lambda *args, **kwargs: pytest.fail("Read-only check called gh"))
    assert release.main(["--report", str(path), "--check"]) == 0
    assert sorted(p.name for p in path.parent.iterdir()) == public_files_before
    assert not (tmp_path / ".gallery-cache/release-media.lock").exists()


def test_mutation_requires_private_audit_binding_before_network(tmp_path, monkeypatch):
    path, _ = local_report(tmp_path)
    monkeypatch.setattr(release, "_gh", lambda *args, **kwargs: pytest.fail("Missing audit reached network"))
    with pytest.raises(release.ReleaseMediaError, match="required"):
        release.upload_or_publish(path, collection_audit=None, source_root=None)


def test_cli_hides_external_errors_and_private_paths(tmp_path, monkeypatch, capsys):
    path, _ = local_report(tmp_path)
    def broken():
        raise OSError("private /home/user/auth.json SECRET-VALUE")
    monkeypatch.setattr(release, "fetch_release_assets", broken)
    assert release.main(["--report", str(path)]) == 1
    output = capsys.readouterr()
    assert "/home/" not in output.err and "SECRET-VALUE" not in output.err


def test_changed_collection_audit_is_rejected(tmp_path):
    path, report = local_report(tmp_path)
    audit = tmp_path / "audit.json"
    audit.write_text('{"full_goal_complete":false}')
    with pytest.raises(release.ReleaseMediaError, match="fingerprint"):
        release._verify_collection_binding(report, path, audit, tmp_path / "sources")


def test_duplicate_draft_tags_are_not_silently_reused(monkeypatch):
    monkeypatch.setattr(release, "_authenticated_json", lambda *args: [release_record(True), release_record(True)])
    with pytest.raises(release.ReleaseMediaError, match="Multiple releases"):
        release._find_authenticated_release()


def test_draft_lookup_paginates_and_uses_pending_tag_not_public_tag_endpoint(monkeypatch):
    calls = []
    def read(url):
        calls.append(url)
        return [{"tag_name": f"other-{i}"} for i in range(100)] if url.endswith("page=1") else [release_record(True)]
    monkeypatch.setattr(release, "_authenticated_json", read)
    assert release._find_authenticated_release()["id"] == 77
    assert len(calls) == 2 and all("/releases?" in url for url in calls)


@pytest.mark.parametrize("corruption", [None, "frames", "width", "fps", "duration", "selection"])
def test_private_binding_rechecks_exported_frame_mapping(tmp_path, monkeypatch, corruption):
    import robocasa_export
    path, report = local_report(tmp_path)
    audit = tmp_path / "audit.json"
    audit.write_text('{"synthetic":"only the adapter call is mocked"}')
    run = report["runs"][0]
    run["auditSha256"] = release.sha256(audit)
    jobs = []
    for item in report["media"]:
        if item["benchmark"] != "robocasa": continue
        item.update(frames=2, width=1536, height=512, fps="20", durationSeconds=.1)
        jobs.append({"episode": {"id": item["episode"], "video": item["video"], "frames": 2,
                                 "width": 1536, "height": 512, "durationSeconds": .1},
                     "selection": {"sourceVideoSha256": "f" * 64}})
    provenance = copy.deepcopy(run)
    if corruption == "frames": report["media"][-1]["frames"] = 1
    elif corruption == "width": report["media"][-1]["width"] = 768
    elif corruption == "fps": report["media"][-1]["fps"] = "10"
    elif corruption == "duration": report["media"][-1]["durationSeconds"] = .2
    elif corruption == "selection": run["attemptSelection"][0]["steps"] = 2
    monkeypatch.setattr(robocasa_export, "load_audited_robocasa", lambda *args: ({}, jobs, provenance))
    if corruption is None:
        release._verify_collection_binding(report, path, audit, tmp_path / "runs")
    else:
        with pytest.raises(release.ReleaseMediaError):
            release._verify_collection_binding(report, path, audit, tmp_path / "runs")
