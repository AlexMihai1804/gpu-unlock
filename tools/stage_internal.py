"""Stage a dedicated internal ESP package in build/; never installs it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from audit_trust import pe_hash
from build import inspect_pe

ROOT=Path(__file__).resolve().parents[1]
SHA=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    build,out=a.build_root.resolve(),a.output.resolve()
    if not build.is_relative_to(ROOT/'build') or not out.is_relative_to(ROOT/'build') or out.exists():
        p.error('Use a completed build and a new output under build/')
    report=json.loads((build/'build-report.json').read_text())
    if not report.get('automatic_mode') or not report['board_evidence_ready']:
        p.error('Reviewed automatic build required')
    image=build/'M6501-AUTOMATIC.EFI'
    inspect_pe(image)
    mok=pe_hash(image.read_bytes())[0].hex()
    previous=json.loads((ROOT/'build/candidate-20261025-v3/build-report.json').read_text())
    if report['patched_core_sha256']!=previous['patched_core_sha256']:
        p.error('GPU transaction core differs from the physically validated v3')
    prefix='EFI/M6501GPU/'
    files={prefix+'shimx64.efi':ROOT/'build/shim/shimx64.efi',prefix+'mmx64.efi':ROOT/'build/shim/mmx64.efi',
           prefix+'grubx64.efi':image,prefix+'LICENSE':ROOT/'LICENSE',prefix+'THIRD_PARTY_NOTICES.md':ROOT/'THIRD_PARTY_NOTICES.md'}
    for f in (ROOT/'build/firmware').iterdir():
        if f.is_file():files[prefix+'RTX-UNLOCK/ASSETS/'+f.name]=f
    for f in (ROOT/'vendor/rtx30-unlock/LICENSES').iterdir():
        if f.is_file():files[prefix+'LICENSES/'+f.name]=f
    for f in (ROOT/'build/shim').glob('*.copyright'):
        files[prefix+'LICENSES/'+f.name]=f
    for name,source in files.items():
        destination=out/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    info=out/prefix/'INSTALL-INFO.txt'
    info.write_text('M6501RM automatic internal UEFI image. PREPARATION ONLY.\n'
                    'Secure Boot remains active. This is not GRUB.\n'
                    'Five second Esc cancellation; otherwise automatic unlock.\n'
                    'Install only on the reviewed new dedicated 512 MiB FAT32 ESP.\n'
                    'Do not put these 85 MB assets in the full Windows ESP.\n'
                    'MOK SHA256: '+mok+'\n',encoding='utf-8')
    staged={f.relative_to(out).as_posix():SHA(f) for f in sorted(out.rglob('*')) if f.is_file()}
    manifest={'mode':'automatic-internal','hardware_tested':False,'installed':False,'mok_enrolled':False,
              'candidate_sha256':SHA(image),'candidate_pe_authenticode_sha256':mok,'countdown_seconds':5,
              'gpu_core_identical_to_validated_v3':True,'boot_path':'\\EFI\\M6501GPU\\shimx64.efi',
              'files':staged,'bytes':sum((out/name).stat().st_size for name in staged)}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))


if __name__=='__main__':main()
