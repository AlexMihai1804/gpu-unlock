"""Review local TF32 experiment evidence; does not install, enroll or apply it."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_trust import pe_hash
from build import inspect_pe

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--vm-result', type=Path, required=True)
    p.add_argument('--diagnostic', type=Path, required=True)
    p.add_argument('--regression-build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    for key, value in vars(args).items():
        if not value.resolve().is_relative_to(ROOT):
            p.error('All evidence paths must be in this workspace: ' + key)
    if args.output.exists():
        p.error('Output already exists')
    built = read(args.build_root/'build-report.json')
    native = read(args.build_root/'saved-board-full-ss1/report.json')
    vm, diagnostic = read(args.vm_result), read(args.diagnostic)
    package = read(args.package/'MANIFEST.json')
    regression = read(args.regression_build/'tests/report.json')
    original = read(ROOT/'build/automatic-20261025-v2/build-report.json')
    rebuilt_default = read(args.regression_build/'build-report.json')
    image = args.build_root/'M6501-TF32-SS1-CANDIDATE.EFI'
    pe = inspect_pe(image)
    mok = pe_hash(image.read_bytes())[0].hex()
    checks = {}
    checks['separate_manual_image'] = (built.get('automatic_mode') is False
        and built.get('physical_confirmation_key') == 'T'
        and built.get('experimental_private_directory') == 'EFI/M6501TF32'
        and built.get('board_evidence_ready') is True)
    checks['pinned_upstream_core_retained'] = (built['original_core_sha256']
        == built['patched_core_sha256']
        == sha(args.build_root/'generated/unlock_610_ss1_full.c'))
    checks['saved_board_and_fault_scenarios_pass'] = (native['passed']
        and native.get('ss1_full_experiment') and native.get('transaction_scenarios') == 22
        and native['saved_board_preflight_cases'] == 14 and not native['hardware_executed'])
    checks['virtual_secure_boot_and_internal_io_pass'] = (vm['passed']
        and vm['image_sha256'] == pe['sha256']
        and vm['candidate_pe_authenticode_sha256'] == mok and not vm['hardware_executed'])
    checks['default_ss0_core_unchanged'] = (original['patched_core_sha256']
        == rebuilt_default['patched_core_sha256'])
    checks['regression_groups_pass'] = bool(regression['results']) and all(
        row['passed'] for row in regression['results']) and not regression['hardware_executed']
    checks['diagnostic_correct_no_clock_change'] = (diagnostic['passed']
        and diagnostic['offsets_unchanged']
        and all(row['offset'] == 0 for row in diagnostic['offsets_after'].values())
        and diagnostic['tf32_outputs_bit_identical_across_math_modes'])
    tf32 = [row for row in diagnostic['results'] if row['mode'] == 'tf32']
    checks['tf32_tensor_kernels_observed'] = len(tf32) == 4 and all(
        row['correctness_passed'] and row['kernels'] and all(
            'tensorop_s1688gemm' in kernel['kernel'] for kernel in row['kernels']) for row in tf32)
    checks['package_identity_matches'] = (package['candidate_sha256'] == pe['sha256']
        and package['candidate_pe_authenticode_sha256'] == mok
        and package['mode'] == 'manual-tf32-ss1-experiment')
    bad = []
    for relative, expected in package['files'].items():
        target = (args.package/relative).resolve()
        if (not target.is_relative_to(args.package.resolve())
                or not relative.startswith('EFI/M6501TF32/') or sha(target) != expected):
            bad.append(relative)
    checks['separate_package_files_verified'] = not bad and bool(package['files'])
    passed = all(checks.values())
    report = dict(preparation_passed=passed, checks=checks,
        prepared_locally=True, installed=False, mok_enrolled=False,
        physical_test_authorized=False, hardware_ss1_tested=False,
        tf32_gain_on_this_laptop_validated=False,
        candidate_image=str(image.resolve()), file_sha256=pe['sha256'], pe_authenticode_sha256=mok,
        package=str(args.package.resolve()), package_manifest_sha256=sha(args.package/'MANIFEST.json'),
        physical_confirmation_key='T', private_directory='EFI/M6501TF32',
        expected_entry_ss1='0x3', requested_ss1='0x8', original_automatic_installation_replaced=False,
        regression_groups=len(regression['results']), bad_package_paths=bad,
        next='Separate approval for installation/manual boot and exact additional MOK hash; no automatic replacement',
        evidence_sha256={str(path.resolve().relative_to(ROOT)): sha(path) for path in
            (args.build_root/'build-report.json', args.build_root/'saved-board-full-ss1/report.json',
             args.vm_result, args.diagnostic, args.regression_build/'tests/report.json')})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
