"""Reject stale controls and attempts outside the approved unchanged-image sequence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import review_unlock


class ReproAuthorization(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'results').mkdir()
        (self.root/'docs').mkdir()
        self.evidence=self.root/'results/attempt'
        self.evidence.mkdir()
        self.plan=self.root/'docs/plan.md'
        self.plan.write_bytes(b'B2 A3 B3 A4 unchanged image')
        self.auth={'attempt_limit':2,'additional_attempt_limit':2,'order':['B2','A3','B3','A4'],
                   'plan':'docs/plan.md','plan_sha256':hashlib.sha256(self.plan.read_bytes()).hexdigest(),
                   'utc_recorded':'2026-10-25T19:00:00Z','file_sha256':'image','pe_authenticode_sha256':'pe'}
        self.context={'stage':'B2','ordinal_in_authorization':1,'authorized_attempt_limit':2,
                      'preceding_review':'results/normal.json'}
        self.control={'normal_return_passed':True,'benchmark':'normal-return-A2-2026-10-25.json',
                      'new_boot_utc':'2026-10-25T18:00:00Z'}
        self.windows={'windows_boot_utc':'2026-10-25T20:00:00Z'}
        self.stage='B2'
        self.patcher=patch.object(review_unlock,'ROOT',self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def review(self):
        raw=json.dumps(self.auth).encode()
        (self.root/'results/repro-v3-authorization.json').write_bytes(raw)
        (self.evidence/'repro-v3-authorization.json').write_bytes(raw)
        (self.evidence/'attempt-context.json').write_text(json.dumps(self.context))
        (self.root/'results/normal.json').write_text(json.dumps(self.control))
        return review_unlock.review_authorization(self.evidence,self.stage,'image','pe',self.windows)

    def test_B2_keeps_one_attempt_for_B3(self):
        self.assertEqual(self.review()['remaining_after_this_attempt'],1)

    def test_B3_requires_A3_and_consumes_allowance(self):
        self.stage='B3'
        self.context.update(stage='B3',ordinal_in_authorization=2)
        with self.assertRaises(ValueError):
            self.review()
        self.control['benchmark']='normal-return-A3-2026-10-25.json'
        self.assertEqual(self.review()['remaining_after_this_attempt'],0)

    def test_unpassed_normal_control_rejected(self):
        self.control['normal_return_passed']=False
        with self.assertRaises(ValueError):
            self.review()

    def test_old_boot_cannot_be_used_for_new_attempt(self):
        self.windows['windows_boot_utc']=self.control['new_boot_utc']
        with self.assertRaises(ValueError):
            self.review()

    def test_boot_before_authorization_rejected(self):
        self.windows['windows_boot_utc']='2026-10-25T18:30:00Z'
        with self.assertRaises(ValueError):
            self.review()

    def test_changed_image_rejected(self):
        self.auth['file_sha256']='different'
        with self.assertRaises(ValueError):
            self.review()

    def test_relabeling_B2_as_second_attempt_rejected(self):
        self.context['ordinal_in_authorization']=2
        with self.assertRaises(ValueError):
            self.review()

    def test_changed_approved_plan_rejected(self):
        self.plan.write_bytes(b'different plan')
        with self.assertRaises(ValueError):
            self.review()


if __name__=='__main__':
    unittest.main()
