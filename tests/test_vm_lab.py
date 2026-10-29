"""Prevent VM timeouts from being misreported as Secure Boot validation."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("vm_lab",ROOT/"tools/vm_lab.py")
vm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class VmEvidenceTests(unittest.TestCase):
    def test_timeout_alone_is_not_mok_rejection(self):
        self.assertFalse(vm.evaluate("n",{"timed_out":True},"",""))

    def test_mok_rejection_requires_file_open_and_error(self):
        debug="FSOpen: Open '\\EFI\\BOOT\\grubx64.efi' Success"
        serial="Verification failed: (0x1A) Security Violation"
        self.assertTrue(vm.evaluate("n",{"timed_out":True},debug,serial))
        self.assertFalse(vm.evaluate("n",{"timed_out":True},debug+"VM_HARNESS_ENTERED",serial))

    def test_windows_call_marker_is_not_execution_evidence(self):
        debug="REAL_WINDOWS_BOOT_MANAGER_START\nCHILD_LOAD=0x0000000000000000"
        self.assertFalse(vm.evaluate("w",{},debug,""))
        self.assertTrue(vm.evaluate("w",{},debug,"Windows Boot Manager \\EFI\\Microsoft\\Boot\\BCD 0xc000000f"))

    def test_child_status_marker_requires_successful_vm_exit(self):
        self.assertFalse(vm.evaluate("p",{"returncode":35},"VM_TEST_PASS",""))
        self.assertTrue(vm.evaluate("p",{"returncode":33},"VM_TEST_PASS",""))

    def test_vm_state_cannot_escape_workspace_lab(self):
        for path in (ROOT/"build/vm-lab/../../Windows",ROOT/"build/USB-PROBE",ROOT):
            with self.assertRaises(ValueError): vm.within(path)
        self.assertEqual(vm.within(vm.VM/"case/VARS.fd"),(vm.VM/"case/VARS.fd").resolve())


if __name__=="__main__": unittest.main()
