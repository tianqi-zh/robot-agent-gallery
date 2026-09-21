#!/usr/bin/env python3
"""Recompute the essay's reviewed labels without changing archived agent reports.

Only user-confirmed human corrections are applied. Corrections bind to an
episode *and source stage* and to the archived result/finish hashes. Benchmark
labels never change. --write regenerates derived fields but cannot confirm a
review; --require-complete is the publication gate for confirmed coverage.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys

from validate_libero_blog import (
    PREFIXES, R1_TASKS, R2_TASKS, ValidationError, boolean, check_public,
    exact, require, sha256, validate_alignment,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = 'data/libero-human-review.json'
SOURCE_PATHS = {
    'alignment': 'data/libero-alignment.json',
    'episodes': 'data/libero-alignment-episodes.csv',
}
METADATA_FIELDS = {
    'schemaVersion', 'reviewScope', 'reviewCoverageStatus', 'coveragePanels',
    'unchangedDisagreementsConfirmed', 'reviewNote', 'corrections',
}
DERIVED_FIELDS = {
    'sourceFiles', 'reportingRule', 'reviewCoverageSummary', 'before', 'round1',
    'after', 'rerunSubset', 'finalRoundSubset',
}
CORRECTION_FIELDS = {
    'stage', 'episodeKey', 'originalAgentOutcome', 'originalAgentLabel',
    'reviewedAgentLabel', 'nativeSuccess', 'sourceRunName',
    'sourceManifestSha256', 'sourceResultSha256', 'sourceFinishSha256',
    'reason', 'decisionBasis',
}
REPORTING_RULE = {
    'iasFormula': '1 - count(reviewed agent success AND native benchmark failure) / N',
    'nativeSuccess': 'Accept every native benchmark success as agent success under the presentation convention; this is not an explicit agent declaration or a human rating.',
    'nativeFailure': 'Start from the explicit visually_complete claim, if present, then apply only a confirmed, source-matched human correction. Other native failures count as agent failure under the reporting convention.',
    'unassessedNativeFailure': 'A native failure without a finish declaration is assigned to agent failure because no completion was declared; this is not a human assessment of the terminal image.',
    'notApplicableCell': 'agent failure / benchmark success',
    'notApplicableSymbol': '\\',
    'nativeOutcomesChanged': False,
    'archivedAgentReportsChanged': False,
    'pendingReview': 'Unconfirmed disagreements retain their archived completion claim provisionally. Pending coverage must not be presented as a completed human rating.',
}


def load_sources(root):
    alignment = json.loads((root / SOURCE_PATHS['alignment']).read_text())
    with (root / SOURCE_PATHS['episodes']).open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    fingerprints = {
        key: {'path': path, 'sha256': sha256(root / path)}
        for key, path in SOURCE_PATHS.items()
    }
    return alignment, rows, fingerprints


def identity(row, prefix):
    return row[prefix + 'Stage'], row['episodeKey']


def validate_metadata(review, alignment, rows):
    require(set(review) <= METADATA_FIELDS | DERIVED_FIELDS,
            'Unexpected human-review fields')
    require(METADATA_FIELDS <= set(review), 'Missing human-review metadata')
    require(review['schemaVersion'] == 1, 'Unsupported human-review schema')
    require(review['reviewScope'] == 'agent-benchmark disagreement videos',
            'Review scope must remain limited to disagreement videos')
    require(review['coveragePanels'] == ['before', 'after'],
            'Coverage confirmation applies to the before/after comparison')
    require(review['reviewCoverageStatus'] in ('pending_confirmation', 'complete'),
            'Invalid review coverage status')
    require(type(review['unchangedDisagreementsConfirmed']) is bool,
            'Coverage confirmation must be a boolean')
    require((review['reviewCoverageStatus'] == 'complete')
            == review['unchangedDisagreementsConfirmed'],
            'Complete review requires explicit confirmation of unchanged disagreements')
    require(isinstance(review['reviewNote'], str) and review['reviewNote'].strip(),
            'Missing review status explanation')
    require(isinstance(review['corrections'], list), 'Corrections must be a list')
    provenance = {source['stage']: source for source in alignment['provenance']}
    source_rows = {}
    covered = set()
    for row in rows:
        for prefix in PREFIXES:
            source_rows[identity(row, prefix)] = row, prefix
        for prefix in review['coveragePanels']:
            if (row[prefix + 'AgentOutcome'] == 'visually_complete'
                    and not boolean(row[prefix + 'BenchSuccess'], prefix)):
                covered.add(identity(row, prefix))
    corrections = {}
    for correction in review['corrections']:
        require(isinstance(correction, dict) and set(correction) == CORRECTION_FIELDS,
                'Unexpected correction fields')
        key = correction['stage'], correction['episodeKey']
        require(key not in corrections, 'Duplicate source-stage correction')
        require(key in source_rows and key in covered,
                'Correction must target a before/after raw disagreement')
        row, prefix = source_rows[key]
        require(correction['originalAgentOutcome'] == row[prefix + 'AgentOutcome'] == 'visually_complete',
                'Correction original outcome does not match the archived claim')
        require(correction['originalAgentLabel'] == row[prefix + 'AgentLabel'] == 'success',
                'Correction original label does not match the archived claim')
        require(correction['reviewedAgentLabel'] == 'failure',
                'Disagreement corrections must reject an original completion claim')
        require(correction['nativeSuccess'] is False
                and not boolean(row[prefix + 'BenchSuccess'], prefix),
                'Human review cannot change a native benchmark outcome')
        expected = {
            'sourceRunName': row[prefix + 'RunName'],
            'sourceManifestSha256': provenance[key[0]]['manifestSha256'],
            'sourceResultSha256': row[prefix + 'ResultSha256'],
            'sourceFinishSha256': row[prefix + 'FinishSha256'],
        }
        for field, value in expected.items():
            require(correction[field] == value, f'Correction {field} does not match its source stage')
        require(correction['decisionBasis'] == 'User-confirmed human review',
                'Corrections require an explicitly confirmed human decision')
        require(isinstance(correction['reason'], str) and correction['reason'].strip(),
                'Correction requires a short review reason')
        corrections[key] = correction
    return corrections, covered


def reviewed_statistics(rows, prefix, corrections, confirmed_unchanged):
    require(bool(rows), 'Cannot summarize an empty review panel')
    matrix = {label: {'benchSuccess': 0, 'benchFailure': 0}
              for label in ('success', 'failure')}
    raw_mismatches = corrected = inferred = unassessed = reviewed = 0
    for row in rows:
        native = boolean(row[prefix + 'BenchSuccess'], prefix)
        outcome = row[prefix + 'AgentOutcome']
        raw_success = outcome == 'visually_complete'
        label = 'success' if native or raw_success else 'failure'
        key = identity(row, prefix)
        if not native and raw_success:
            raw_mismatches += 1
            if key in corrections:
                label = corrections[key]['reviewedAgentLabel']
                corrected += 1
                reviewed += 1
            elif key in confirmed_unchanged:
                reviewed += 1
        inferred += int(native and not raw_success)
        unassessed += int(not native and not outcome)
        matrix[label]['benchSuccess' if native else 'benchFailure'] += 1
    n = len(rows)
    native_successes = sum(value['benchSuccess'] for value in matrix.values())
    mismatches = matrix['success']['benchFailure']
    return {
        'n': n, 'benchSuccess': native_successes, 'benchFailure': n - native_successes,
        'benchSuccessRate': native_successes / n,
        'mismatchCount': mismatches, 'ias': 1 - mismatches / n,
        'matrix': matrix,
        'agentCounts': {label: sum(value.values()) for label, value in matrix.items()},
        'sourceStageCounts': dict(Counter(row[prefix + 'Stage'] for row in rows)),
        'rawMismatchCount': raw_mismatches,
        'appliedCorrectionCount': corrected,
        'confirmedDisagreementReviewCount': reviewed,
        'unconfirmedDisagreementCount': raw_mismatches - reviewed,
        'inferredNativeSuccessCount': inferred,
        'unassessedNativeFailureCount': unassessed,
    }


def rebuild_review(review, alignment, rows, source_files):
    """Return derived accounting, keeping all supplied human metadata unchanged."""
    check_public(review, 'humanReview')
    validate_alignment(alignment, rows)
    corrections, covered = validate_metadata(review, alignment, rows)
    retained = covered - set(corrections) if review['unchangedDisagreementsConfirmed'] else set()
    result = {key: deepcopy(value) for key, value in review.items() if key in METADATA_FIELDS}
    result['sourceFiles'] = deepcopy(source_files)
    result['reportingRule'] = deepcopy(REPORTING_RULE)
    result['reviewCoverageSummary'] = {
        'rawDisagreementEpisodes': len(covered),
        'confirmedCorrections': len(corrections),
        'confirmedUnchangedDisagreements': len(retained),
        'awaitingConfirmation': len(covered) - len(corrections) - len(retained),
    }
    for prefix in PREFIXES:
        result[prefix] = reviewed_statistics(rows, prefix, corrections, retained)
    for name, selection in [('rerunSubset', R1_TASKS), ('finalRoundSubset', R2_TASKS)]:
        selected = [row for row in rows if (row['suite'], int(row['taskId'])) in selection]
        result[name] = {'n': len(selected)}
        for prefix in PREFIXES:
            result[name][prefix] = reviewed_statistics(selected, prefix, corrections, retained)
    check_public(result, 'humanReview')
    return result


def validate_review(review, alignment, rows, source_files, *, require_complete=False):
    expected = rebuild_review(review, alignment, rows, source_files)
    exact(review, expected, 'humanReview')
    if require_complete:
        require(review['reviewCoverageStatus'] == 'complete'
                and review['reviewCoverageSummary']['awaitingConfirmation'] == 0,
                'Human review is pending confirmation; publication requires complete coverage')
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true', help='Validate committed reviewed statistics (default)')
    action.add_argument('--write', action='store_true', help='Regenerate derived fields without confirming review coverage')
    parser.add_argument('--require-complete', action='store_true', help='Reject pending human-review coverage')
    args = parser.parse_args()
    try:
        review_path = args.root / REVIEW_PATH
        review = json.loads(review_path.read_text())
        alignment, rows, fingerprints = load_sources(args.root)
        if args.write:
            review = rebuild_review(review, alignment, rows, fingerprints)
        validate_review(review, alignment, rows, fingerprints,
                        require_complete=args.require_complete)
        if args.write:
            review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps({
            'reviewCoverageStatus': review['reviewCoverageStatus'],
            'coverage': review['reviewCoverageSummary'],
            'before': {'mismatchCount': review['before']['mismatchCount'], 'ias': review['before']['ias']},
            'after': {'mismatchCount': review['after']['mismatchCount'], 'ias': review['after']['ias']},
            'nativeOutcomesChanged': False,
        }, indent=2))
    except (OSError, ValueError, ValidationError, KeyError, TypeError) as exc:
        print(f'Human-review validation failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
