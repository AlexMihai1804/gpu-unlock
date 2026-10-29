"""Test the real manual candidate's shim/MOK acceptance in an isolated NVMe VM.

No GPU is emulated: the expected result is rejection before any hardware writes.
The virtual MOK list lives in a workspace file; host firmware is never accessed.
"""
import argparse
import json
from pathlib import Path
import time

from audit_trust import pe_hash
import vm_lab as lab


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    args = p.parse_args()
    image = args.image.resolve()
    if not image.is_relative_to(lab.ROOT/'build') or image.name != 'M6501-TF32-SS1-CANDIDATE.EFI':
        p.error('Use the separate local TF32 candidate')
    folder = lab.within(lab.VM/('tf32-manual-internal-'+time.strftime('%Y%m%d-%H%M%S')))
    folder.mkdir(parents=True)
    mok = pe_hash(image.read_bytes())[0].hex()
    files = {'EFI/BOOT/BOOTX64.EFI': (lab.ROOT/'build/shim/shimx64.efi').read_bytes(),
             'EFI/BOOT/mmx64.efi': (lab.ROOT/'build/shim/mmx64.efi').read_bytes(),
             'EFI/BOOT/grubx64.efi': image.read_bytes(),
             'EFI/M6501TF32/RTX-UNLOCK/VM-ONLY.txt': b'NO PHYSICAL GPU OR HOST DISKS\n'}
    lab.gpt_image(folder/'USB.img', files)
    lab.seed_vars(folder/'VARS.fd', mok, mok, 'p')
    result = lab.run_vm(folder, 25, internal=True)
    from pyfatfs.PyFatFS import PyFatFS
    with PyFatFS(str(folder/'USB.img'), offset=lab.OFFSET) as fs:
        log = fs.readtext('EFI/M6501TF32/RTX-UNLOCK/RUN00/UNLOCK.TXT')
    required = ('MANUAL TF32 / SS1 FULL EXPERIMENT',
                'SECURE SecureBoot=1 SetupMode=0', 'SMBIOS M6501RM_product=1 BIOS_313=1',
                'TARGET exact_matches=0', 'GPU_MMIO_writes=0')
    passed = (all(item in log for item in required) and 'TRANSACTION result=' not in log
              and 'MEM_ENABLE' not in log and 'selector write:' not in log)
    result.update(passed=passed, image_sha256=lab.digest(image),
        candidate_pe_authenticode_sha256=mok, directory=str(folder), private_log=log,
        hardware_executed=False, gpu_emulated=False, host_disks_attached=False,
        scope='Actual manual candidate on virtual NVMe: shim/MOK acceptance, private IO, missing-GPU refusal',
        limitation='Does not test ASUS firmware, physical GPU unlock, TF32 gain or Windows driver handoff')
    (folder/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('qmp_greeting', 'private_log')}, indent=2))
    print(log)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
