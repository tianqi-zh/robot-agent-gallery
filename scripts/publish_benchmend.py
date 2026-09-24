#!/usr/bin/env python3
"""Publish the validated LIBERO Dataset, then pin the static gallery to its commit."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from huggingface_hub import HfApi


ROOT = Path(__file__).resolve().parents[1]
STAGES = {"original": 400, "revised_r1": 90, "revised_r2": 20}
PUBLIC_METADATA = {
    "README.md", ".gitattributes", "episodes.json", "episodes.jsonl",
    "episodes.csv", "metadata.json", "provenance.json", "checksums.sha256",
    *(f"{stage}/metadata.jsonl" for stage in STAGES),
}
EPISODE_FIELDS = {
    "id", "stage", "pairKey", "suite", "taskId", "taskName", "initStateIndex",
    "seed", "rolloutId", "instruction", "originalInstruction", "nativeSuccess",
    "agentSuccess", "agentOutcome", "presentationAgentSuccess", "humanCorrection",
    "final", "steps", "video", "poster", "sourceRun", "sourceAttempt",
    "sourceManifestSha256", "sourceResultSha256", "sourceFinishSha256", "sourceVideo",
    "width", "height", "fps", "duration", "frames", "bytes", "sha256",
    "sourceVideoSha256", "posterSha256",
}
SPACE_PUBLIC_FILES = {
    "README.md", ".gitattributes", "index.html", "styles.css", "app.js",
    "episodes.json", "metadata.json", "media-hosting.js",
}


def check_public_text(text, name):
    for prefix in ("/playpen/", "/playpen-ssd/", "/home/", "/tmp/"):
        require(prefix not in text, f"Private host path in {name}: {prefix}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_dataset(root):
    episodes = json.loads((root / "episodes.json").read_text())
    require(all(set(row) == EPISODE_FIELDS for row in episodes), "Unexpected public episode fields")
    require(Counter(row["stage"] for row in episodes) == STAGES, "Unexpected stage counts")
    require(len({row["id"] for row in episodes}) == 510, "Duplicate episode IDs")
    final = [row for row in episodes if row["final"]]
    require(Counter(row["stage"] for row in final) == {
        "original": 310, "revised_r1": 70, "revised_r2": 20,
    }, "Final comparison must explicitly reuse 310 original episodes")
    require(len({row["pairKey"] for row in final}) == 400, "Duplicate final episode slots")
    originals = {row["pairKey"]: row for row in episodes if row["stage"] == "original"}
    require(len(originals) == 400, "Duplicate original episode slots")
    require(len({(row["stage"], row["pairKey"]) for row in episodes}) == 510,
            "Duplicate stage/episode slots")
    require(len({row["video"] for row in episodes}) == 510
            and len({row["poster"] for row in episodes}) == 510,
            "Every recording must have its own video and poster")
    priority = {stage: index for index, stage in enumerate(STAGES)}
    latest = {}
    for row in episodes:
        previous = latest.get(row["pairKey"])
        if previous is None or priority[row["stage"]] > priority[previous["stage"]]:
            latest[row["pairKey"]] = row
    allowed = set(PUBLIC_METADATA)
    expected_hashes = {}
    for row in episodes:
        require(row["suite"] in {"libero_spatial", "libero_goal", "libero_object", "libero_10"}, "Non-LIBERO episode")
        require(row["id"] == f"{row['stage']}/{row['pairKey']}", "Episode ID does not match its stage/slot")
        require(row["pairKey"] in originals, "Revision has no original episode")
        original = originals[row["pairKey"]]
        require(all(row[field] == original[field] for field in (
            "suite", "taskId", "taskName", "initStateIndex", "seed", "rolloutId", "originalInstruction",
        )), f"Unpaired revision: {row['id']}")
        require(original["instruction"] == row["originalInstruction"], "Original instruction differs")
        require(row["stage"] == "original" or row["instruction"] != original["instruction"],
                "Revision did not change its instruction")
        require(type(row["final"]) is bool and row["final"] == (latest[row["pairKey"]] is row),
                "Final comparison must select the latest available instruction revision")
        require(type(row["nativeSuccess"]) is bool, "Native outcome must be boolean")
        require(row["sha256"] == row["sourceVideoSha256"], "Source video must be preserved byte-for-byte")
        for field in ("sha256", "posterSha256", "sourceManifestSha256", "sourceResultSha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", row[field]) is not None, f"Invalid {field}")
        source = Path(row["sourceVideo"])
        require(not source.is_absolute() and ".." not in source.parts, "Unsafe source archive identifier")
        for key, folder, suffix in (("video", "videos", ".mp4"), ("poster", "posters", ".jpg")):
            relative = row[key]
            path = Path(relative)
            require(not path.is_absolute() and ".." not in path.parts, f"Unsafe public path: {relative}")
            require(path.parent.as_posix() == f"{row['stage']}/{folder}" and path.suffix == suffix,
                    f"Unexpected {key} path: {relative}")
            allowed.add(relative)
        require(sha256(root / row["video"]) == row["sha256"], f"Video hash mismatch: {row['id']}")
        require((root / row["video"]).stat().st_size == row["bytes"], f"Video size mismatch: {row['id']}")
        require(sha256(root / row["poster"]) == row["posterSha256"], f"Poster hash mismatch: {row['id']}")
        expected_hashes[row["video"]] = row["sha256"]
        expected_hashes[row["poster"]] = row["posterSha256"]
    present = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(allowed == present, f"Unexpected or missing Dataset files: {sorted(allowed ^ present)}")
    require(not any(path.is_symlink() for path in root.rglob("*")), "Dataset staging must not contain symlinks")
    for name in PUBLIC_METADATA:
        check_public_text((root / name).read_text(), name)
    require([json.loads(line) for line in (root / "episodes.jsonl").read_text().splitlines()] == episodes,
            "JSONL episode catalog differs from JSON")
    with (root / "episodes.csv").open(newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    require(csv_rows == [{key: "" if value is None else str(value) for key, value in row.items()}
                         for row in episodes], "CSV episode catalog differs from JSON")
    for stage in STAGES:
        expected = []
        for row in episodes:
            if row["stage"] == stage:
                item = {key: value for key, value in row.items() if key != "video"}
                item["file_name"] = Path(row["video"]).relative_to(stage).as_posix()
                item["poster"] = Path(row["poster"]).relative_to(stage).as_posix()
                expected.append(item)
        actual = [json.loads(line) for line in (root / stage / "metadata.jsonl").read_text().splitlines()]
        require(actual == expected, f"VideoFolder metadata differs from catalog: {stage}")
    # Verify metadata, posters, and videos against the exporter's complete manifest.
    checksums = {}
    for line in (root / "checksums.sha256").read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        relative = relative.lstrip(" *")
        require(relative not in checksums, f"Duplicate checksum entry: {relative}")
        checksums[relative] = digest
    require(set(checksums) == allowed - {"checksums.sha256"}, "Incomplete checksum manifest")
    for name, expected in checksums.items():
        actual = expected_hashes.get(name) or sha256(root / name)
        require(actual == expected, f"Checksum mismatch: {name}")
    return episodes, allowed


def verify_remote(api, repo, kind, revision, root, names):
    info = api.repo_info(repo, repo_type=kind, revision=revision, files_metadata=True)
    require(info.sha == revision, f"Remote {kind} revision differs from uploaded commit")
    remote = {item.rfilename: item for item in info.siblings}
    require(set(remote) == names, f"Remote {kind} inventory differs: {sorted(set(remote) ^ names)}")
    for name in sorted(names):
        item = remote[name]
        local = root / name
        require(item.size == local.stat().st_size, f"Remote size mismatch: {name}")
        if item.lfs:
            require(item.lfs.sha256 == sha256(local), f"Remote SHA256 mismatch: {name}")
        else:
            raw = local.read_bytes()
            git_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            require(item.blob_id == git_blob, f"Remote Git blob mismatch: {name}")
    return info.sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("/playpen-ssd/tianqizh/benchmend-libero"))
    parser.add_argument("--space-root", type=Path, default=ROOT / "hf-space")
    parser.add_argument("--dataset", default="benchmend/libero")
    parser.add_argument("--space", default="benchmend/gallery")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts/benchmend/publication.json")
    args = parser.parse_args()
    episodes, names = validate_dataset(args.dataset_root)
    print(f"Validated {len(episodes)} LIBERO recordings and {len(names)} Dataset files.", flush=True)
    if args.validate_only:
        return

    api = HfApi()
    # The active user's normal HF authentication is used; credentials are never exported.
    api.create_repo(args.dataset, repo_type="dataset", private=False, exist_ok=True)
    api.create_repo(args.space, repo_type="space", space_sdk="static", private=False, exist_ok=True)
    commit = api.upload_folder(
        repo_id=args.dataset, repo_type="dataset", folder_path=args.dataset_root,
        allow_patterns=sorted(names), commit_message="Publish 400 original LIBERO evaluations and 110 instruction-repair reruns",
    )
    dataset_sha = verify_remote(api, args.dataset, "dataset", commit.oid, args.dataset_root, names)
    print(f"Dataset verified: {args.dataset}@{dataset_sha}", flush=True)

    # Publish a small static interface with local metadata and immutable remote media URLs.
    for name in ("episodes.json", "metadata.json"):
        shutil.copy2(args.dataset_root / name, args.space_root / name)
    base = f"https://huggingface.co/datasets/{args.dataset}/resolve/{dataset_sha}/"
    (args.space_root / "media-hosting.js").write_text(
        "'use strict';\n// Media are pinned to the verified Dataset commit.\n"
        "window.GALLERY_MEDIA_BASE ||= " + json.dumps(base) + ";\n"
    )
    # Keep the upload allowlist fixed: local browser checks, logs and future files
    # cannot silently become public when they are added to the source directory.
    attributes = args.space_root / ".gitattributes"
    if not attributes.exists():
        attributes.write_text("* text=auto\n")
    space_names = set(SPACE_PUBLIC_FILES)
    require(all((args.space_root / name).is_file() for name in space_names), "Missing required Space files")
    for name in space_names:
        check_public_text((args.space_root / name).read_text(), f"Space/{name}")
    require(not any(path.is_symlink() for path in args.space_root.rglob("*")), "Space staging must not contain symlinks")
    # A new static Space includes HF's boilerplate style.css. This app uses
    # styles.css; remove only the verified template, never an unknown stylesheet.
    existing = api.repo_info(args.space, repo_type="space", files_metadata=True)
    boilerplate = next((item for item in existing.siblings if item.rfilename == "style.css"), None)
    if boilerplate:
        require(boilerplate.blob_id == "114adf441e9032febb46bc056b2a8bb651075f0d",
                "Unexpected style.css on the Space; preserve it for review")
    commit = api.upload_folder(
        repo_id=args.space, repo_type="space", folder_path=args.space_root,
        allow_patterns=sorted(space_names), commit_message="Launch the LIBERO-only BenchMend gallery",
        delete_patterns=["style.css"] if boilerplate else None,
    )
    space_sha = verify_remote(api, args.space, "space", commit.oid, args.space_root, space_names)
    report = {
        "dataset": args.dataset, "datasetCommit": dataset_sha,
        "space": args.space, "spaceCommit": space_sha,
        "recordings": len(episodes), "stages": STAGES, "datasetFiles": len(names),
        "mediaBaseUrl": base,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
