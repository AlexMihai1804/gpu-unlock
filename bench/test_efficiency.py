import unittest
from unittest.mock import Mock, patch
from efficiency import energy_metrics, aggregate, set_trial_offset, restore_original


class EnergyAccounting(unittest.TestCase):
    def test_same_work_and_energy_window(self):
        m = energy_metrics(1000, 1_001_000, 10, 9900, 8192, 400)
        self.assertEqual(m['energy_j'], 1000)
        self.assertEqual(m['average_power_w'], 100)
        self.assertAlmostEqual(m['tflop_per_joule'], 2 * 8192**3 * 400 / 1e15)
        self.assertAlmostEqual(m['cuda_tflops'], m['work_tflop'] / 9.9)

    def test_counter_reset_or_stall_cannot_be_efficiency_gain(self):
        for end in (999, 1000):
            with self.assertRaises(ValueError):
                energy_metrics(1000, end, 10, 9900, 8192, 400)

    def test_rejects_mismatched_cuda_window(self):
        with self.assertRaises(ValueError):
            energy_metrics(1000, 5000, 1, 2000, 8192, 400)

    def test_aggregate_uses_total_work_over_total_energy(self):
        rows = [dict(phase='reference-0', mode='fp16', offset_mhz=0, iterations=1,
            energy_j=energy, meter_wall_seconds=1, cuda_ms=1000, work_tflop=1,
            median_sm_clock_mhz=1000, median_voltage_mv=700, max_temperature_c=70,
            correctness_passed=True) for energy in (10, 90)]
        self.assertAlmostEqual(aggregate(rows)[0]['tflop_per_joule'], 0.02)

    def test_tuning_rejects_unbounded_offset_before_any_device_access(self):
        for offset in (-30, 15, 180, 1000):
            with self.assertRaises(ValueError):
                set_trial_offset(None, offset)

    def test_restores_changed_offset_and_verifies_readback(self):
        meter = Mock()
        original = {'0': {'offset': 0}}
        meter.offsets.side_effect = [{'0': {'offset': 30}}, original]
        with patch('efficiency.set_trial_offset') as setter:
            restore_original(meter, original)
            setter.assert_called_once_with(meter, 0)

    def test_restoration_never_reports_success_on_bad_readback(self):
        meter = Mock()
        meter.offsets.return_value = {'0': {'offset': 60}}
        with patch('efficiency.set_trial_offset'), self.assertRaises(RuntimeError):
            restore_original(meter, {'0': {'offset': 0}})

    def test_no_setter_needed_when_failed_trial_did_not_change_anything(self):
        meter = Mock()
        meter.offsets.return_value = {'0': {'offset': 0}}
        with patch('efficiency.set_trial_offset') as setter:
            restore_original(meter, {'0': {'offset': 0}})
            setter.assert_not_called()


if __name__ == '__main__':
    unittest.main()
