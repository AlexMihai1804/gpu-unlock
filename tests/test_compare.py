import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("gemm_compare",ROOT/"bench/compare.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComparisonGuards(unittest.TestCase):
    def setUp(self):
        self.before=json.loads((ROOT/"results/baseline-2026-10-25.json").read_text())
        self.after=copy.deepcopy(self.before)

    def test_identity_gives_zero_change(self):
        self.assertTrue(all(r["gain_percent"]==0 for r in module.compare(self.before,self.after)))

    def test_different_library_rejected(self):
        self.after["packages"]["nvidia-cublas-cu12"]="different"
        with self.assertRaises(ValueError): module.compare(self.before,self.after)

    def test_failed_numerics_rejected(self):
        self.after["results"][0]["correctness_passed"]=False
        with self.assertRaises(ValueError): module.compare(self.before,self.after)

    def test_different_inputs_rejected(self):
        self.after["results"][0]["input_sha256"][0]="different"
        with self.assertRaises(ValueError): module.compare(self.before,self.after)
