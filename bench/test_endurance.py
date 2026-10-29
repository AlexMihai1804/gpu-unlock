"""Offline tests of failure guards and duration summaries; no CUDA initialization."""
import unittest
from endurance import check_limits, check_health, parse_telemetry, summarize, cooling_requested


class Guards(unittest.TestCase):
    def test_no_application_temperature_cutoff_unless_requested(self):
        check_limits({'temperature_c':82,'ac_line_status':1},None)
        with self.assertRaises(RuntimeError):
            check_limits({'temperature_c':82,'ac_line_status':0},None)

    def test_cooling_hysteresis(self):
        self.assertFalse(cooling_requested(78,False,79,74))
        self.assertTrue(cooling_requested(79,False,79,74))
        self.assertTrue(cooling_requested(78,True,79,74))
        self.assertTrue(cooling_requested(75,True,79,74))
        self.assertFalse(cooling_requested(74,True,79,74))

    def test_temperature_boundary(self):
        check_limits({'temperature_c':81, 'ac_line_status':1}, 82)
        with self.assertRaises(RuntimeError):
            check_limits({'temperature_c':82, 'ac_line_status':1}, 82)

    def test_ac_disconnected_and_unknown(self):
        for value in (0, 255):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                check_limits({'temperature_c':60, 'ac_line_status':value}, 82)

    def test_driver_hardware_and_sleep_stop(self):
        for provider, event_id in [('nvlddmkm',153), ('Display',4101),
                ('Microsoft-Windows-WHEA-Logger',18), ('Microsoft-Windows-Kernel-Power',506)]:
            with self.subTest(provider=provider), self.assertRaises(RuntimeError):
                check_health([{'provider':provider, 'id':event_id}])

    def test_known_network_warning_only(self):
        event={'provider':'Microsoft-Windows-WHEA-Logger', 'id':17, 'fields':{
            'VendorID':'0x1022', 'DeviceID':'0x14ba', 'Bus':'0x0', 'Device':'0x2',
            'Function':'0x1', 'UncorrectableErrorStatus':'0x0'}}
        check_health([event])
        event['fields']['UncorrectableErrorStatus']='0x1'
        with self.assertRaises(RuntimeError):
            check_health([event])

    def test_telemetry_requires_selected_gpu(self):
        row={'returncode':0, 'stdout':'0, 70, 110.5, 1500, 7001, 99, 1200, P0, 0x0', 'stderr':''}
        parsed=parse_telemetry(row,0)
        self.assertEqual(parsed['temperature_c'],70)
        self.assertEqual(parsed['utilization_percent'],99)
        with self.assertRaises(RuntimeError):
            parse_telemetry(row,1)
        row['stdout']='0, N/A, 110, 1500, 7001, 99, 1200, P0, 0x0'
        with self.assertRaises(ValueError):
            parse_telemetry(row,0)

    def test_summary_counts_and_drift(self):
        rows=[dict(mode='fp16',iterations=100,cuda_ms=2500,tflops=x,
                   correctness_passed=True,sample_relative_l2=0.00001) for x in (40,39,38,36)]
        result=summarize(rows)['fp16']
        self.assertEqual(result['gemm_count'],400)
        self.assertEqual(result['cuda_seconds'],10)
        self.assertAlmostEqual(result['last_vs_first_quarter_percent'],-10)
        self.assertTrue(result['all_numeric_checks_passed'])

    def test_tf32_summary_requires_explicit_mode_and_retains_failed_block(self):
        rows=[dict(mode='tf32',iterations=100,cuda_ms=5000,tflops=22.0,
                   correctness_passed=False,sample_relative_l2=0.004)]
        self.assertEqual(summarize(rows),{})
        result=summarize(rows,('tf32',))['tf32']
        self.assertEqual(result['gemm_count'],100)
        self.assertEqual(result['cuda_seconds'],5.0)
        self.assertFalse(result['all_numeric_checks_passed'])


if __name__ == '__main__':
    unittest.main()
