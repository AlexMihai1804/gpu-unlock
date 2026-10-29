"""One isolated internal-NVMe/OVMF boot of the real automatic image.

No NVIDIA GPU is emulated. It must log a rejected GPU preflight and start the
real signed Windows loader, which stops at the deliberately missing VM BCD.
"""
import argparse
import json
import os
from pathlib import Path
import time

from audit_trust import pe_hash
import vm_lab as lab


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--profile',choices=('ss0','tf32'),default='ss0')
    a=p.parse_args()
    image=a.image.resolve()
    if not image.is_relative_to(lab.ROOT/'build'):
        p.error('Use a local build image')
    if a.profile=='tf32' and image.name!='M6501-AUTOMATIC-TF32.EFI':
        p.error('Use the separate automatic TF32 image')
    private='EFI/M6501TF32' if a.profile=='tf32' else 'EFI/M6501GPU'
    folder=lab.within(lab.VM/('automatic-internal-'+time.strftime('%Y%m%d-%H%M%S')))
    folder.mkdir(parents=True)
    digest=pe_hash(image.read_bytes())[0].hex()
    files={'EFI/BOOT/BOOTX64.EFI':(lab.ROOT/'build/shim/shimx64.efi').read_bytes(),
           'EFI/BOOT/mmx64.efi':(lab.ROOT/'build/shim/mmx64.efi').read_bytes(),
           'EFI/BOOT/grubx64.efi':image.read_bytes(),
           'EFI/Microsoft/Boot/bootmgfw.efi':(Path(os.environ['SystemRoot'])/'Boot/EFI/bootmgfw.efi').read_bytes(),
           private+'/RTX-UNLOCK/VM-ONLY.txt':b'NO PHYSICAL GPU OR USER DISK\n'}
    lab.gpt_image(folder/'USB.img',files)
    lab.seed_vars(folder/'VARS.fd',digest,digest,'p')
    result=lab.run_vm(folder,25,internal=True)
    from pyfatfs.PyFatFS import PyFatFS
    with PyFatFS(str(folder/'USB.img'),offset=lab.OFFSET) as fs:
        log=fs.readtext(private+'/RTX-UNLOCK/RUN0000/UNLOCK.TXT')
    serial=(folder/'serial.log').read_text(errors='replace')
    required=('SECURE SecureBoot=1 SetupMode=0','SMBIOS M6501RM_product=1 BIOS_313=1',
              'TARGET exact_matches=0','AUTOBOOT: skipped before GPU writes',
              'WINDOWS_PRELOAD status=0 unique_GUID_match=1')
    passed=(all(x in log for x in required) and 'TRANSACTION result=' not in log and 'MEM_ENABLE' not in log and
            'Windows Boot Manager' in serial and '\\EFI\\Microsoft\\Boot\\BCD' in serial and '0xc000000f' in serial)
    if a.profile=='tf32':
        passed=passed and 'AUTOMATIC TF32 / SS1 FULL EXPERIMENT' in log
    result.update(passed=passed,scope='Actual automatic image on emulated internal NVMe/ESP with Secure Boot and MOK; no physical GPU/disks/network',
                  image_sha256=lab.digest(image),private_log=log,hardware_executed=False,
                  limitation='GPU absence rejection/fallback only; does not validate automatic unlock execution on the laptop',
                  directory=str(folder),profile=a.profile,private_directory=private)
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('qmp_greeting','private_log')},indent=2))
    print(log)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
