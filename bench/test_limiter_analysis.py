import json
from pathlib import Path
import tempfile
import unittest
from limiter_analysis import analyze


class Limiters(unittest.TestCase):
    def check_rows(self,rows,snapshots=()):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'endurance').mkdir()
            (out/'endurance/telemetry.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
            (out/'limits-snapshots.jsonl').write_text('\n'.join(json.dumps(row) for row in snapshots))
            return analyze(out)

    def test_idle_does_not_count_as_active_power_limit(self):
        rows=[dict(utilization_percent=100,temperature_c=80,power_w=110,clocks_event_reasons='0x4'),
              dict(utilization_percent=0,temperature_c=78,power_w=30,clocks_event_reasons='0x1')]
        result=self.check_rows(rows)
        self.assertEqual(result['active_samples'],1)
        self.assertEqual(result['limiter_sample_percent']['sw_power_cap'],100)
        self.assertEqual(result['limiter_sample_percent']['sw_thermal_slowdown'],0)

    def test_power_and_thermal_can_overlap(self):
        rows=[dict(utilization_percent=100,temperature_c=87,power_w=110,clocks_event_reasons='0x24'),
              dict(utilization_percent=100,temperature_c=87,power_w=110,clocks_event_reasons='0x40')]
        result=self.check_rows(rows)
        self.assertEqual(result['limiter_sample_percent']['sw_power_cap'],50)
        self.assertEqual(result['limiter_sample_percent']['sw_thermal_slowdown'],50)
        self.assertEqual(result['limiter_sample_percent']['hw_thermal_slowdown'],50)
        self.assertEqual(result['limiter_sample_percent']['hw_power_brake'],0)

    def test_missing_limits_are_not_invented(self):
        result=self.check_rows([],({'gpu_power_readings':{'current_power_limit':'N/A'}},))
        self.assertIsNone(result['observed_current_power_limit_w'])
        self.assertIsNone(result['limiter_sample_percent']['sw_power_cap'])


if __name__=='__main__':unittest.main()
