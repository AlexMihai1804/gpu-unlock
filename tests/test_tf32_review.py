"""Reject incomplete/failed SS1 evidence without accessing the physical GPU."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from review_tf32_physical import validate_log


class Tf32TransactionEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'results/automatic-tf32-physical-20261026-193847/RTX-UNLOCK/RUN0000/UNLOCK.TXT'
        if not path.is_file():
            raise unittest.SkipTest('Saved physical log not present')
        cls.log=path.read_text(encoding='ascii')

    def test_complete_saved_transaction(self):
        self.assertEqual(validate_log(self.log)['final_ss1'],'0x8')

    def test_missing_ss1_write_rejected(self):
        with self.assertRaises(ValueError):
            validate_log(self.log.replace('selector write: SS1=0x8',''))

    def test_wrong_post_flr_selector_rejected(self):
        with self.assertRaises(ValueError):
            validate_log(self.log.replace('SS0=88888888 SS1=00000008','SS0=88888888 SS1=00000003'))

    def test_repeated_reset_rejected(self):
        with self.assertRaises(ValueError):
            validate_log(self.log+'\nPCIe FLR returned: result=0\n')

    def test_stop_after_success_rejected(self):
        with self.assertRaises(ValueError):
            validate_log(self.log+'\nSTOP. No further boot handoff.\n')


if __name__=='__main__':
    unittest.main()
