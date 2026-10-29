import unittest
from adaptive_tuning import assess,screen_plan


def phase(name, gain=1., power=1., temperature=83, blocks=3):
    rows=[]
    for mode in ('fp16','bf16'):
        for _ in range(blocks):
            seconds=10/gain
            rows.append(dict(phase=name,mode=mode,work_tflop=400,energy_j=1142.857142857*power/gain,
                cuda_ms=seconds*1000,meter_wall_seconds=seconds,max_temperature_c=temperature,
                correctness_passed=True))
    return rows


class Escalation(unittest.TestCase):
    def test_original_plan_stays_bounded_at_120(self):
        self.assertEqual(screen_plan([60,90,120]),(60,90,120))

    def test_150_comparison_requires_exact_explicit_plan(self):
        self.assertEqual(screen_plan([120,150]),(120,150))
        for invalid in ([],[150],[120,180],[60,90,120,150],[150,120]):
            with self.assertRaises(ValueError):screen_plan(invalid)

    def test_positive_balanced_gain_allows_next_step(self):
        r=assess(phase('a')+phase('t',1.03)+phase('b'),'t',('a','b'))
        self.assertTrue(r['allow_next_step'])

    def test_one_regressing_mode_prevents_escalation(self):
        trials=phase('t',1.03)
        for row in trials:
            if row['mode']=='bf16':
                row['energy_j']*=1.05
        self.assertFalse(assess(phase('a')+trials+phase('b'),'t',('a','b'))['allow_next_step'])

    def test_higher_power_does_not_masquerade_as_tuning_gain(self):
        r=assess(phase('a')+phase('t',1.08,power=1.06)+phase('b'),'t',('a','b'))
        self.assertFalse(r['allow_next_step'])

    def test_unbalanced_temperature_is_inconclusive(self):
        r=assess(phase('a',temperature=75)+phase('t',1.03)+phase('b'),'t',('a','b'))
        self.assertFalse(r['allow_next_step'])

    def test_too_small_marginal_gain_stops_higher_offsets(self):
        previous=assess(phase('a')+phase('t',1.03)+phase('b'),'t',('a','b'))
        current=assess(phase('b')+phase('u',1.032)+phase('c'),'u',('b','c'),previous)
        self.assertTrue(current['worth'])
        self.assertFalse(current['allow_next_step'])

    def test_sufficient_marginal_gain_allows_higher_offset(self):
        previous=assess(phase('a')+phase('t',1.03)+phase('b'),'t',('a','b'))
        current=assess(phase('b')+phase('u',1.04)+phase('c'),'u',('b','c'),previous)
        self.assertTrue(current['allow_next_step'])

    def test_insufficient_measurement_windows_prevent_escalation(self):
        r=assess(phase('a',blocks=2)+phase('t',1.03)+phase('b'),'t',('a','b'))
        self.assertFalse(r['allow_next_step'])

    def test_incorrect_output_prevents_escalation(self):
        rows=phase('a')+phase('t',1.03)+phase('b')
        rows[4]['correctness_passed']=False
        self.assertFalse(assess(rows,'t',('a','b'))['allow_next_step'])


if __name__=='__main__':
    unittest.main()
