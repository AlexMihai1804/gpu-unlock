"""Prepare a separate manual SS1 experiment locally; no physical deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from audit_trust import pe_hash
from build import inspect_pe

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--automatic', action='store_true', help='Stage the explicitly requested automatic TF32 variant')
    args = p.parse_args()
    build, out = args.build_root.resolve(), args.output.resolve()
    if not build.is_relative_to(ROOT/'build') or not out.is_relative_to(ROOT/'build') or out.exists():
        p.error('Use an existing reviewed build and a NEW output below build/')
    report = json.loads((build/'build-report.json').read_text())
    tests = json.loads((build/'saved-board-full-ss1/report.json').read_text())
    if (not report.get('ss1_policy', '').startswith('EXPERIMENTAL:') or report.get('automatic_mode') != args.automatic
            or not report.get('board_evidence_ready')
            or report.get('physical_confirmation_key') != (None if args.automatic else 'T')
            or report.get('experimental_private_directory') != 'EFI/M6501TF32'
            or report['original_core_sha256'] != report['patched_core_sha256']
            or not tests['passed'] or not tests.get('ss1_full_experiment')
            or tests.get('transaction_scenarios') != 22 or tests['saved_board_preflight_cases'] != 14):
        p.error('Reviewed SS1 build with matching automatic/manual policy and saved-board tests required')
    if args.automatic and report.get('automatic_countdown_seconds')!=5:
        p.error('Automatic TF32 requires the five-second Esc countdown')
    image = build/('M6501-AUTOMATIC-TF32.EFI' if args.automatic else 'M6501-TF32-SS1-CANDIDATE.EFI')
    pe = inspect_pe(image)
    if pe['sha256'] != report['images'][image.name]['sha256']:
        p.error('The image differs from the reviewed build')
    mok = pe_hash(image.read_bytes())[0].hex()
    prefix = 'EFI/M6501TF32/'
    files = {prefix+'shimx64.efi': ROOT/'build/shim/shimx64.efi',
             prefix+'mmx64.efi': ROOT/'build/shim/mmx64.efi',
             prefix+'grubx64.efi': image,
             prefix+'LICENSE': ROOT/'LICENSE',
             prefix+'THIRD_PARTY_NOTICES.md': ROOT/'THIRD_PARTY_NOTICES.md'}
    for source in (ROOT/'build/firmware').iterdir():
        if source.is_file():
            files[prefix+'RTX-UNLOCK/ASSETS/'+source.name] = source
    for source in (ROOT/'vendor/rtx30-unlock/LICENSES').iterdir():
        if source.is_file():
            files[prefix+'LICENSES/'+source.name] = source
    for source in (ROOT/'build/shim').glob('*.copyright'):
        files[prefix+'LICENSES/'+source.name] = source
    for relative, source in files.items():
        target = out/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = dict(schema=1, mode='automatic-tf32-ss1-experiment' if args.automatic else 'manual-tf32-ss1-experiment',
        prepared_locally=True, installed=False, hardware_tested=False,
        physical_test_authorized=False, mok_enrolled=False,
        private_directory='EFI/M6501TF32', boot_path='\\EFI\\M6501TF32\\shimx64.efi',
        candidate_sha256=pe['sha256'], candidate_pe_authenticode_sha256=mok,
        selectors=dict(ss0='0x88888888', ss1_entry='0x3', ss1_target='0x8'),
        manual_confirmation_key=None if args.automatic else 'T', automatic_boot_order_change=False,
        proposed_default_boot=args.automatic, countdown_seconds=5 if args.automatic else None,
        existing_automatic_package_replaced=False,
        files={relative: sha(out/relative) for relative in sorted(files)},
        bytes=sum((out/relative).stat().st_size for relative in files))
    (out/'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in manifest.items() if key != 'files'}, indent=2))


if __name__ == '__main__':
    main()
