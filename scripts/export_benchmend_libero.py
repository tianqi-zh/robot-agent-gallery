#!/usr/bin/env python3
"""Export 400 original and 90 final-revision LIBERO videos as an HF VideoFolder.

Source runs are read-only. Videos are copied byte-for-byte, decoded and hashed;
only a strict public metadata schema and generated posters leave the archive.
The final 400-slot comparison is a view, never 400 fabricated revision videos.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = Path('/playpen/tianqi/code/robot-agent/eval_runs')
DEFAULT_OUTPUT = Path('/playpen-ssd/tianqizh/benchmend-libero-merged')
SOURCE_STAGES = {
    'original': ('baseline', 'astra_libero_v5_calibrated_parallel10_r4', 400),
    'revised_r1': ('round1', 'astra_libero_v5_instruction_refined_parallel8_r1', 90),
    'revised_r2': ('round2', 'astra_libero_v5_instruction_minimal_parallel4_r2', 20),
}
PUBLIC_STAGES = {'original': 400, 'revision': 90}
PAIR_FIELDS = ('suite', 'task_id', 'task_name', 'rollout_id', 'init_state_id',
               'seed', 'bddl_sha256', 'init_sha256')
EXPECTED_SOURCE_SUCCESS = {'original': 322, 'revised_r1': 63, 'revised_r2': 12}
EXPECTED_SUCCESS = {'original': 322, 'revision': 75}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def manifest_hash(manifest):
    value = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_reference(root):
    """Bind every actual source to the already audited article's public CSV."""
    with (root / 'data/libero-alignment-episodes.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 400, 'The audited comparison must contain 400 slots')
    reference, final = {}, set()
    for row in rows:
        for prefix in ('before', 'round1', 'after'):
            key = row[prefix + 'Stage'], row['episodeKey']
            expected = {
                'instruction': row[prefix + 'Instruction'],
                'nativeSuccess': row[prefix + 'BenchSuccess'] == 'True',
                'resultSha256': row[prefix + 'ResultSha256'],
                'finishSha256': row[prefix + 'FinishSha256'] or None,
                'runName': row[prefix + 'RunName'],
                'attempt': row[prefix + 'Attempt'],
            }
            require(row[prefix + 'BenchSuccess'] in ('True', 'False'), 'Invalid audited native score')
            require(key not in reference or reference[key] == expected,
                    f'Conflicting audited source: {key}')
            reference[key] = expected
        final.add((row['afterStage'], row['episodeKey']))
    require(len(reference) == 510 and len(final) == 400, 'Wrong audited source/composite count')
    review = read_json(root / 'data/libero-human-review.json')
    corrections = {(item['stage'], item['episodeKey']): item for item in review['corrections']}
    return reference, final, corrections


def unique_valid_attempt(episode_dir):
    attempts = sorted(episode_dir.glob('attempt_*/result.json'))
    valid, excluded = [], []
    for path in attempts:
        result = read_json(path)
        if result['status'] in ('success', 'failure'):
            valid.append((path.parent, result))
        else:
            require(result['status'] in ('error', 'interrupted', 'timeout'),
                    f'Unrecognized attempt status: {path}')
            excluded.append({'attempt': path.parent.name, 'status': result['status']})
    require(len(valid) == 1, f'Need exactly one valid evaluation attempt: {episode_dir}')
    require(valid[0][0] == attempts[-1].parent, f'A later invalid attempt exists: {episode_dir}')
    return *valid[0], excluded


def collect_sources(run_root, root):
    reference, final, corrections = load_reference(root)
    sources, provenance, originals = [], [], {}
    for stage, (audit_stage, run_name, expected_count) in SOURCE_STAGES.items():
        run = run_root / run_name
        manifest_path = run / 'manifest.json'
        manifest = read_json(manifest_path)
        require(manifest_hash(manifest) == manifest['manifest_sha256'], 'Manifest integrity failure')
        require(len(manifest['episodes']) == expected_count, f'Wrong count for {run_name}')
        require(len({item['episode_key'] for item in manifest['episodes']}) == expected_count,
                f'Duplicate episode key in {run_name}')
        excluded_attempts = []
        for spec in manifest['episodes']:
            key = spec['episode_key']
            require('/' not in key and '..' not in key and spec['suite'].startswith('libero_'),
                    'Unsafe or non-LIBERO episode identity')
            attempt, result, excluded = unique_valid_attempt(run / 'episodes' / key)
            excluded_attempts.extend({'episodeKey': key, **item} for item in excluded)
            native = result['success']
            require(type(native) is bool and native == (result['status'] == 'success'),
                    f'Invalid native score for {key}')
            environment = read_json(attempt / 'env_result.json')
            require(environment['success'] == native and environment['steps'] == result['steps'],
                    f'Environment score mismatch for {key}')
            actual_spec = read_json(attempt / 'spec.json')
            require(all(actual_spec.get(field) == value for field, value in spec.items()),
                    f'Attempt spec mismatch for {key}')
            for record in (result, environment, actual_spec):
                require(record['episode_key'] == key
                        and record['manifest_sha256'] == manifest['manifest_sha256'],
                        f'Source linkage mismatch for {key}')
            for field in ('suite', 'task_id', 'init_state_id', 'seed'):
                require(environment[field] == spec[field], f'Environment identity mismatch for {key}')
            if stage == 'original':
                originals[key] = spec
            else:
                require(key in originals, f'Revision without an original episode: {key}')
                require(all(spec[field] == originals[key][field] for field in PAIR_FIELDS),
                        f'Revision changes pairing fields: {key}')
                require(spec['language'] != originals[key]['language'],
                        f'Revision has no instruction change: {key}')
            video_info = result['environment']['video']
            video = Path(video_info['path'])
            require(video.is_file() and video.resolve().is_relative_to(attempt.resolve()),
                    f'Missing or unrelated video for {key}')
            require(video_info['codec'] == 'h264' and video_info.get('error') is None,
                    f'Invalid archived encoder result for {key}')
            finish_path = attempt / 'finish_assessment.json'
            finish = read_json(finish_path) if finish_path.exists() else {}
            outcome = finish.get('outcome')
            require(outcome in (None, 'visually_complete', 'unable_to_continue'),
                    f'Unexpected explicit agent outcome for {key}')
            result_hash = sha256(attempt / 'result.json')
            finish_hash = sha256(finish_path) if finish_path.exists() else None
            expected = reference[(audit_stage, key)]
            require(expected == {'instruction': spec['language'], 'nativeSuccess': native,
                                 'resultSha256': result_hash, 'finishSha256': finish_hash,
                                 'runName': run_name, 'attempt': attempt.name},
                    f'Source differs from published audit: {stage}/{key}')
            correction = corrections.get((audit_stage, key))
            if correction:
                require(correction['sourceResultSha256'] == result_hash
                        and correction['sourceFinishSha256'] == finish_hash
                        and correction['sourceManifestSha256'] == manifest['manifest_sha256'],
                        f'Human correction source mismatch for {key}')
            agent_success = {'visually_complete': True, 'unable_to_continue': False, None: None}[outcome]
            row = {
                'id': f'{stage}/{key}', 'stage': stage, 'pairKey': key,
                'suite': spec['suite'], 'taskId': spec['task_id'], 'taskName': spec['task_name'],
                'initStateIndex': spec['init_state_id'], 'seed': spec['seed'],
                'rolloutId': spec['rollout_id'], 'instruction': spec['language'],
                'originalInstruction': originals[key]['language'], 'nativeSuccess': native,
                'agentSuccess': agent_success, 'agentOutcome': outcome,
                'presentationAgentSuccess': False if correction else native or outcome == 'visually_complete',
                'humanCorrection': bool(correction),
                'final': (audit_stage, key) in final, 'steps': result['steps'],
                'video': f'{stage}/videos/{key}.mp4', 'poster': f'{stage}/posters/{key}.jpg',
                'sourceRun': run_name, 'sourceAttempt': attempt.name,
                'sourceManifestSha256': manifest['manifest_sha256'],
                'sourceResultSha256': result_hash, 'sourceFinishSha256': finish_hash,
                'sourceVideo': video.resolve().relative_to(run.resolve()).as_posix(),
            }
            sources.append({'row': row, 'source': video, 'expectedFrames': video_info['frames']})
        provenance.append({
            'stage': 'original' if stage == 'original' else 'revision',
            'runName': run_name, 'episodeCount': expected_count,
            'publishedEpisodeCount': sum(item['row']['sourceRun'] == run_name
                                         and (stage == 'original' or item['row']['final'])
                                         for item in sources),
            'manifestSha256': manifest['manifest_sha256'],
            'manifestFileSha256': sha256(manifest_path),
            'requestedModel': manifest['config']['model'],
            'reasoningEffort': manifest['config']['reasoning_effort'],
            'liberoCommit': manifest['provenance']['libero_commit'],
            'excludedInfrastructureAttempts': excluded_attempts,
        })
    require(len(sources) == 510, 'Wrong number of actual source episodes')
    source_success = {stage: sum(item['row']['nativeSuccess'] for item in sources
                                if item['row']['stage'] == stage)
                      for stage in SOURCE_STAGES}
    require(source_success == EXPECTED_SOURCE_SUCCESS,
            'Native archived source success totals differ from the audit')
    return select_public_sources(sources), provenance


def select_public_sources(sources):
    """Publish every original and only the article's audited final revision.

    The later run replaces all ten initial states for two tasks, regardless of
    success. Selection follows the audited afterStage, not a best-of outcome.
    """
    selected = []
    for source in sources:
        row = source['row']
        if row['stage'] != 'original' and not row['final']:
            continue
        stage = 'original' if row['stage'] == 'original' else 'revision'
        public_row = dict(row, stage=stage, id=f'{stage}/{row["pairKey"]}',
                          video=f'{stage}/videos/{row["pairKey"]}.mp4',
                          poster=f'{stage}/posters/{row["pairKey"]}.jpg')
        selected.append(dict(source, row=public_row))
    require(dict(Counter(item['row']['stage'] for item in selected)) == PUBLIC_STAGES,
            'Public export must contain 400 original and 90 final revision videos')
    require(len({item['row']['id'] for item in selected}) == len(selected),
            'Duplicate public episode identity')
    return selected


def check_public(value):
    """Reject accidental private paths or raw trace payloads in exported metadata."""
    text = json.dumps(value, ensure_ascii=False)
    for forbidden in ('/playpen/', '/playpen-ssd/', '/home/', 'codex_events',
                      'auth_json', 'thread_ids', 'prompt_template', 'chain_of_thought'):
        require(forbidden not in text, f'Private content in public metadata: {forbidden}')


def run_checked(command):
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    require(not result.stderr.strip(), f'Media validation emitted an error: {result.stderr[:400]}')
    return result.stdout


def export_episode(source, output):
    row = dict(source['row'])
    original = source['source']
    video, poster = output / row['video'], output / row['poster']
    video.parent.mkdir(parents=True, exist_ok=True)
    poster.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(original)
    if not video.exists() or sha256(video) != source_hash:
        shutil.copyfile(original, video)
    require(sha256(video) == source_hash, f'Video changed during copy: {row["id"]}')
    # -count_frames decodes the full video, so truncated or corrupt final segments
    # cannot pass a metadata-only header check. Only errors are printed by ffprobe.
    probe = json.loads(run_checked([
        'ffprobe', '-v', 'error', '-threads', '1', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', str(video),
    ]))
    streams = probe['streams']
    require(len(streams) == 1 and streams[0]['codec_type'] == 'video', 'Unexpected extra media stream')
    stream = streams[0]
    require(stream['codec_name'] == 'h264' and stream['pix_fmt'] == 'yuv420p', 'Non-browser video format')
    require(int(stream['nb_read_frames']) == source['expectedFrames'],
            f'Incomplete recording: {row["id"]}')
    fps = float(Fraction(stream['avg_frame_rate']))
    duration = float(probe['format']['duration'])
    require(fps == 20 and stream['width'] == 1024 and stream['height'] == 512,
            f'Unexpected original recording shape: {row["id"]}')
    require(abs(duration - source['expectedFrames'] / fps) < .051, 'Frame count/duration mismatch')
    run_checked([
        'ffmpeg', '-v', 'error', '-y', '-threads', '1', '-ss', str(min(1.0, duration / 10)),
        '-i', str(video), '-frames:v', '1', '-vf', 'scale=640:320', '-q:v', '3',
        '-threads', '1', '-update', '1', str(poster),
    ])
    row.update({
        'width': stream['width'], 'height': stream['height'], 'fps': fps,
        'duration': duration, 'frames': int(stream['nb_read_frames']),
        'bytes': video.stat().st_size, 'sha256': source_hash, 'sourceVideoSha256': source_hash,
        'posterSha256': sha256(poster),
    })
    check_public(row)
    return row


def summarize(rows):
    selected = [row for row in rows if row['final']]
    require(len({row['pairKey'] for row in selected}) == len(selected) == 400,
            'Final composite must contain one source per original slot')
    counts = dict(Counter(row['stage'] for row in rows))
    require(counts == PUBLIC_STAGES, 'Wrong split counts')
    success = {stage: sum(row['nativeSuccess'] for row in rows if row['stage'] == stage)
               for stage in PUBLIC_STAGES}
    require(success == EXPECTED_SUCCESS, 'Native source success totals differ from the audit')
    require(sum(row['nativeSuccess'] for row in selected) == 357, 'Wrong final success total')
    final_counts = dict(Counter(row['stage'] for row in selected))
    require(final_counts == {'original': 310, 'revision': 90},
            'Wrong final composite source composition')
    require(len({row['sha256'] for row in rows}) == 490, 'Duplicate source recordings')
    return {
        'episodes': len(rows), 'originalEpisodes': 400, 'revisedEpisodes': 90,
        'stageCounts': counts, 'nativeSuccessCounts': success,
        'finalComposite': {'episodes': 400, 'stageCounts': final_counts,
                           'nativeSuccess': 357, 'nativeSuccessRate': 357 / 400},
        'originalNativeSuccess': 322, 'originalNativeSuccessRate': 322 / 400,
        'videoBytes': sum(row['bytes'] for row in rows),
    }


DATASET_CARD = """---
pretty_name: BenchMend LIBERO Evaluation Videos
language:
- en
tags:
- robotics
- libero
- benchmark
- evaluation
- video
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: original
    path:
    - original/videos/*.mp4
    - original/metadata.jsonl
  - split: revision
    path:
    - revision/videos/*.mp4
    - revision/metadata.jsonl
---

# BenchMend: LIBERO evaluation videos

**BenchMend: Agent-Guided Instruction Repair for Robotics Benchmarks.**

This dataset contains **490 actual LIBERO evaluation recordings**: **400 with
the original task instructions** and **90 with the final revised instructions**.
It contains LIBERO only.
These are evaluation rollouts, not LIBERO training demonstrations or a new
training split. The native benchmark success checker was not changed.

[Browse and play the gallery](https://huggingface.co/spaces/benchmend/gallery).

| Split | Actual videos | Tasks | Native successes |
| --- | ---: | ---: | ---: |
| `original` | 400 | 40 | 322 |
| `revision` | 90 | 9 | 75 |

The original evaluation covers four suites (`libero_spatial`, `libero_object`,
`libero_goal`, `libero_10`), ten tasks per suite and ten initial states per task.
Revised runs use the same corresponding task, initial state, seed and native
goal specification. Only tasks receiving an instruction edit were rerun.

## Actual reruns and the final comparison

There are **90 published revised-instruction videos**, not 400 new reruns.
The single `revision` split combines 70 recordings from the first revised run
with 20 recordings from the later run. For `libero_goal_t05` and `libero_10_t05`,
the later run replaces all ten initial states of the earlier revision. The
superseded 20 videos are excluded from this dataset; their archived source runs
remain unchanged. Selection follows the audited final instruction version for
each task, never the most successful rollout for an individual initial state.
The final 400-slot comparison selects **310 unchanged original recordings +
90 revision recordings**. `final: true` marks the 400 selected sources;
`pairKey` links recordings of the same evaluation slot.
Original native success is 322/400 (80.5%); the final composite is 357/400 (89.25%).
Do not treat the final composite as an independent 400-episode rerun.

## Files and loading

Each split contains original MP4 bytes in `videos/`, generated JPEG preview
images in `posters/`, and standard VideoFolder `metadata.jsonl` with a relative
`file_name` pointing to its video. All 490 source MP4s are copied
**byte-for-byte**: H.264, YUV420p, 1024 × 512, 20 fps. Their two camera views are
agent view on the left and wrist view on the right. Initial and warmup frames
are retained, with no cropping, speed changes, subtitles or added audio.

```python
from datasets import load_dataset

videos = load_dataset("benchmend/libero")
original = videos["original"]  # 400 actual recordings
revision = videos["revision"]  # 90 actual recordings, one revision per task
```

Root `episodes.json`, `episodes.jsonl` and `episodes.csv` provide the same 490
flat records for gallery use and metadata-only analysis. Paths in these root
files are relative to the dataset repository. The split metadata uses paths
relative to its own split folder. `metadata.json` gives counts and conventions;
`provenance.json` gives source-run identifiers and hashes. `checksums.sha256`
covers every public file except the checksum file itself.

## Metadata conventions

- `instruction` is the actual task instruction supplied in that run;
  `originalInstruction` preserves its original wording.
- `nativeSuccess` is the unmodified LIBERO environment success outcome.
- `agentSuccess` is an **explicit agent finish declaration**: true for
  `visually_complete`, false for `unable_to_continue`, and null when none was
  recorded. Null does not mean failure. Native success often terminates a run
  before an explicit finish declaration.
- `presentationAgentSuccess` follows the article's reporting convention:
  native successes count as successful; among native failures, an explicit
  completion claim counts as success unless corrected by confirmed human
  review. Other native failures count as failure under that convention.
  This field is not an independent ground-truth rating of every episode.
- `humanCorrection` marks the one confirmed second-round correction
  (`libero_goal_t05_r05`). Its raw explicit declaration remains unchanged.
  Confirmed disagreement review covers reported disagreements in the
  original/final comparison, not a full human rating of all 490 videos.
- `sourceRun`, `sourceAttempt` and `sourceVideo` are relative archive identifiers;
  source manifest/result/video hashes bind the public record to the archived
  run. Absolute host paths, prompts, raw agent traces, credentials and runtime
  configuration files are not included.
- `sha256` and `sourceVideoSha256` match because no video is re-encoded or remuxed.

The archived requested policy is `gpt-6-astra` with `high` reasoning effort.
This is the requested model identifier in the archived evaluation records;
the server-reported actual model is not independently exposed.

## Provenance and reproduction

The exporter `scripts/export_benchmend_libero.py` in the BenchMend project checks
the original manifest digest, native result/spec linkage, stage pairing, the
audited article CSV, every full video's decoded frame count and every copied
video's SHA-256. Invalid infrastructure attempts are excluded, never substituted
for valid scored episodes. Generated poster images are preview assets only.

LIBERO upstream: <https://github.com/Lifelong-Robot-Learning/LIBERO>.
VideoFolder format: <https://huggingface.co/docs/datasets/video_dataset>.
"""


def write_public_files(output, rows, provenance, summary):
    metadata = {
        'schemaVersion': 1, 'dataset': 'benchmend/libero', 'benchmark': 'LIBERO',
        'purpose': 'evaluation', 'summary': summary,
        'videoPreservation': 'byte-for-byte copy; no re-encoding or remuxing',
        'agentSuccessMeaning': 'Explicit finish declaration only; null means no declaration',
        'finalMeaning': '400-slot composite: 310 original + 90 revision',
        'gallery': 'https://huggingface.co/spaces/benchmend/gallery',
    }
    for item in (rows, metadata, provenance):
        check_public(item)
    write_json(output / 'episodes.json', rows)
    (output / 'episodes.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    with (output / 'episodes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / 'metadata.json', metadata)
    write_json(output / 'provenance.json', {'schemaVersion': 1, 'sources': provenance})
    for stage in PUBLIC_STAGES:
        stage_rows = []
        for row in rows:
            if row['stage'] != stage:
                continue
            item = {key: value for key, value in row.items() if key != 'video'}
            item['file_name'] = Path(row['video']).relative_to(stage).as_posix()
            item['poster'] = Path(row['poster']).relative_to(stage).as_posix()
            stage_rows.append(item)
        (output / stage / 'metadata.jsonl').write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in stage_rows))
    (output / 'README.md').write_text(DATASET_CARD)
    (output / '.gitattributes').write_text('*.mp4 filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n')
    public_files = sorted(path for path in output.rglob('*')
                          if path.is_file() and path.name != 'checksums.sha256')
    (output / 'checksums.sha256').write_text(''.join(
        f'{sha256(path)}  {path.relative_to(output).as_posix()}\n' for path in public_files))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=DEFAULT_RUNS)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args(argv)
    require(1 <= args.workers <= 32, 'Workers must be between 1 and 32')
    require(not args.output.resolve().is_relative_to(args.runs.resolve()),
            'Output must not modify archived source runs')
    require(not any((args.output / stage).exists() for stage in ('revised_r1', 'revised_r2')),
            'Use a clean output directory; old public revision folders must not be retained')
    sources, provenance = collect_sources(args.runs, args.root)
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(export_episode, source, args.output) for source in sources]
        for future in as_completed(pending):
            rows.append(future.result())
            if len(rows) % 25 == 0 or len(rows) == len(sources):
                print(f'Copied, decoded and verified {len(rows)}/{len(sources)} videos', flush=True)
    order = {stage: index for index, stage in enumerate(PUBLIC_STAGES)}
    rows.sort(key=lambda row: (order[row['stage']], row['suite'], row['taskId'], row['initStateIndex']))
    summary = summarize(rows)
    write_public_files(args.output, rows, provenance, summary)
    report_dir = args.root / 'artifacts/benchmend'
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / 'export-report.json', {
        'output': str(args.output), 'summary': summary, 'allVideosFullyDecoded': True,
        'allVideoBytesIdentical': True, 'videoCount': len(rows), 'posterCount': len(rows),
        'publicFileCount': len([p for p in args.output.rglob('*') if p.is_file()]),
    })
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
