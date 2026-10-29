"""Compare BCD entries without treating the final output newline as a change."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from review_probe import bootmgr_block


class BootInventoryComparison(unittest.TestCase):
    entry=('Windows Boot Manager\n--------------------\n'
           'identifier              {bootmgr}\n'
           'path                    \\EFI\\MICROSOFT\\BOOT\\BOOTMGFW.EFI\n'
           'timeout                 5')

    def test_last_block_equals_block_before_removable_entry(self):
        with_usb=self.entry+'\n\nFirmware Application\n--------------------\nidentifier {usb}\n'
        self.assertEqual(bootmgr_block(with_usb),bootmgr_block(self.entry+'\n'))

    def test_real_boot_path_change_is_not_ignored(self):
        changed=self.entry.replace('BOOTMGFW.EFI','CHANGED.EFI')
        self.assertNotEqual(bootmgr_block(self.entry+'\n'),bootmgr_block(changed+'\n'))

    def test_missing_windows_entry_rejected(self):
        with self.assertRaises(ValueError):
            bootmgr_block('Firmware Boot Manager\n---------------------\nidentifier {fwbootmgr}\n')


if __name__=='__main__':
    unittest.main()
