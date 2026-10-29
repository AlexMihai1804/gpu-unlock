import base64
from pathlib import Path
import struct
import sys
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from internal_boot import load_option, inspect, ESP, SHIM


class InternalBootOption(unittest.TestCase):
    def setUp(self):
        self.partition={'disk':1,'partition_number':4,'guid':'12345678-1234-5678-9abc-def012345678',
                        'gpt_type':ESP,'offset':2047873105920,'size':536870912}

    def test_standard_GPT_node_round_trip(self):
        data=load_option(self.partition)
        result=inspect(data)
        self.assertEqual(result['partition_guid'],self.partition['guid'])
        self.assertEqual(result['start_lba'],self.partition['offset']//512)
        self.assertEqual(result['size_lba'],1048576)
        self.assertEqual(result['path'],SHIM)
        self.assertEqual(struct.unpack_from('<IH',data)[0],1)

    def test_existing_Windows_disk_is_rejected(self):
        self.partition['disk']=0
        with self.assertRaises(ValueError): load_option(self.partition)

    def test_existing_data_partition_is_rejected(self):
        self.partition['partition_number']=3
        with self.assertRaises(ValueError): load_option(self.partition)

    def test_non_ESP_and_wrong_size_rejected(self):
        for key,value in [('gpt_type','ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'),('size',107374182400),('offset',123)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                load_option({**self.partition,key:value})

    def test_device_path_does_not_replace_Windows_loader(self):
        data=load_option(self.partition)
        self.assertNotIn('Microsoft'.encode('utf-16-le'),data)
        changed=data.replace('shimx64'.encode('utf-16-le'),'changed'.encode('utf-16-le'))
        with self.assertRaises(ValueError): inspect(changed)

    def test_truncation_and_trailing_bytes_rejected(self):
        data=load_option(self.partition)
        for changed in (data[:-4],data+b'junk'):
            with self.assertRaises(ValueError): inspect(changed)

    def test_explicit_tf32_profile_has_separate_path_and_label(self):
        data=load_option(self.partition,profile='tf32-automatic')
        decoded=inspect(data,profile='tf32-automatic')
        self.assertEqual(decoded['path'],'\\EFI\\M6501TF32\\shimx64.efi')
        self.assertIn('M6501 GPU FP16 BF16 TF32'.encode('utf-16-le'),data)
        self.assertNotIn('M6501GPU'.encode('utf-16-le'),data)
        with self.assertRaises(ValueError): inspect(data)
        with self.assertRaises(ValueError): load_option(self.partition,profile='unknown')


if __name__=='__main__': unittest.main()
