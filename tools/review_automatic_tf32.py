"""Bind the automatic TF32 package, tests, fresh read-only preflight and installer."""
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path

from audit_trust import SHA256, esl, pe_hash
from build import inspect_pe

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build=ROOT/'build/automatic-tf32-20261026-v1'
    package=ROOT/'build/automatic-tf32-release-20261026-v1'
    preflight=ROOT/'results/tf32-update-preflight-20261026-191804'
    vm_path=ROOT/'build/vm-lab/automatic-internal-20261026-192045/result.json'
    built=read(build/'build-report.json')
    native=read(build/'saved-board-full-ss1/report.json')
    vm=read(vm_path)
    inspect=read(preflight/'tf32-preflight.json')
    boot={row['name']:row for row in read(preflight/'boot-variables.json')}
    collection=read(preflight/'collection-complete.json')
    manifest=read(package/'MANIFEST.json')
    image=build/'M6501-AUTOMATIC-TF32.EFI'
    pe=inspect_pe(image)
    mok=pe_hash(image.read_bytes())[0].hex()
    if (not inspect['completed'] or not collection['completed']
        or inspect['partition_guid'].strip('{}')!='33333333-3333-4333-8333-333333333333'
        or inspect['partition_offset']!=2047869976576 or inspect['partition_size']!=536870912
        or inspect['filesystem']!='FAT32' or inspect['volume_label']!='M6501GPU'
        or inspect['free_bytes']<manifest['bytes']+16777216):
        raise ValueError('Fresh original installation preflight incomplete or target differs')
    if (not built.get('automatic_mode') or built.get('automatic_countdown_seconds')!=5
        or built.get('automatic_private_directory')!='EFI/M6501TF32'
        or not built.get('ss1_policy','').startswith('EXPERIMENTAL:')
        or built['original_core_sha256']!=built['patched_core_sha256']
        or not native['passed'] or native['transaction_scenarios']!=22
        or native['saved_board_preflight_cases']!=14
        or not vm['passed'] or vm.get('profile')!='tf32' or vm['image_sha256']!=pe['sha256']):
        raise ValueError('Automatic full-selector build/test evidence missing or mismatched')
    if manifest['candidate_sha256']!=pe['sha256'] or manifest['candidate_pe_authenticode_sha256']!=mok:
        raise ValueError('Package candidate differs')
    for name,digest in manifest['files'].items():
        path=(package/name).resolve()
        if not path.is_relative_to(package) or not name.startswith('EFI/M6501TF32/') or sha(path)!=digest:
            raise ValueError('Package path/hash mismatch')
    denied=[]
    for name in ('dbx','MokListXRT'):
        path=preflight/'trust'/(name+'.bin')
        if path.exists():
            denied.extend(row['data'].hex() for row in esl(path.read_bytes()) if row['type']==SHA256)
    if mok in denied or pe['sha256'] in denied:
        raise ValueError('Candidate hash is in freshly exported revocations')
    tests=(build/'python-tests.log').read_text(encoding='utf-8')
    if 'Ran 46 tests' not in tests or '\nOK\n' not in tests:
        raise ValueError('Required Python regression tests missing')
    support=('scripts/Install-AutomaticTf32.ps1','scripts/BootVariables.cs',
        'scripts/Restore-PreviousGpuBoot.ps1','scripts/Disable-InternalAutomatic.ps1',
        'tools/internal_boot.py','tools/build.py','uefi/m6501.c','uefi/automatic_boot.h',
        'config/board.reviewed.json')
    report=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        mode='automatic-tf32-ss1-experiment',local_validation_passed=True,
        file_sha256=pe['sha256'],pe_authenticode_sha256=mok,
        build=build.relative_to(ROOT).as_posix(),package=package.relative_to(ROOT).as_posix(),
        manifest_sha256=sha(package/'MANIFEST.json'),countdown_seconds=5,cancel_key='Esc',
        disk_serial=inspect['disk_serial'],disk_size=inspect['disk_size'],
        existing_partition_guid='33333333-3333-4333-8333-333333333333',
        partition_resized=False,windows_loader_replaced=False,
        private_directory='EFI/M6501TF32',preserve_old_automatic=True,
        preflight=preflight.relative_to(ROOT).as_posix(),
        preflight_boot_order_base64=boot['BootOrder']['base64'],
        preflight_entries={name:boot[name]['base64'] for name in ('Boot0000','Boot0001')},
        python_tests_passed=46,transaction_scenarios_passed=22,saved_board_preflight_cases=14,
        virtual_secure_boot_and_windows_fallback_passed=True,
        candidate_not_in_exported_revocations=True,installed=False,mok_enrolled=False,
        physical_ss1_executed=False,tf32_gain_on_this_laptop_validated=False,
        supporting_files={name:sha(ROOT/name) for name in support},
        evidence_files={str(path.relative_to(ROOT)):sha(path) for path in
            (build/'build-report.json',build/'saved-board-full-ss1/report.json',vm_path,
             build/'python-tests.log',preflight/'tf32-preflight.json',preflight/'boot-variables.json')})
    out=ROOT/'results/automatic-tf32-ready.json'
    if out.exists():
        raise ValueError('A reviewed plan already exists; use a new revision')
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items()
                      if key not in ('supporting_files','evidence_files','preflight_entries')},indent=2))


if __name__=='__main__':
    main()
