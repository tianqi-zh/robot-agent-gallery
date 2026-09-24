"""Guard source selection, recording preservation and HF metadata semantics."""
import importlib.util
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/export_benchmend_libero.py'
SPEC = importlib.util.spec_from_file_location('benchmend_export', SCRIPT)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


def write_attempt(root, name, status):
    path = root / name / 'result.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': status}))
    return path.parent


def test_infrastructure_retry_does_not_replace_or_duplicate_scored_episode(tmp_path):
    write_attempt(tmp_path, 'attempt_001', 'error')
    scored = write_attempt(tmp_path, 'attempt_002', 'failure')
    attempt, result, excluded = export.unique_valid_attempt(tmp_path)
    assert attempt == scored
    assert result['status'] == 'failure'
    assert excluded == [{'attempt': 'attempt_001', 'status': 'error'}]
    write_attempt(tmp_path, 'attempt_003', 'success')
    with pytest.raises(ValueError, match='exactly one valid'):
        export.unique_valid_attempt(tmp_path)


@pytest.mark.parametrize('value', [
    {'sourceVideo': '/playpen/tianqi/private/rollout.mp4'},
    {'nested': {'auth_json': 'secret'}},
    {'source': '/home/user/.cache/auth'},
])
def test_host_paths_and_private_trace_fields_are_rejected(value):
    with pytest.raises(ValueError, match='Private content'):
        export.check_public(value)


def test_video_folder_metadata_has_real_video_feature_and_relative_paths(tmp_path):
    rows = []
    for stage in export.PUBLIC_STAGES:
        (tmp_path / stage).mkdir()
        rows.append({'id': stage + '/episode', 'stage': stage,
                     'video': stage + '/videos/episode.mp4',
                     'poster': stage + '/posters/episode.jpg',
                     'nativeSuccess': False, 'agentSuccess': None})
    export.write_public_files(tmp_path, rows, [], {})
    for stage in export.PUBLIC_STAGES:
        item = json.loads((tmp_path / stage / 'metadata.jsonl').read_text())
        assert item['file_name'] == 'videos/episode.mp4'
        assert item['poster'] == 'posters/episode.jpg'
        assert 'video' not in item  # VideoFolder generates the decoded Video feature.
        assert item['agentSuccess'] is None
    assert json.loads((tmp_path / 'episodes.json').read_text()) == rows
    card = (tmp_path / 'README.md').read_text()
    assert 'split: original' in card and 'split: revision' in card
    assert 'split: revised_r1' not in card and 'split: revised_r2' not in card


def test_public_revision_replaces_whole_tasks_and_preserves_all_originals():
    reference, final, _ = export.load_reference(SCRIPT.parents[1])
    stage_names = {config[0]: stage for stage, config in export.SOURCE_STAGES.items()}
    sources = []
    for (audit_stage, pair), expected in reference.items():
        stage = stage_names[audit_stage]
        sources.append({'source': Path(expected['runName']) / pair / 'video.mp4',
                        'expectedFrames': 100, 'row': {
                            'id': f'{stage}/{pair}', 'stage': stage, 'pairKey': pair,
                            'video': f'{stage}/videos/{pair}.mp4',
                            'poster': f'{stage}/posters/{pair}.jpg',
                            'sourceRun': expected['runName'],
                            'sourceResultSha256': expected['resultSha256'],
                            'sourceFinishSha256': expected['finishSha256'],
                            'instruction': expected['instruction'],
                            'nativeSuccess': expected['nativeSuccess'],
                            'final': (audit_stage, pair) in final,
                            'sha256': f'{stage}/{pair}', 'bytes': 1,
                        }})
    before = deepcopy(sources)
    selected = export.select_public_sources(sources)
    assert sources == before  # Source metadata must also remain untouched.
    assert len(selected) == 490
    originals = [source for source in selected if source['row']['stage'] == 'original']
    assert originals == [source for source in sources if source['row']['stage'] == 'original']
    revisions = [source for source in selected if source['row']['stage'] == 'revision']
    assert len(revisions) == 90
    latest_run = export.SOURCE_STAGES['revised_r2'][1]
    latest = [source for source in revisions if source['row']['sourceRun'] == latest_run]
    assert Counter(source['row']['pairKey'].rsplit('_r', 1)[0] for source in latest) == {
        'libero_goal_t05': 10, 'libero_10_t05': 10,
    }
    assert {source['row']['pairKey'] for source in latest} == {
        f'{task}_r{index:02d}' for task in ('libero_goal_t05', 'libero_10_t05')
        for index in range(10)
    }
    first_run = export.SOURCE_STAGES['revised_r1'][1]
    retained = [source for source in revisions if source['row']['sourceRun'] == first_run]
    assert Counter(source['row']['pairKey'].rsplit('_r', 1)[0] for source in retained) == {
        'libero_spatial_t04': 10, 'libero_goal_t00': 10, 'libero_goal_t09': 10,
        'libero_object_t00': 10, 'libero_object_t04': 10,
        'libero_10_t06': 10, 'libero_10_t07': 10,
    }
    by_source = {(source['row']['sourceRun'], source['row']['pairKey']): source
                 for source in sources}
    for source in revisions:
        row = source['row']
        original_source = by_source[(row['sourceRun'], row['pairKey'])]
        assert source['source'] == original_source['source']
        assert source['expectedFrames'] == original_source['expectedFrames']
        for field in row.keys() - {'id', 'stage', 'video', 'poster'}:
            assert row[field] == original_source['row'][field]
        assert row['id'] == f'revision/{row["pairKey"]}'
        assert row['video'] == f'revision/videos/{row["pairKey"]}.mp4'
        assert row['poster'] == f'revision/posters/{row["pairKey"]}.jpg'
    summary = export.summarize([source['row'] for source in selected])
    assert summary['nativeSuccessCounts'] == {'original': 322, 'revision': 75}
    assert summary['finalComposite']['stageCounts'] == {'original': 310, 'revision': 90}
    assert summary['finalComposite']['nativeSuccess'] == 357


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
                    reason='Full video preservation check requires ffmpeg/ffprobe')
def test_export_preserves_video_bytes_and_rejects_missing_frames(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=green:s=1024x512:r=20', '-frames:v', '20',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-threads', '1',
                    str(source)], check=True)
    original_bytes = source.read_bytes()
    record = {'row': {'id': 'original/episode', 'video': 'original/videos/episode.mp4',
                      'poster': 'original/posters/episode.jpg'},
              'source': source, 'expectedFrames': 20}
    output = tmp_path / 'public'
    row = export.export_episode(record, output)
    assert (output / row['video']).read_bytes() == source.read_bytes() == original_bytes
    assert row['sha256'] == row['sourceVideoSha256'] == export.sha256(source)
    assert row['duration'] == 1 and row['frames'] == 20
    assert (output / row['poster']).is_file()
    record['expectedFrames'] = 21
    with pytest.raises(ValueError, match='Incomplete recording'):
        export.export_episode(record, output)
