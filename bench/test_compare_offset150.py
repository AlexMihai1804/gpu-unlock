import copy
import unittest

from compare_offset150 import summarize


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rounds = []
        for index, offset in enumerate((0, 150, 150, 0)):
            ms = (40, 35, 35, 42)[index]
            self.rounds.append(dict(offset_mhz=offset, results=[dict(
                mode=mode, sample_ms=[ms] * 7, tflops=2 * 8192**3 / (ms * 1e9),
                correctness_passed=True, output_bit_identical_to_baseline=True,
                inputs_identical_to_baseline=True,
                telemetry_summary=dict(maximum_temperature_c=80, median_power_w=115,
                                       median_sm_mhz=1500))
                for mode in ('fp16', 'bf16', 'tf32', 'fp32')]))

    def test_balanced_comparison_and_zero_control_drift(self):
        result = summarize(self.rounds)['tf32']
        self.assertAlmostEqual(result['gain_percent'], (41 / 35 - 1) * 100)
        self.assertAlmostEqual(result['zero_last_vs_first_percent'], (40 / 42 - 1) * 100)
        self.assertEqual(len(result['offsets']['150']['sample_ms']), 14)

    def test_incomplete_experiment_cannot_pass(self):
        with self.assertRaises(ValueError):
            summarize(self.rounds[:-1])

    def test_numerically_plausible_but_different_output_rejected(self):
        damaged = copy.deepcopy(self.rounds)
        damaged[2]['results'][2]['output_bit_identical_to_baseline'] = False
        with self.assertRaises(ValueError):
            summarize(damaged)

    def test_missing_cuda_samples_rejected(self):
        damaged = copy.deepcopy(self.rounds)
        damaged[1]['results'][0]['sample_ms'] = []
        with self.assertRaises(ValueError):
            summarize(damaged)


if __name__ == '__main__':
    unittest.main()
