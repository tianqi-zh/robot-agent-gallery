#!/usr/bin/env python3
"""Assemble independently exported benchmark demonstrations into a public catalog."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from validate_gallery import validate_training_demos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--records', type=Path, help='Directory containing benchmark JSON export records')
    args = parser.parse_args()
    root = args.root.resolve()
    records_directory = args.records or root / 'artifacts/task-demos'
    gallery = json.loads((root / 'data/gallery.json').read_text())
    tasks, coverage = {}, {}
    for benchmark in gallery['benchmarks']:
        benchmark_id = benchmark['id']
        records = json.loads((records_directory / f'{benchmark_id}.json').read_text())
        if not isinstance(records, list):
            raise ValueError(f'{benchmark_id}: expected a list of exported task records')
        expected = {task['id'] for task in benchmark['tasks']}
        actual = [record['taskId'] for record in records]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError(f'{benchmark_id}: duplicate or incomplete task mapping')
        if any(record['benchmark'] != benchmark_id for record in records):
            raise ValueError(f'{benchmark_id}: records contain another benchmark')
        by_id = {record['taskId']: record for record in records}
        tasks.update((task['id'], by_id[task['id']]) for task in benchmark['tasks'])
        statuses = Counter(record['status'] for record in records)
        coverage[benchmark_id] = {'tasks': len(expected), 'available': statuses['available'],
                                  'unavailable': statuses['unavailable']}
    catalog = {'schemaVersion': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
               'coverage': coverage, 'tasks': tasks}
    destination = root / 'data/task-demos.json'
    previous = destination.read_bytes() if destination.exists() else None
    temporary = destination.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(destination)
    try:
        validate_training_demos(root, gallery, required=True)
    except Exception:
        if previous is None:
            destination.unlink()
        else:
            destination.write_bytes(previous)
        raise
    print(json.dumps(coverage, indent=2))


if __name__ == '__main__':
    main()
