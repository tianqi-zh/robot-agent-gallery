"""Protect task/source identity and unavailable-demo behavior with synthetic assets."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_gallery import ValidationError, validate_training_demos


@pytest.fixture
def catalog(tmp_path):
    task_id = 'robocasa_example'
    missing_id = 'robocasa_missing'
    gallery = {'benchmarks': [{'id': 'robocasa', 'tasks': [{'id': task_id}, {'id': missing_id}]}]}
    payload = b'synthetic media for metadata tests only'
    digest = hashlib.sha256(payload).hexdigest()
    record = {'taskId': task_id, 'benchmark': 'robocasa', 'status': 'available',
              'source': {'dataset': 'Synthetic fixture', 'url': 'https://example.invalid/dataset',
                         'relativePath': 'Example/episode_000000.mp4', 'episode': 0, 'taskName': 'Example'},
              'frames': 20, 'fps': 20, 'durationSeconds': 1, 'width': 256, 'height': 256,
              'cameras': ['Main view']}
    for key, suffix in [('video', '.mp4'), ('poster', '.jpg')]:
        relative = f'media/demos/robocasa/{task_id}{suffix}'
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        record.update({key: relative, f'{key}Sha256': digest, f'{key}Bytes': len(payload)})
    data = {'schemaVersion': 1, 'coverage': {'robocasa': {'tasks': 2, 'available': 1, 'unavailable': 1}},
            'tasks': {task_id: record, missing_id: {
                'taskId': missing_id, 'benchmark': 'robocasa', 'status': 'unavailable',
                'reason': 'No released training demonstration for this task',
                'source': {'dataset': 'Synthetic fixture', 'url': 'https://example.invalid/dataset'}}}}
    (tmp_path / 'data').mkdir()

    def validate(value=None):
        (tmp_path / 'data/task-demos.json').write_text(json.dumps(data if value is None else value))
        return validate_training_demos(tmp_path, gallery, required=True)

    return tmp_path, gallery, data, validate


def test_reference_video_does_not_add_evaluation_episodes(catalog):
    _, gallery, data, validate = catalog
    before = deepcopy(gallery)
    coverage, videos, paths = validate()
    assert gallery == before
    assert coverage == data['coverage']
    assert len(videos) == 1 and len(paths) == 2


@pytest.mark.parametrize('corruption', ['wrong_task', 'missing_task', 'unavailable_video',
                                       'source_task', 'media_path', 'duration', 'hash', 'coverage'])
def test_rejects_misattribution_and_false_media_claims(catalog, corruption):
    _, _, original, validate = catalog
    data = deepcopy(original)
    record = data['tasks']['robocasa_example']
    if corruption == 'wrong_task':
        record['taskId'] = 'robocasa_missing'
    elif corruption == 'missing_task':
        del data['tasks']['robocasa_missing']
    elif corruption == 'unavailable_video':
        data['tasks']['robocasa_missing']['video'] = record['video']
    elif corruption == 'source_task':
        record['source']['taskName'] = 'DifferentTask'
    elif corruption == 'media_path':
        record['video'] = 'media/robocasa/robocasa_example_r00.mp4'
    elif corruption == 'duration':
        record['durationSeconds'] = 5
    elif corruption == 'hash':
        record['videoSha256'] = '0' * 64
    else:
        data['coverage']['robocasa']['available'] = 2
    with pytest.raises(ValidationError):
        validate(data)


def test_required_catalog_cannot_silently_disappear(tmp_path):
    assert validate_training_demos(tmp_path, {'benchmarks': []}) == (None, [], set())
    with pytest.raises(ValidationError, match='required'):
        validate_training_demos(tmp_path, {'benchmarks': []}, required=True)
