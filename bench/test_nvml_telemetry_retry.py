import unittest
from unittest.mock import Mock, patch

from nvidia_metrics import Nvml


class TelemetryRetryTests(unittest.TestCase):
    def setUp(self):
        self.meter = Nvml.__new__(Nvml)
        self.errors = []

    @patch('nvidia_metrics.time.sleep')
    def test_transient_unknown_returns_a_real_subsequent_sample(self, sleep):
        sample = {'temperature_c': 63, 'utilization_percent': 97}
        self.meter.sample = Mock(side_effect=[RuntimeError('utilization: NVML 999: Unknown Error'), sample])
        self.assertIs(self.meter.sample_with_retry(self.errors.append), sample)
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(self.errors[0]['retrying'])
        self.assertEqual(self.meter.sample.call_count, 2)

    @patch('nvidia_metrics.time.sleep')
    def test_persistent_error_is_not_silenced(self, sleep):
        self.meter.sample = Mock(side_effect=RuntimeError('utilization: NVML 999: Unknown Error'))
        with self.assertRaisesRegex(RuntimeError, '999'):
            self.meter.sample_with_retry(self.errors.append)
        self.assertEqual(self.meter.sample.call_count, 3)
        self.assertFalse(self.errors[-1]['retrying'])

    @patch('nvidia_metrics.time.sleep')
    def test_lost_gpu_is_not_retried(self, sleep):
        self.meter.sample = Mock(side_effect=RuntimeError('utilization: NVML 15: GPU is lost'))
        with self.assertRaisesRegex(RuntimeError, 'lost'):
            self.meter.sample_with_retry(self.errors.append)
        self.assertEqual(self.meter.sample.call_count, 1)
        self.assertEqual(self.errors, [])
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
