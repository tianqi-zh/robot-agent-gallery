#!/usr/bin/env python3
"""Build public RoboTwin article data from an immutable, audited HF snapshot.

Inputs default to artifacts/benchmend/blog_refresh_latest: snapshot.json, the
unchanged catalog and selection, stats-audit.json, stats-public.json, and
selected-examples.json. Existing output supplies two archived failure examples.
An author confirmation is applied only after the immutable raw audit validates.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "artifacts/benchmend/blog_refresh_latest"
DEFAULT_OUTPUT = ROOT / "data/robotwin-alignment-summary.json"
DEFAULT_HUMAN_REVIEW = ROOT / "data/robotwin-human-review.json"
ARCHIVED_KEYS = ("move_can_pot_r01", "place_dual_shoes_r00")
ARCHIVED_REVISION = "a853415121ee6363d34db7ce892631f909af9ba0"
SELECTED_KEYS = ("adjust_bottle_r00", "place_object_basket_r01")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def summarize(rows, phase, expected):
    values = [row[phase] for row in rows]
    matrix = Counter((item["presentationAgentComplete"], item["nativeSuccess"])
                     for item in values)
    result = {"n": len(values)}
    for label, value in (("Success", True), ("False", False), ("Unknown", None)):
        for native_label, native in (("Success", True), ("False", False)):
            result[f"agent{label}Bench{native_label}"] = matrix[value, native]
    public_matrix = {f"{agent}_{native}": matrix[a, b]
                     for agent, a in (("complete", True), ("incomplete", False), ("unknown", None))
                     for native, b in (("success", True), ("failure", False))}
    require(public_matrix == expected["presentationMatrix"], "Rows differ from audited matrix")
    known = sum(item["positiveDisagreement"] is True for item in values)
    unknown = sum(item["positiveDisagreement"] is None for item in values)
    result.update({
        "benchSuccess": sum(item["nativeSuccess"] for item in values),
        "benchFalse": sum(not item["nativeSuccess"] for item in values),
        "timeouts": sum(item["nativeStatus"] == "timeout" for item in values),
        "instinctAlignment": None if unknown else 1 - known / len(values),
        "instinctAlignmentBounds": {"min": 1 - (known + unknown) / len(values),
                                    "max": 1 - known / len(values)},
    })
    require(result["n"] == expected["episodes"]
            and result["benchSuccess"] == expected["nativeSuccesses"]
            and result["benchFalse"] == expected["nativeFailuresIncludingTimeout"]
            and known == expected["explicitPositiveDisagreementsKnown"]
            and unknown == expected["positiveDisagreementUnknown"], "Rows differ from audited totals")
    result["benchmarkSuccessRate"] = result["benchSuccess"] / len(values)
    return result


def selected_examples(manifest, rows, root):
    by_key = {row["episodeKey"]: row for row in rows}
    require(tuple(item["sourceEpisodeKey"] for item in manifest["examples"]) == SELECTED_KEYS,
            "Expected exactly Task 00 / Episode 01 and Task 32 / Episode 02")
    examples = []
    for item in manifest["examples"]:
        row = by_key[item["sourceEpisodeKey"]]
        example = {"episodeKey": item["sourceEpisodeKey"], "taskId": item["taskId"],
                   "episodeNumber": item["episodeNumber"], "taskName": item["taskName"],
                   "title": item["taskTitle"], "label": item["label"],
                   "sameSceneSeed": item["sameReportedSeed"],
                   "galleryUrl": "https://benchmend-gallery.static.hf.space/gallery/robotwin/"
                                 "?episode=" + row["before"]["id"]}
        for phase, source_phase in (("before", "original"), ("after", "revision")):
            source = item["phases"][source_phase]
            record, audited = source["sourceRecord"], row[phase]
            require(record["id"] == audited["id"] and record["seed"] == row["seed"]
                    and record["status"] == audited["nativeStatus"], "Selected record differs from audit")
            details = {key: record[key] for key in ("id", "instruction", "status", "seed", "steps",
                       "toolCalls", "wallSeconds", "durationSeconds", "width", "height", "frames")}
            details.update({"benchSuccess": audited["nativeSuccess"],
                            "agentSuccess": audited["presentationAgentComplete"],
                            "agentOutcome": audited["agentOutcome"],
                            "agentOutcomeAvailability": audited["agentOutcomeAvailability"],
                            "source": audited["source"], "mediaSources": {}})
            for kind in ("video", "poster"):
                asset = source["media"][kind]
                path = root / asset["localPath"]
                require(path.is_file() and sha256(path) == asset["sha256"],
                        f"Missing or changed selected {kind}: {asset['localPath']}")
                require(kind != "video" or asset.get("fullDecodeVerified") is True,
                        "Selected video has not passed full decoding")
                details[kind] = asset["localPath"]
                details["mediaSources"][kind] = {"url": asset["sourceUrl"], "sha256": asset["sha256"],
                                                "bytes": asset["bytes"], "metadata": asset["probe"]}
            example[phase] = details
        require(example["before"]["seed"] == example["after"]["seed"], "Example scene seeds differ")
        examples.append(example)
    return examples


def apply_author_confirmation(rows, snapshot, review_path):
    """Overlay the author's dated judgment without changing raw self-assessments."""
    review = read(review_path)
    require(review["snapshot"] == snapshot, "Author confirmation snapshot differs")
    require(review["source"]["kind"] == "project_author_confirmation"
            and review["decision"] == "agent_benchmark_disagreement", "Unsupported confirmation source or decision")
    keys = review["episodeKeys"]
    unknown = {row["episodeKey"] for row in rows if row["after"]["positiveDisagreement"] is None}
    require(len(keys) == len(set(keys)) == 36 and set(keys) == unknown,
            "Author confirmation must match exactly the 36 unpublished after assessments")
    provenance = {"document": "data/robotwin-human-review.json", "sha256": sha256(review_path),
                  "date": review["date"], "source": review["source"], "decision": review["decision"]}
    revised = deepcopy(rows)
    for row in revised:
        if row["episodeKey"] not in unknown:
            continue
        after = row["after"]
        require(row["disposition"] == "revision_replaces_original_disagreement"
                and after["nativeStatus"] == "failure" and after["nativeSuccess"] is False
                and after["agentOutcome"] is None and after["agentOutcomeAvailability"] == "not_exported"
                and after["presentationAgentComplete"] is None,
                "Author confirmation targets an unexpected outcome")
        after["presentationAgentComplete"] = True
        after["positiveDisagreement"] = True
        after["authorConfirmation"] = provenance
    return revised, provenance


def confirmed_stats(raw_stats, confirmed_count):
    stats = deepcopy(raw_stats)
    require(stats["positiveDisagreementUnknown"] == confirmed_count
            and stats["presentationMatrix"]["unknown_failure"] == confirmed_count,
            "Confirmed outcomes do not match unknown failure statistics")
    stats["explicitPositiveDisagreementsKnown"] += confirmed_count
    stats["positiveDisagreementUnknown"] = 0
    stats["positiveDisagreementRange"] = [stats["explicitPositiveDisagreementsKnown"]] * 2
    stats["presentationMatrix"]["complete_failure"] += confirmed_count
    stats["presentationMatrix"]["unknown_failure"] = 0
    stats["authorConfirmedDisagreements"] = confirmed_count
    return stats


def regenerate(snapshot_dir, legacy_path, root=ROOT, human_review_path=DEFAULT_HUMAN_REVIEW):
    snapshot = read(snapshot_dir / "snapshot.json")
    audit, public = (read(snapshot_dir / name) for name in ("stats-audit.json", "stats-public.json"))
    media = read(snapshot_dir / "selected-examples.json")
    require(snapshot == audit["snapshot"] == public["snapshot"] == media["sourceSnapshot"],
            "Input snapshots differ")
    base = f"https://huggingface.co/spaces/{snapshot['space']}/resolve/{snapshot['revision']}/"
    sources = {name: audit["sources"][name] for name in ("catalog", "selection")}
    for name, relative in (("catalog", "data/gallery.json"),
                           ("selection", "data/robotwin-original-disagreement-selection.json")):
        require(sources[name]["url"] == base + relative
                and sources[name]["sha256"] == sha256(snapshot_dir / relative), "Pinned source hash differs")
    catalog = read(snapshot_dir / "data/gallery.json")
    selection = read(snapshot_dir / "data/robotwin-original-disagreement-selection.json")
    records = {episode["id"]: episode for benchmark in catalog["benchmarks"]
               for task in benchmark["tasks"] for episode in task["episodes"]}
    rows = public["rows"]
    require(len(rows) == len({row["episodeKey"] for row in rows}) == len(audit["rows"]) == 500,
            "Expected 500 distinct audited episodes")
    for row, private in zip(rows, audit["rows"]):
        require(row["episodeKey"] == private["episodeKey"], "Audit row order differs")
        for phase in ("before", "after"):
            data = row[phase]
            require({k: v for k, v in data.items() if k != "source"}
                    == {k: v for k, v in private[phase].items() if k != "source"}, "Public audit altered outcomes")
            record = records[data["id"]]
            require(record["sourceEpisodeKey"] == row["episodeKey"] and record["seed"] == row["seed"]
                    and record["status"] == data["nativeStatus"]
                    and (record["status"] == "success") == data["nativeSuccess"]
                    and object_sha256(record) == data["source"]["episodeObjectSha256"], "Catalog record differs")
    changed = {row["episodeKey"] for row in rows if row["disposition"] == "revision_replaces_original_disagreement"}
    require(changed == {case["episodeKey"] for case in selection["cases"]}, "Selected replacement set differs")
    # Validate immutable raw totals before applying separately sourced author judgments.
    before = summarize(rows, "before", public["before"])
    summarize(rows, "after", public["afterComposite"])
    summarize([row for row in rows if row["episodeKey"] in changed], "after", public["rerunsOnly"])
    rows, confirmation = apply_author_confirmation(rows, snapshot, human_review_path)
    after_stats = confirmed_stats(public["afterComposite"], 36)
    rerun_stats = confirmed_stats(public["rerunsOnly"], 36)
    summarize([row for row in rows if row["episodeKey"] in changed], "after", rerun_stats)
    sources["authorConfirmation"] = confirmation
    rules = {**public["rules"],
             "revisedFailure": "Use the recorded final assessment or the separately sourced author confirmation. A verified missing finish counts as incomplete. Raw unavailable assessments remain null.",
             "authorConfirmation": "The project author confirmed that all 36 listed V4 failures remain agent-benchmark disagreements on 2026-09-24. This confirmation supplies their classification, not a recovered raw finish assessment."}
    legacy = read(legacy_path)
    archived_source = legacy.get("archivedExamplesSource", {
        "url": f"https://github.com/tianqi-zh/robot-agent-gallery/blob/{ARCHIVED_REVISION}/data/robotwin-alignment-summary.json",
        "sha256": sha256(legacy_path), "sourceRun": "robotwin_goal_spec_full_v1",
        "note": "Archived failure examples retain historical records and media; their historical after outcomes are not used in the latest comparison.",
    })
    archived = {case["episodeKey"]: deepcopy(case) for case in legacy["cases"]}
    cases = [{**archived[key], "archived": True, "sourceRun": "robotwin_goal_spec_full_v1"} for key in ARCHIVED_KEYS]
    result = {"schemaVersion": 2, "generatedAt": catalog["generatedAt"], "benchmark": "robotwin",
              "snapshot": snapshot, "sources": sources, "comparisonScope": public["comparisonScope"],
              "before": before,
              "after": summarize(rows, "after", after_stats),
              "rerunsOnly": rerun_stats,
              "coverage": {"plannedEpisodes": len(rows), "beforeTerminalResults": len(rows),
                           "afterTerminalResults": len(rows), "revisionEpisodes": len(changed)},
              "notes": ["After combines unchanged originals with selected reruns of original disagreements.",
                        "Native success counts as agent complete in the reporting matrix; raw self-assessments are preserved separately.",
                        "The project author confirmed 36 remaining disagreements; their raw self-assessments are still unavailable. The confirmed after alignment is 92.8%."],
              "rules": rules, "unknownAfterEpisodeKeys": [],
              "authorConfirmedAfterEpisodeKeys": read(human_review_path)["episodeKeys"],
              "episodes": rows, "archivedExamplesSource": archived_source, "cases": cases,
              "selectedExamples": selected_examples(media, rows, root)}
    encoded = json.dumps(result, ensure_ascii=False)
    require(not any(private in encoded for private in ("/playpen/", "/lustre/", "/home/", "agentReason", "agentVisualChecks")),
            "Private paths or assessment notes entered public data")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--legacy-summary", type=Path, help="Defaults to existing output")
    parser.add_argument("--human-review", type=Path, default=DEFAULT_HUMAN_REVIEW,
                        help="Dated, snapshot-scoped author confirmation")
    args = parser.parse_args()
    result = regenerate(args.snapshot_dir, args.legacy_summary or args.output,
                        human_review_path=args.human_review)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(result['episodes'])} audited episodes and {len(result['selectedExamples'])} paired examples: "
          f"native success {result['before']['benchSuccess']} → {result['after']['benchSuccess']}")


if __name__ == "__main__":
    main()
