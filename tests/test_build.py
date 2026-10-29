import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_tools", ROOT/"tools/build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BuildSafety(unittest.TestCase):
    def test_isolated_build_rejects_overwrite_or_escape(self):
        for path in (ROOT, ROOT/"build", ROOT/"build/../results", ROOT/"build/generated"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                module.output_directory(path)
        self.assertEqual(module.output_directory(ROOT/"build/test-new-isolated-folder"),
                         (ROOT/"build/test-new-isolated-folder").resolve())

    def test_reviewed_board_binds_exact_prom_and_chip(self):
        board=json.loads((ROOT/"config/board.pending.json").read_text())
        board.update(evidence_reviewed=True, chip="0xb76000a1", prom_sha256="dce995afb0e825c9640488b55054179ebc15c77d38c00ed45a05f7e2701433e7",
                     booter_fuse_raw="0x1", fwsec_fuse_raw="0x3")
        with TemporaryDirectory() as folder:
            path=Path(folder)/"profile.json"
            path.write_text(json.dumps(board))
            header, ready=module.board_header(path)
            self.assertTrue(ready)
            self.assertIn('M6501_EVIDENCE_READY 1',header)
            self.assertIn(board['prom_sha256'],header)
            self.assertIn('0xb76000a1U',header)
            board['prom_sha256']=''
            path.write_text(json.dumps(board))
            with self.assertRaises(ValueError): module.board_header(path)
    def test_pending_board_stays_disabled(self):
        header, ready = module.board_header(ROOT/"config/board.pending.json")
        self.assertFalse(ready)
        self.assertIn("M6501_EVIDENCE_READY 0", header)

    def test_ss1_write_removed_and_readback_preserved(self):
        original = (ROOT/"vendor/rtx30-unlock/src/unlock/vendor/unlock_610.c").read_text()
        patched = module.patch_core(original)
        self.assertNotIn('write_selector(work, "SS1"', patched)
        self.assertIn("#define GU_SS1_UNLOCK (GU_INITIAL_SS1)", patched)
        self.assertEqual(patched.count("ss1 != GU_SS1_UNLOCK"), 2)
        self.assertIn("actual != GU_SS1_UNLOCK", patched)

    def test_unknown_upstream_rejected(self):
        with self.assertRaises(ValueError):
            module.patch_core("other implementation")

    def test_full_ss1_experiment_retains_original_transaction(self):
        original = (ROOT/'vendor/rtx30-unlock/src/unlock/vendor/unlock_610.c').read_text()
        full = module.experimental_full_core(original)
        self.assertEqual(full, original)
        self.assertIn('#define GU_SS1_UNLOCK 0x8u', full)
        self.assertEqual(full.count('ss1 != GU_SS1_UNLOCK'), 2)
        with self.assertRaises(ValueError):
            module.experimental_full_core(module.patch_core(original))

    def test_full_ss1_experiment_cannot_build_automatic_image(self):
        completed = subprocess.run([sys.executable, str(ROOT/'tools/build.py'),
            '--ss1-full-experiment', '--automatic'], capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('cannot build an automatic image', completed.stderr)

    def test_experiment_io_is_separate_from_automatic_installation(self):
        original = (ROOT/'vendor/rtx30-unlock/src/unlock/app_io.c').read_text()
        patched = module.patch_experiment_io(original)
        self.assertIn('L"\\\\EFI\\\\M6501TF32\\\\RTX-UNLOCK"', patched)
        self.assertNotIn('L"\\\\RTX-UNLOCK"', patched)
        self.assertNotIn('L"\\\\EFI\\\\M6501GPU\\\\RTX-UNLOCK"', patched)
        with self.assertRaises(ValueError):
            module.patch_experiment_io(patched)

    def test_explicit_automatic_tf32_uses_private_append_only_logs(self):
        original = (ROOT/'vendor/rtx30-unlock/src/unlock/app_io.c').read_text()
        patched = module.patch_auto_tf32_io(original)
        self.assertIn('L"\\\\EFI\\\\M6501TF32\\\\RTX-UNLOCK"', patched)
        self.assertIn('L"RUN0000"', patched)
        self.assertIn('Selected >= 10000', patched)
        self.assertNotIn('L"\\\\EFI\\\\M6501GPU\\\\RTX-UNLOCK"', patched)
        with self.assertRaises(ValueError):
            module.patch_auto_tf32_io(patched)

    def test_automatic_tf32_cannot_be_combined_with_legacy_options(self):
        for option in ('--automatic', '--ss1-full-experiment'):
            with self.subTest(option=option):
                completed = subprocess.run([sys.executable, str(ROOT/'tools/build.py'),
                    '--automatic-ss1-experiment', option], capture_output=True, text=True)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn('explicit automatic SS1 option on its own', completed.stderr)

    def test_images_have_nx_sbat_relocations_and_no_imports(self):
        for name in ("PROBE", "HANDOFF", "CAPTURE", "UNLOCK-CANDIDATE"):
            with self.subTest(name=name):
                report = module.inspect_pe(ROOT/"build"/f"M6501-{name}.EFI")
                self.assertTrue(report["nx_compatible"])


if __name__ == "__main__":
    unittest.main()
