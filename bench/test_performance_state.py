"""Regression tests for real measured power-profile cases; no GPU initialization."""
import copy
import json
from pathlib import Path
import unittest
from performance_state import classify

ROOT=Path(__file__).resolve().parents[1]


def saved(name):
    return json.loads((ROOT/'results'/name).read_text())


class State(unittest.TestCase):
    def test_locked_baseline(self):
        self.assertEqual(classify(saved('baseline-2026-10-25.json'))['classification'],'consistent_with_locked')

    def test_verified_unlocked(self):
        self.assertTrue(classify(saved('unlock-v3-B2-2026-10-25.json'))['unlocked_performance_supported'])

    def test_post_standby_is_locked_pattern(self):
        self.assertEqual(classify(saved('automatic-before-endurance-2026-10-26.json'))['classification'],'consistent_with_locked')

    def test_unlocked_at_80w_is_not_rejected_for_low_raw_tflops(self):
        data=saved('long-current-state-20261026-115044/before.json')
        rates={row['mode']:row['tflops'] for row in data['results']}
        self.assertLess(rates['fp16']/rates['tf32'],2.5)
        self.assertTrue(classify(data)['unlocked_performance_supported'])

    def test_missing_clocks_are_inconclusive(self):
        data=saved('unlock-v3-B2-2026-10-25.json');data['telemetry']=[]
        self.assertEqual(classify(data)['classification'],'inconclusive')

    def test_changed_libraries_are_not_classified(self):
        data=copy.deepcopy(saved('unlock-v3-B2-2026-10-25.json'));data['packages']['numpy']='different'
        self.assertEqual(classify(data)['classification'],'inconclusive')

    def test_verified_tf32_unlock_is_not_rejected_as_changed_control(self):
        result=classify(saved('tf32-after-automatic-20261026-1938.json'))
        self.assertTrue(result['unlocked_performance_supported'])
        self.assertTrue(result['tf32_unlocked_performance_supported'])
        self.assertEqual(result['tf32_classification'],'consistent_with_full_rate')

    def test_full_tf32_still_requires_fp32_control(self):
        data=copy.deepcopy(saved('tf32-after-automatic-20261026-1938.json'))
        next(row for row in data['results'] if row['mode']=='fp32')['tflops']*=1.5
        self.assertEqual(classify(data)['classification'],'inconclusive')

    def test_tf32_gain_alone_does_not_prove_fp16_bf16_unlock(self):
        data=copy.deepcopy(saved('baseline-2026-10-25.json'))
        next(row for row in data['results'] if row['mode']=='tf32')['tflops']*=2
        self.assertEqual(classify(data)['classification'],'inconclusive')
        self.assertFalse(classify(data)['unlocked_performance_supported'])


if __name__=='__main__':
    unittest.main()
