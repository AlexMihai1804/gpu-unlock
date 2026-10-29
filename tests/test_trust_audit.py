import importlib.util
from pathlib import Path
import struct
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trust_audit",ROOT/"tools/audit_trust.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustPrecheck(unittest.TestCase):
    def test_esl_bounds_and_sha256_entry(self):
        raw=uuid.UUID(module.SHA256).bytes_le+struct.pack("<III",76,0,48)+bytes(16)+bytes(range(32))
        self.assertEqual(module.esl(raw)[0]["data"],bytes(range(32)))
        for truncated in (raw[:27],raw[:-1]):
            with self.assertRaises(ValueError): module.esl(truncated)

    def test_shim_hash_matches_both_embedded_signed_content_digests(self):
        raw=(ROOT/"build/shim/shimx64.efi").read_bytes()
        digest,at,size=module.pe_hash(raw)
        self.assertEqual(digest.hex(),"f4166948f7adafa71e45c7ca5d30d97f78f382ecf1e3c8e4767b1ec1770cd52f")
        stop=at+size
        count=0
        while at<stop:
            length=struct.unpack_from("<I",raw,at)[0]
            embedded,_=module.pkcs7_details(raw[at+8:at+length])
            self.assertEqual(digest,embedded)
            at+=(length+7)&~7
            count+=1
        self.assertEqual(count,2)

    def test_checksum_excluded_and_code_changes_detected(self):
        raw=bytearray((ROOT/"build/M6501-PROBE.EFI").read_bytes())
        before=module.pe_hash(raw)[0]
        pe=struct.unpack_from("<I",raw,0x3c)[0]
        raw[pe+24+64]^=1
        self.assertEqual(before,module.pe_hash(raw)[0])
        headers=struct.unpack_from("<I",raw,pe+24+60)[0]
        raw[headers]^=1
        self.assertNotEqual(before,module.pe_hash(raw)[0])
