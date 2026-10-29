"""A normal control must retain both the latest attempt and historical USB logs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from review_normal_return import expected_usb_logs, validate_unchanged_logs


class NormalReturnInventory(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous=Path(self.temp.name)
        self.log=self.previous/'RTX-UNLOCK/RUN07/UNLOCK.TXT'
        self.log.parent.mkdir(parents=True)
        data=b'saved new transaction\n'
        self.log.write_bytes(data)
        digest=hashlib.sha256(data).hexdigest()
        self.expected={'RUN06/UNLOCK.TXT':'historic','RUN07/UNLOCK.TXT':digest}
        self.write('evidence-hashes.json',[{'file':'RUN07/UNLOCK.TXT','bytes':len(data),'sha256':digest}])
        self.write('usb-log-inventory.json',[{'file':k,'sha256':v} for k,v in self.expected.items()])

    def write(self,name,value):
        (self.previous/name).write_text(json.dumps(value),encoding='utf-8')

    def observed(self):
        return [{'file':k,'sha256':v} for k,v in self.expected.items()]

    def test_new_attempt_archive_keeps_historical_inventory(self):
        expected=expected_usb_logs(self.previous)
        self.assertEqual(validate_unchanged_logs(expected,self.observed()),self.expected)

    def test_additional_USB_launch_rejected(self):
        rows=self.observed()+[{'file':'RUN08/UNLOCK.TXT','sha256':'unexpected'}]
        with self.assertRaises(ValueError):
            validate_unchanged_logs(self.expected,rows)

    def test_historical_log_change_rejected(self):
        rows=self.observed()
        rows[0]['sha256']='changed'
        with self.assertRaises(ValueError):
            validate_unchanged_logs(self.expected,rows)

    def test_tampered_saved_transaction_rejected(self):
        self.log.write_bytes(b'changed archive')
        with self.assertRaises(ValueError):
            expected_usb_logs(self.previous)

    def test_inventory_cannot_omit_archived_transaction(self):
        self.write('usb-log-inventory.json',[{'file':'RUN06/UNLOCK.TXT','sha256':'historic'}])
        with self.assertRaises(ValueError):
            expected_usb_logs(self.previous)


if __name__=='__main__':
    unittest.main()
