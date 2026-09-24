#!/usr/bin/env python3
"""Render the blog's silent, 16:9 case-comparison presentation as H.264 MP4.

Requires ffmpeg/ffprobe and the repository's Playwright installation.
All generated assets stay under artifacts/video unless --output is supplied.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import math
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS = 1920, 1080, 30
CASE_IDS = ("alphabet-soup", "book-compartment")
BOXES = {"left": {"x": 72, "y": 470, "width": 864, "height": 432},
         "right": {"x": 984, "y": 470, "width": 864, "height": 432}}


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revised_markup(case_id, instruction):
    escaped = html.escape(instruction)
    additions = ("blue-and-yellow", "can") if case_id == "alphabet-soup" else (", between the two large side compartments",)
    for addition in additions:
        escaped_addition = html.escape(addition)
        if addition == "can":
            escaped = escaped.replace(" can ", " <strong>can</strong> ")
        else:
            if escaped_addition not in escaped:
                raise ValueError(f"Missing expected instruction addition: {addition}")
            escaped = escaped.replace(escaped_addition, f"<strong>{escaped_addition}</strong>")
    if html.unescape(escaped.replace("<strong>", "").replace("</strong>", "")) != instruction:
        raise ValueError("Instruction highlighting changed the original text")
    return escaped


def make_manifest(speed):
    media = read_json(ROOT / "data/libero-blog-media.json")
    review = read_json(ROOT / "data/libero-human-review.json")
    robotwin = read_json(ROOT / "data/robotwin-alignment-summary.json")
    cases, scenes = [], []
    start_frame = 0
    for case_id in CASE_IDS:
        pair = next(item for item in media["pairs"] if item["id"] == case_id)
        before, after = (media["clips"][pair[stage]] for stage in ("before", "after"))
        if before["nativeSuccess"] or before["agentAssessment"] != "visually_complete" or not after["nativeSuccess"]:
            raise ValueError(f"Invalid disagreement-to-success pair: {case_id}")
        if (before["seed"], before["initStateId"]) != (after["seed"], after["initStateId"]):
            raise ValueError(f"Unmatched initial state: {case_id}")
        for clip in (before, after):
            if sha256(ROOT / clip["video"]) != clip["media"]["videoSha256"]:
                raise ValueError(f"Video does not match its evidence hash: {clip['video']}")
        left_frames = math.ceil(before["durationSeconds"] / speed * FPS)
        reveal_frame = left_frames + FPS
        right_frames = math.ceil(after["durationSeconds"] / speed * FPS)
        total_frames = reveal_frame + right_frames + round(2.5 * FPS)
        case = {
            "id": case_id,
            "title": "Identify the intended can" if case_id == "alphabet-soup" else "Specify the intended compartment",
            "originalInstruction": before["instruction"],
            "revisedInstruction": after["instruction"],
            "revisionHtml": revised_markup(case_id, after["instruction"]),
            "beforeSuccesses": pair["beforeTask"]["successes"],
            "afterSuccesses": pair["afterTask"]["successes"],
            "episodes": pair["beforeTask"]["episodes"],
            "seed": before["seed"], "initStateId": before["initStateId"],
            "beforeVideo": before["video"], "afterVideo": after["video"],
            "beforeSourceSeconds": before["durationSeconds"],
            "afterSourceSeconds": after["durationSeconds"],
            "leftFrames": left_frames, "revealFrame": reveal_frame,
            "rightFrames": right_frames, "frames": total_frames,
        }
        cases.append(case)
        scenes.append({"id": case_id, "kind": "case", "startFrame": start_frame,
                       "frames": total_frames, "rightRevealFrame": start_frame + reveal_frame})
        start_frame += total_frames
    for scene_id in ("results-libero", "results-robotwin", "takeaways"):
        frames = 18 * FPS
        scenes.append({"id": scene_id, "kind": "slide", "startFrame": start_frame, "frames": frames})
        start_frame += frames
    return {
        "width": WIDTH, "height": HEIGHT, "fps": FPS, "playbackSpeed": speed,
        "videoBoxes": BOXES, "audio": False, "subtitles": False,
        "cases": cases,
        "libero": {stage: review[stage] for stage in ("before", "after")},
        "robotwin": {**{stage: robotwin[stage] for stage in ("before", "after")},
                     "comparisonScope": robotwin["comparisonScope"]},
        "scenes": scenes, "frames": start_frame, "durationSeconds": start_frame / FPS,
        "sources": {str(path.relative_to(ROOT)): sha256(path) for path in (
            ROOT / "data/libero-blog-media.json", ROOT / "data/libero-human-review.json",
            ROOT / "data/robotwin-alignment-summary.json")},
    }


def run_logged(command, log_path):
    with log_path.open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"Command failed; see {log_path}\n" + log_path.read_text()[-6000:])


def encode_options(frames):
    return ["-an", "-sn", "-frames:v", str(frames), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "4",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def render_case(case, speed, work):
    scene_id = case["id"]
    output = work / f"{scene_id}.mp4"
    duration = case["frames"] / FPS
    reveal = case["revealFrame"] / FPS
    # The complete original recording plays first, then holds its final frame.
    # The revised panel and recording fade in together; neither clip is cropped.
    graph = (
        f"[0:v]format=yuv420p,setpts=PTS-STARTPTS[base];"
        f"[1:v]format=rgba,setpts=PTS-STARTPTS,fade=t=in:st={reveal}:d=0.4:alpha=1[panel];"
        f"[base][panel]overlay=0:0:shortest=1[background];"
        f"[2:v]setpts=(PTS-STARTPTS)/{speed},fps={FPS},scale=864:432:flags=lanczos,setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={duration}[left];"
        f"[background][left]overlay=72:470:eof_action=repeat[withleft];"
        f"[3:v]setpts=(PTS-STARTPTS)/{speed},fps={FPS},scale=864:432:flags=lanczos,setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={duration},format=rgba,"
        f"fade=t=in:st=0:d=0.4:alpha=1,setpts=PTS+{reveal}/TB[right];"
        f"[withleft][right]overlay=984:470:enable='gte(t,{reveal})':eof_action=repeat,"
        "format=yuv420p[out]"
    )
    command = ["ffmpeg", "-y", "-hide_banner", "-filter_complex_threads", "2",
               "-loop", "1", "-framerate", str(FPS), "-i", str(work / "cases" / f"{scene_id}-before.png"),
               "-loop", "1", "-framerate", str(FPS), "-i", str(work / "cases" / f"{scene_id}-after.png"),
               "-i", str(ROOT / case["beforeVideo"]), "-i", str(ROOT / case["afterVideo"]),
               "-filter_complex", graph, "-map", "[out]", *encode_options(case["frames"]), str(output)]
    run_logged(command, work / f"{scene_id}.ffmpeg.log")
    print(f"Rendered {scene_id}: {duration:.2f}s", flush=True)
    return output


def render_still(scene, work):
    output = work / f"{scene['id']}.mp4"
    command = ["ffmpeg", "-y", "-hide_banner", "-loop", "1", "-framerate", str(FPS),
               "-i", str(work / f"{scene['id']}.png"),
               *encode_options(scene["frames"]), str(output)]
    run_logged(command, work / f"{scene['id']}.ffmpeg.log")
    print(f"Rendered {scene['id']}: {scene['frames'] / FPS:.2f}s", flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/video/blog-showcase.mp4")
    parser.add_argument("--speed", type=float, default=2.0, help="Playback speed, visibly labeled on case pages")
    parser.add_argument("--prepare-only", action="store_true", help="Write the manifest without rendering")
    args = parser.parse_args()
    if not 0.25 <= args.speed <= 4:
        parser.error("--speed must be between 0.25 and 4")
    output = args.output.resolve()
    if output.suffix.lower() != ".mp4":
        parser.error("--output must end in .mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    manifest = make_manifest(args.speed)
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Prepared {manifest['durationSeconds']:.2f}s, {WIDTH}×{HEIGHT}, {FPS} fps; silent, no subtitle track.", flush=True)
    if args.prepare_only:
        return
    subprocess.run(["node", str(ROOT / "scripts/render_blog_video_slides.cjs"),
                    "--manifest", str(manifest_path), "--output", str(work)], check=True, cwd=ROOT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(render_case, case, args.speed, work) for case in manifest["cases"]]
        tasks += [pool.submit(render_still, scene, work) for scene in manifest["scenes"] if scene["kind"] == "slide"]
        parts = [task.result() for task in tasks]
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{part.name}'\n" for part in parts))
    run_logged(["ffmpeg", "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-map", "0:v:0", "-c", "copy", "-an", "-sn", "-movflags", "+faststart", str(output)],
               work / "concat.ffmpeg.log")
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", str(output)], text=True))
    streams = probe["streams"]
    if len(streams) != 1 or streams[0]["codec_type"] != "video":
        raise RuntimeError("The output must have exactly one video stream and no audio/subtitles")
    video = streams[0]
    if (video["width"], video["height"], video["pix_fmt"]) != (WIDTH, HEIGHT, "yuv420p"):
        raise RuntimeError("Unexpected output geometry or pixel format")
    if abs(float(probe["format"]["duration"]) - manifest["durationSeconds"]) > 1 / FPS:
        raise RuntimeError("Output duration differs from the storyboard")
    (work / "output-probe.json").write_text(json.dumps(probe, indent=2) + "\n")
    print(f"Video ready: {output} ({output.stat().st_size / 1_000_000:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
