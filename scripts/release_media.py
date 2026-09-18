"""Verify or explicitly publish the complete RoboCasa365 video release.

The default and --check modes only read the public report and GitHub API.
--upload-draft and --publish are the only modes that write to GitHub. Both
require the complete local videos plus a current hash-bound collection audit;
an existing asset is never overwritten. No credentials or private paths are
included in release notes, output, or public metadata.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener


RELEASE_REPOSITORY = "tianqi-zh/robot-agent-gallery"
RELEASE_TAG = "robocasa365-20260918"
RELEASE_HOSTING = {"kind": "github-release", "repository": RELEASE_REPOSITORY, "tag": RELEASE_TAG}
API_ROOT = f"https://api.github.com/repos/{RELEASE_REPOSITORY}"
EXPECTED_ASSETS = 365
MAX_ASSET_BYTES = 2 * 1024**3


class ReleaseMediaError(ValueError):
    """A release is incomplete or does not match the approved local evidence."""


def require(condition, message):
    if not condition:
        raise ReleaseMediaError(message)


def remote_video_url(episode_id):
    require(isinstance(episode_id, str) and re.fullmatch(r"robocasa_[a-z][a-z0-9_]*_r00", episode_id),
            "Invalid lowercase RoboCasa episode ID")
    return f"https://github.com/{RELEASE_REPOSITORY}/releases/download/{RELEASE_TAG}/{episode_id}.mp4"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReleaseMediaError("Release API redirects are refused; verify the fixed repository identity")


def _public_json(url):
    require(url.startswith(API_ROOT + "/"), "Unexpected release API repository")
    request = Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                                   "User-Agent": "robot-agent-gallery-release-verifier"})
    with build_opener(NoRedirect()).open(request, timeout=60) as response:
        require(response.geturl() == url, "Unexpected release API response URL")
        payload = response.read(8 * 1024 * 1024 + 1)
    require(len(payload) <= 8 * 1024 * 1024, "Release API response is unexpectedly large")
    return json.loads(payload)


def _validate_release(release, *, draft):
    page = release.get("html_url", "") if isinstance(release, dict) else ""
    expected_page = f"https://github.com/{RELEASE_REPOSITORY}/releases/tag/{RELEASE_TAG}"
    draft_page = (isinstance(page, str) and re.fullmatch(
        re.escape(f"https://github.com/{RELEASE_REPOSITORY}/releases/tag/") + r"untagged-[A-Za-z0-9]+", page))
    require(isinstance(release, dict) and type(release.get("id")) is int and release["id"] > 0
            and release.get("tag_name") == RELEASE_TAG and release.get("draft") is draft
            and (page == expected_page or draft is True and draft_page)
            and release.get("url") == f"{API_ROOT}/releases/{release['id']}"
            and release.get("assets_url") == f"{API_ROOT}/releases/{release['id']}/assets",
            "Wrong release identity, tag, or draft state")


def _asset_urls(name, release=None):
    urls = {remote_video_url(name[:-4])}
    if release is not None and release.get("draft") is True:
        _validate_release(release, draft=True)
        pending = release["html_url"].rsplit("/", 1)[1]
        urls.add(f"https://github.com/{RELEASE_REPOSITORY}/releases/download/{pending}/{name}")
    return urls


def _collect_assets(release, read_json, *, complete):
    assets = {}
    # A page of exactly 100 needs another request; page 11 catches an over-limit
    # or nonterminating endpoint instead of silently truncating the response.
    for page in range(1, 12):
        batch = read_json(f"{release['assets_url']}?per_page=100&page={page}")
        require(isinstance(batch, list) and len(batch) <= 100, "Invalid release asset page")
        for asset in batch:
            require(isinstance(asset, dict), "Invalid release asset")
            name = asset.get("name")
            require(isinstance(name, str) and name.endswith(".mp4"), "Unknown non-video release asset")
            allowed_urls = _asset_urls(name, release)
            require(name not in assets and type(asset.get("id")) is int and asset["id"] > 0
                    and asset.get("url") == f"{API_ROOT}/releases/assets/{asset['id']}"
                    and asset.get("browser_download_url") in allowed_urls and asset.get("state") == "uploaded"
                    and asset.get("content_type") in {"video/mp4", "application/octet-stream"}
                    and type(asset.get("size")) is int and 0 < asset["size"] < MAX_ASSET_BYTES
                    and isinstance(asset.get("digest"), str) and re.fullmatch(r"sha256:[0-9a-f]{64}", asset["digest"]),
                    "Duplicate, incomplete, or invalid release asset metadata")
            assets[name] = {key: asset[key] for key in ("id", "name", "url", "size", "digest", "content_type",
                                                       "browser_download_url", "state")}
        require(len(assets) <= EXPECTED_ASSETS, "Release contains unknown additional assets")
        if len(batch) < 100:
            break
    else:
        raise ReleaseMediaError("Release asset pagination did not terminate")
    require(not complete or len(assets) == EXPECTED_ASSETS, "Release does not contain all 365 videos")
    return assets


def fetch_release_assets():
    """Read all published assets from the fixed public repository, without auth."""
    release = _public_json(f"{API_ROOT}/releases/tags/{RELEASE_TAG}")
    _validate_release(release, draft=False)
    return _collect_assets(release, _public_json, complete=True)


def load_expected_assets(report_path):
    """Validate the public report contract; CI need not have private source runs."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text())
    require(report.get("schemaVersion") == 1 and report.get("complete") is True
            and report.get("expectedEpisodes") == report.get("verifiedEpisodes") == 815
            and report.get("videoHosting", {}).get("robocasa") == RELEASE_HOSTING,
            "A complete 815-episode export with the fixed RoboCasa hosting configuration is required")
    media = report["media"]
    require(len(media) == len({item["episode"] for item in media}) == 815
            and Counter(item["benchmark"] for item in media) == {"libero": 400, "robotwin": 50, "robocasa": 365},
            "Incomplete or duplicate exported episode matrix")
    runs = [run for run in report["runs"] if run.get("benchmark") == "robocasa"]
    require(len(runs) == 1 and runs[0].get("auditKind") == "robocasa_collection" and runs[0].get("selectedEpisodes") == 365,
            "Missing complete RoboCasa collection provenance")
    run = runs[0]
    for key in ("auditSha256", "planSha256"):
        require(isinstance(run.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", run[key]), "Invalid collection fingerprint")
    selections = run["attemptSelection"]
    require(len(selections) == len({row["episode"] for row in selections}) == 365, "Duplicate or incomplete source selections")
    by_id = {row["episode"]: row for row in selections}
    expected = {}
    for item in media:
        if item["benchmark"] != "robocasa":
            continue
        episode_id = item["episode"]
        url = remote_video_url(episode_id)
        require(item.get("video") == f"media/robocasa/{episode_id}.mp4"
                and item.get("remoteVideo", url) == url and item.get("verified") is True
                and item.get("codec") == "h264" and item.get("pixelFormat") == "yuv420p" and item.get("fastStart") is True
                and type(item.get("videoBytes")) is int and 0 < item["videoBytes"] < MAX_ASSET_BYTES
                and isinstance(item.get("videoSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", item["videoSha256"]),
                "Invalid local video publication record")
        selection = by_id.get(episode_id)
        require(selection is not None and selection.get("status") in {"success", "failure", "timeout"}
                and type(selection.get("steps")) is int and selection["steps"] > 0
                and selection.get("sourceVideoSha256") == item.get("sourceSha256"), "Media/source audit binding differs")
        expected[f"{episode_id}.mp4"] = {"size": item["videoBytes"], "digest": f"sha256:{item['videoSha256']}",
                                         "browser_download_url": url, "local_relative_path": item["video"]}
    return report, expected


def verify_assets(expected, actual, *, allow_missing=False, draft_release=None):
    require(not (set(actual) - set(expected)), "Release contains assets outside the complete collection")
    require(allow_missing or set(actual) == set(expected), "Release is missing expected videos")
    for name, asset in actual.items():
        require(all(asset.get(key) == expected[name][key] for key in ("size", "digest"))
                and asset.get("browser_download_url") in _asset_urls(name, draft_release),
                f"Existing release asset differs from the approved export: {name}")
    return sorted(set(expected) - set(actual))


def _check_local_files(root, expected):
    for name, asset in expected.items():
        path = root / asset["local_relative_path"]
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
                and path.stat().st_size == asset["size"] and f"sha256:{sha256(path)}" == asset["digest"],
                f"Missing or changed local release video: {name}")


def _verify_collection_binding(report, report_path, collection_audit, source_root):
    require(collection_audit is not None and source_root is not None,
            "--collection-audit and --source-root are required for upload or publication")
    run = next(run for run in report["runs"] if run["benchmark"] == "robocasa")
    require(sha256(collection_audit) == run["auditSha256"], "Local collection audit differs from the export fingerprint")
    from robocasa_export import load_audited_robocasa
    _, jobs, provenance = load_audited_robocasa(source_root, collection_audit, report_path.parent.parent)
    require(all(run.get(key) == value for key, value in provenance.items()), "Current collection selections differ from the public export")
    media = {item["episode"]: item for item in report["media"] if item["benchmark"] == "robocasa"}
    require(len(jobs) == 365, "Current collection does not contain every task")
    for job in jobs:
        item, episode = media[job["episode"]["id"]], job["episode"]
        require(item["sourceSha256"] == job["selection"]["sourceVideoSha256"]
                and all(item.get(key) == episode[key] for key in ("video", "width", "height", "frames"))
                and Fraction(item.get("fps", "0")) == 20
                and abs(item.get("durationSeconds", -1) - episode["durationSeconds"]) < 1e-3,
                "Exported video mapping differs from the audited source frames or camera layout")


def _gh(arguments, *, missing_ok=False):
    completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=1800)
    if completed.returncode:
        if missing_ok and re.search(r"\bHTTP 404\b", completed.stderr):
            return None
        # CLI output can contain credentials or private paths; never relay it.
        raise ReleaseMediaError("GitHub CLI failed; no existing asset was overwritten")
    return completed.stdout


def _authenticated_json(url, *, missing_ok=False):
    require(url.startswith(API_ROOT + "/"), "Unexpected authenticated release API repository")
    endpoint = url.removeprefix("https://api.github.com/")
    output = _gh(["api", "--method", "GET", endpoint], missing_ok=missing_ok)
    return None if output is None else json.loads(output)


def _find_authenticated_release():
    # GitHub's /releases/tags endpoint is for published releases. Listing with
    # authenticated push access also finds drafts by their pending tag_name.
    matches = []
    for page in range(1, 102):
        rows = _authenticated_json(f"{API_ROOT}/releases?per_page=100&page={page}")
        require(isinstance(rows, list) and len(rows) <= 100, "Invalid release listing page")
        matches.extend(row for row in rows if isinstance(row, dict) and row.get("tag_name") == RELEASE_TAG)
        require(len(matches) <= 1, "Multiple releases have the requested tag; refusing an ambiguous draft")
        if len(rows) < 100:
            return matches[0] if matches else None
    raise ReleaseMediaError("Release listing pagination did not terminate")


def upload_or_publish(report_path, *, collection_audit, source_root, publish=False):
    """Explicit mutation entry point: called only by --upload-draft / --publish."""
    report_path = Path(report_path).resolve()
    root = report_path.parent.parent
    report_hash = sha256(report_path)
    report, expected = load_expected_assets(report_path)
    _verify_collection_binding(report, report_path, collection_audit, source_root)
    _check_local_files(root, expected)
    # Prevent two invocations in this checkout racing one another. GitHub also
    # rejects duplicate asset names; no invocation ever passes --clobber.
    cache = root / ".gallery-cache"
    cache.mkdir(exist_ok=True)
    with (cache / "release-media.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = _find_authenticated_release()
        if release is None:
            require(not publish, "No draft exists to publish; use --upload-draft after validation")
            require(sha256(report_path) == report_hash, "Export report changed before draft creation")
            _gh(["release", "create", RELEASE_TAG, "--repo", RELEASE_REPOSITORY, "--draft", "--target", "main",
                 "--title", "RoboCasa365 evaluation videos", "--notes",
                 "All 365 independently audited RoboCasa365 policy episodes, including failures and timeouts. Presentation videos retain every recorded frame and camera view."])
            release = _find_authenticated_release()
            require(release is not None, "Created draft was not found")
        _validate_release(release, draft=release.get("draft"))
        require(type(release.get("draft")) is bool, "Invalid draft state")
        actual = _collect_assets(release, _authenticated_json, complete=False)
        missing = verify_assets(expected, actual, allow_missing=not publish, draft_release=release)
        if release["draft"] is False:
            require(not missing, "Published release is incomplete; refusing to mutate it")
            verify_assets(expected, fetch_release_assets())
            return {"state": "already-published", "verifiedAssets": EXPECTED_ASSETS, "uploadedAssets": 0}
        if not publish:
            for number, name in enumerate(missing, 1):
                require(sha256(report_path) == report_hash, "Export report changed during upload")
                _check_local_files(root, {name: expected[name]})
                _gh(["release", "upload", RELEASE_TAG, str(root / expected[name]["local_relative_path"]), "--repo", RELEASE_REPOSITORY])
                if number % 10 == 0 or number == len(missing):
                    print(json.dumps({"state": "uploading-draft", "uploadedAssets": number,
                                      "missingAssetsAtStart": len(missing)}), flush=True)
            refreshed = _authenticated_json(release["url"])
            _validate_release(refreshed, draft=True)
            verify_assets(expected, _collect_assets(refreshed, _authenticated_json, complete=True), draft_release=refreshed)
            require(sha256(report_path) == report_hash, "Export report changed during upload")
            return {"state": "draft", "verifiedAssets": EXPECTED_ASSETS, "uploadedAssets": len(missing)}
        require(sha256(report_path) == report_hash, "Export report changed before publication")
        _check_local_files(root, expected)
        _gh(["release", "edit", RELEASE_TAG, "--repo", RELEASE_REPOSITORY, "--draft=false"])
        verify_assets(expected, fetch_release_assets())
        return {"state": "published", "verifiedAssets": EXPECTED_ASSETS, "uploadedAssets": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[1] / "data/export-report.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only comparison with all published release assets (default)")
    mode.add_argument("--upload-draft", action="store_true", help="Explicitly create/resume a draft and upload missing verified videos")
    mode.add_argument("--publish", action="store_true", help="Explicitly publish only after every asset and private audit matches")
    parser.add_argument("--collection-audit", type=Path, help="Required for mutation: complete hash-bound collection audit")
    parser.add_argument("--source-root", type=Path, help="Required for mutation: original evaluation run directories")
    args = parser.parse_args(argv)
    try:
        if args.upload_draft or args.publish:
            result = upload_or_publish(args.report, collection_audit=args.collection_audit,
                                       source_root=args.source_root, publish=args.publish)
        else:
            _, expected = load_expected_assets(args.report)
            verify_assets(expected, fetch_release_assets())
            result = {"state": "verified-published", "verifiedAssets": EXPECTED_ASSETS}
        print(json.dumps(result, sort_keys=True))
        return 0
    except ReleaseMediaError as exc:
        print(f"Release media verification failed: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, TypeError, IndexError, ArithmeticError, subprocess.SubprocessError):
        # Do not echo third-party exceptions containing local paths or API data.
        print("Release media verification failed. Keep the release unchanged and check the report, audit and asset identities.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
