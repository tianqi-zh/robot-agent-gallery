"""Human corrections must be scoped, reproducible, and separate from raw labels."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from review_libero_alignment import (
    REVIEW_PATH, ValidationError, load_sources, rebuild_review, validate_review,
)


class LiberoHumanReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_sources(ROOT)
        cls.saved_review = json.loads((ROOT / REVIEW_PATH).read_text())

    def setUp(self):
        self.alignment, self.rows, self.fingerprints = deepcopy(self.sources)
        self.review = deepcopy(self.saved_review)

    def rebuild(self):
        return rebuild_review(self.review, self.alignment, self.rows, self.fingerprints)

    def test_committed_statistics_reproduce(self):
        actual = validate_review(self.review, self.alignment, self.rows, self.fingerprints)
        self.assertEqual(actual['before']['matrix'], {
            'success': {'benchSuccess': 322, 'benchFailure': 47},
            'failure': {'benchSuccess': 0, 'benchFailure': 31},
        })
        self.assertEqual(actual['after']['matrix'], {
            'success': {'benchSuccess': 357, 'benchFailure': 0},
            'failure': {'benchSuccess': 0, 'benchFailure': 43},
        })
        self.assertEqual(actual['after']['ias'], 1)
        self.assertEqual(actual['rerunSubset']['after']['matrix']['failure']['benchFailure'], 15)

    def test_final_stage_correction_does_not_relabel_earlier_plate_attempts(self):
        actual = self.rebuild()
        self.assertEqual(actual['before']['appliedCorrectionCount'], 0)
        self.assertEqual(actual['round1']['appliedCorrectionCount'], 0)
        self.assertEqual(actual['after']['appliedCorrectionCount'], 1)
        self.assertEqual(actual['round1']['mismatchCount'], 19)

    def test_raw_records_are_not_mutated(self):
        original = deepcopy((self.alignment, self.rows, self.review))
        self.rebuild()
        self.assertEqual((self.alignment, self.rows, self.review), original)
        self.assertEqual(self.alignment['after']['mismatchCount'], 1)
        row = next(row for row in self.rows if row['episodeKey'] == 'libero_goal_t05_r05')
        self.assertEqual(row['afterAgentOutcome'], 'visually_complete')

    def test_missing_declarations_are_reporting_assignments_not_human_reviews(self):
        actual = self.rebuild()
        self.assertEqual(actual['before']['unassessedNativeFailureCount'], 5)
        self.assertEqual(actual['after']['unassessedNativeFailureCount'], 9)
        self.assertEqual(actual['before']['inferredNativeSuccessCount'], 322)
        self.assertEqual(actual['after']['inferredNativeSuccessCount'], 357)
        self.assertEqual(actual['after']['confirmedDisagreementReviewCount'], 1)

    def test_pending_review_cannot_pass_publication_gate(self):
        self.review['reviewCoverageStatus'] = 'pending_confirmation'
        self.review['unchangedDisagreementsConfirmed'] = False
        actual = self.rebuild()
        self.assertEqual(actual['reviewCoverageSummary']['awaitingConfirmation'], 47)
        with self.assertRaisesRegex(ValidationError, 'pending confirmation'):
            validate_review(actual, self.alignment, self.rows, self.fingerprints, require_complete=True)

    def test_regeneration_does_not_confirm_pending_review(self):
        self.review['reviewCoverageStatus'] = 'pending_confirmation'
        self.review['unchangedDisagreementsConfirmed'] = False
        actual = self.rebuild()
        self.assertEqual(actual['reviewCoverageStatus'], 'pending_confirmation')
        self.assertFalse(actual['unchangedDisagreementsConfirmed'])
        self.assertEqual(actual['before']['confirmedDisagreementReviewCount'], 0)

    def test_explicit_coverage_confirmation_completes_only_before_after_disagreements(self):
        self.review['reviewCoverageStatus'] = 'complete'
        self.review['unchangedDisagreementsConfirmed'] = True
        actual = self.rebuild()
        validate_review(actual, self.alignment, self.rows, self.fingerprints, require_complete=True)
        self.assertEqual(actual['reviewCoverageSummary']['confirmedUnchangedDisagreements'], 47)
        self.assertEqual(actual['reviewCoverageSummary']['awaitingConfirmation'], 0)
        self.assertEqual(actual['before']['confirmedDisagreementReviewCount'], 47)
        self.assertEqual(actual['round1']['unconfirmedDisagreementCount'], 19)

    def test_complete_status_alone_cannot_invent_confirmation(self):
        self.review['reviewCoverageStatus'] = 'complete'
        self.review['unchangedDisagreementsConfirmed'] = False
        with self.assertRaisesRegex(ValidationError, 'explicit confirmation'):
            self.rebuild()

    def test_wrong_stage_is_rejected(self):
        self.review['corrections'][0]['stage'] = 'baseline'
        with self.assertRaisesRegex(ValidationError, 'does not match its source stage'):
            self.rebuild()

    def test_wrong_source_result_hash_is_rejected(self):
        self.review['corrections'][0]['sourceResultSha256'] = '0' * 64
        with self.assertRaisesRegex(ValidationError, 'sourceResultSha256'):
            self.rebuild()

    def test_duplicate_corrections_are_rejected(self):
        self.review['corrections'].append(deepcopy(self.review['corrections'][0]))
        with self.assertRaisesRegex(ValidationError, 'Duplicate'):
            self.rebuild()

    def test_native_outcome_cannot_be_overridden(self):
        self.review['corrections'][0]['nativeSuccess'] = True
        with self.assertRaisesRegex(ValidationError, 'cannot change a native'):
            self.rebuild()

    def test_review_cannot_target_an_unassessed_failure(self):
        self.review['corrections'][0]['episodeKey'] = 'libero_goal_t05_r04'
        with self.assertRaisesRegex(ValidationError, 'raw disagreement'):
            self.rebuild()

    def test_derived_matrix_tampering_is_rejected(self):
        self.review['after']['matrix']['success']['benchSuccess'] += 1
        with self.assertRaisesRegex(ValidationError, 'matrix.success.benchSuccess'):
            validate_review(self.review, self.alignment, self.rows, self.fingerprints)

    def test_stale_source_fingerprint_is_rejected(self):
        self.review['sourceFiles']['episodes']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValidationError, 'sourceFiles.episodes.sha256'):
            validate_review(self.review, self.alignment, self.rows, self.fingerprints)


if __name__ == '__main__':
    unittest.main()
