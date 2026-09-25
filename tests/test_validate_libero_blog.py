"""Frozen evidence regressions with synthetic media bytes; no network or private runs."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from validate_libero_blog import (ValidationError, check_public, load_documents,
                                 local_asset, validate_documents)


class LiberoBlogPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents=deepcopy(load_documents(ROOT))
        cls.media_directory=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.media_directory.cleanup)
        cls.media_root=Path(cls.media_directory.name)
        # Keep the source evidence frozen; synthetic presentation bytes make the
        # structural/hash tests independent of the separately published videos.
        media=cls.documents[2]
        for clip in media['clips'].values():
            for kind in ('video','poster'):
                path=cls.media_root/clip[kind]
                path.parent.mkdir(parents=True,exist_ok=True)
                payload=('synthetic '+clip[kind]).encode()
                path.write_bytes(payload)
                clip['media'][kind+'Bytes']=len(payload)
                clip['media'][kind+'Sha256']=hashlib.sha256(payload).hexdigest()
                if kind=='video' and 'gallerySource' in clip:
                    clip['source']['videoSha256']=clip['media']['videoSha256']
        media['validation']['newMediaBytes']=sum(
            clip['media']['videoBytes']+clip['media']['posterBytes']
            for clip in media['clips'].values() if not clip['reusedBaselineMedia'])

    def setUp(self):
        self.alignment,self.rows,self.media=deepcopy(self.documents)

    def validate(self):
        return validate_documents(ROOT,self.alignment,self.rows,self.media,media_root=self.media_root)

    def test_complete_publication(self):
        result=self.validate()
        self.assertEqual(result['episodeSlots'],400)
        self.assertEqual(result['afterStageCounts'],{'baseline':310,'round1':70,'round2':20})
        self.assertEqual(result['hashedAssets'],36)
        self.assertEqual(result['before']['mismatchCount'],47)
        self.assertEqual(result['after']['mismatchCount'],1)

    def test_rejects_inflated_ias(self):
        self.alignment['after']['ias']=1.0
        with self.assertRaisesRegex(ValidationError,'after.ias'):
            self.validate()

    def test_rejects_changed_confusion_matrix(self):
        self.alignment['before']['matrix']['success']['benchFailure']-=1
        with self.assertRaisesRegex(ValidationError,'matrix.success.benchFailure'):
            self.validate()

    def test_native_success_cannot_impute_agent_success(self):
        row=next(r for r in self.rows if r['beforeBenchSuccess']=='True')
        self.assertEqual(row['beforeAgentOutcome'],'')
        row['beforeAgentLabel']='success'
        with self.assertRaisesRegex(ValidationError,'must remain unknown'):
            self.validate()

    def test_rejects_one_seed_cherry_picked_from_an_earlier_stage(self):
        row=next(r for r in self.rows if r['episodeKey']=='libero_goal_t05_r07')
        row['afterStage']='baseline'
        with self.assertRaisesRegex(ValidationError,'entire-task stage selection'):
            self.validate()

    def test_rejects_different_init_state(self):
        self.rows[0]['initStateId']='9'
        with self.assertRaisesRegex(ValidationError,'seed/init pairing'):
            self.validate()

    def test_rejects_missing_slot(self):
        self.rows.pop()
        with self.assertRaisesRegex(ValidationError,'400 unique'):
            self.validate()

    def test_rejects_changed_pair_transition_matrix(self):
        self.media['pairs'][0]['pairedMatrix']['F→S']-=1
        with self.assertRaisesRegex(ValidationError,'pairedMatrix'):
            self.validate()

    def test_rejects_wrong_gallery_episode(self):
        clip=next(c for c in self.media['clips'].values() if 'gallerySource' in c)
        clip['gallerySource']['recordId']='original/libero_goal_t05_r09'
        with self.assertRaisesRegex(ValidationError,'Gallery record differs'):
            self.validate()

    def test_rejects_stale_gallery_poster_frame(self):
        clip=next(c for c in self.media['clips'].values() if 'gallerySource' in c)
        clip['media']['posterFrame']=clip['frames']//2
        with self.assertRaisesRegex(ValidationError,'Poster frame differs'):
            self.validate()

    def test_rejects_stale_instruction(self):
        clip=self.media['clips']['r2:libero_goal_t05_r02']
        clip['instruction']='push the plate directly in front of the stove, about 35 cm center to center'
        with self.assertRaisesRegex(ValidationError,'instruction mismatch'):
            self.validate()

    def test_rejects_result_from_a_different_run(self):
        clip=self.media['clips']['r2:libero_goal_t05_r02']
        clip['source']['resultSha256']='0'*64
        with self.assertRaisesRegex(ValidationError,'result source mismatch'):
            self.validate()

    def test_rejects_tampered_media_digest(self):
        clip=next(iter(self.media['clips'].values()))
        clip['media']['videoSha256']='0'*64
        with self.assertRaisesRegex(ValidationError,'video (hash/size mismatch|must retain original bytes)'):
            self.validate()

    def test_rejects_traversal_path(self):
        clip=next(iter(self.media['clips'].values()))
        clip['video']='media/../../private.mp4'
        with self.assertRaisesRegex(ValidationError,'repository-relative'):
            self.validate()

    def test_rejects_public_absolute_path_and_reasoning(self):
        for payload in ({'source':'run at /playpen-ssd/private/run'},
                        {'agentMessages':['private model text']},
                        {'credentials':{'token':'secret'}}):
            with self.subTest(payload=tuple(payload)):
                with self.assertRaises(ValidationError):
                    check_public(payload)

    def test_rejects_asset_symlink_outside_site(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);site=base/'site';(site/'media').mkdir(parents=True)
            secret=base/'outside.mp4';secret.write_bytes(b'not public')
            (site/'media/video.mp4').symlink_to(secret)
            with self.assertRaisesRegex(ValidationError,'Unsafe'):
                local_asset(site,'media/video.mp4','video')


if __name__=='__main__':unittest.main()
