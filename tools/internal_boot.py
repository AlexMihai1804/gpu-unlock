"""Encode/inspect an EFI load option for the dedicated internal FAT32 partition.

Pure bytes and local JSON only. This module never accesses firmware or disks.
"""
import argparse
import base64
import json
from pathlib import Path
import struct
import uuid

ESP='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
SHIM='\\EFI\\M6501GPU\\shimx64.efi'
PROFILES = {'automatic': (SHIM, 'M6501 GPU automatic'),
            'tf32-automatic': ('\\EFI\\M6501TF32\\shimx64.efi', 'M6501 GPU FP16 BF16 TF32')}


def load_option(partition,sector_size=512,*,profile='automatic'):
    if profile not in PROFILES:
        raise ValueError('Unknown boot profile')
    if (partition['disk']!=1 or partition['size']!=536870912 or
        uuid.UUID(partition['gpt_type'].strip('{}'))!=uuid.UUID(ESP) or
        partition['offset']%sector_size or partition['size']%sector_size or
        partition['partition_number']<=3 or sector_size!=512):
        raise ValueError('Expected the new dedicated 512 MiB ESP on disk 1')
    guid=uuid.UUID(partition['guid'].strip('{}'))
    if guid.int==0:
        raise ValueError('Partition GUID must be assigned by Windows')
    hd=struct.pack('<BBHIQQ16sBB',4,1,42,partition['partition_number'],
                   partition['offset']//sector_size,partition['size']//sector_size,guid.bytes_le,2,2)
    shim, label = PROFILES[profile]
    name=(shim+'\0').encode('utf-16-le')
    filepath=struct.pack('<BBH',4,4,4+len(name))+name
    device_path=hd+filepath+b'\x7f\xff\x04\x00'
    description=(label+'\0').encode('utf-16-le')
    return struct.pack('<IH',1,len(device_path))+description+device_path


def inspect(data,*,profile='automatic'):
    if profile not in PROFILES:
        raise ValueError('Unknown boot profile')
    shim, label = PROFILES[profile]
    attributes,size=struct.unpack_from('<IH',data)
    end=6
    while end+2<=len(data) and data[end:end+2]!=b'\0\0':
        end+=2
    start=end+2
    if start+size!=len(data) or attributes!=1:
        raise ValueError('Unexpected load-option length/attributes')
    path=data[start:]
    kind,subtype,length,number,lba,sectors,guid,mbr,signature=struct.unpack_from('<BBHIQQ16sBB',path)
    if (kind,subtype,length,mbr,signature)!=(4,1,42,2,2):
        raise ValueError('Expected GPT hard-drive node')
    kind,subtype,length=struct.unpack_from('<BBH',path,42)
    if (kind,subtype)!=(4,4) or path[42+length:]!=b'\x7f\xff\x04\x00':
        raise ValueError('Unexpected file path or end node')
    filename=path[46:42+length].decode('utf-16-le')
    if filename!=shim+'\0':
        raise ValueError('Only the private shim path is allowed')
    return {'partition_number':number,'start_lba':lba,'size_lba':sectors,
            'partition_guid':str(uuid.UUID(bytes_le=guid)),'path':shim,'attributes':attributes}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--partition-info',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',choices=tuple(PROFILES),default='automatic')
    a=p.parse_args()
    if a.output.exists():
        p.error('Output exists')
    partition=json.loads(a.partition_info.read_text(encoding='utf-8-sig'))
    data=load_option(partition,profile=a.profile)
    a.output.write_text(json.dumps({'base64':base64.b64encode(data).decode(),
                                   'decoded':inspect(data,profile=a.profile)},indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
