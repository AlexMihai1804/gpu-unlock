"""Offline review of the installed automatic image, its boot log and live-boot evidence."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from audit_trust import esl, SHA256, pe_hash
from review_probe import bootmgr_block

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bench'))
from compare import compare
from endurance import known_network_warning
from performance_state import classify


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def review(evidence, benchmark=None):
    manifest = read(ROOT/'build/internal-release-20261025-v1/MANIFEST.json')
    image = (ROOT/'build/automatic-20261025-v2/M6501-AUTOMATIC.EFI').read_bytes()
    assert hashlib.sha256(image).hexdigest() == manifest['candidate_sha256']
    assert pe_hash(image)[0].hex() == manifest['candidate_pe_authenticode_sha256']
    installed = read(evidence/'installed-files.json')
    assert {row['file']: row['sha256'] for row in installed} == manifest['files']
    archived = read(evidence/'evidence-hashes.json')
    if isinstance(archived, dict):
        archived = [archived]
    for entry in archived:
        raw = (evidence/'RTX-UNLOCK'/entry['file']).read_bytes()
        assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
    logs = sorted((evidence/'RTX-UNLOCK').glob('RUN[0-9][0-9][0-9][0-9]/UNLOCK.TXT'))
    assert logs, 'No automatic boot log'
    log = logs[-1]
    text = log.read_text(encoding='ascii')
    cold = re.search(r'COLD chip=0xb76000a1 fb_mib=6144 ss0=0x[0-9a-f]+ ss1=(0x[0-9a-f]+)', text)
    assert cold, 'Missing exact-board cold state'
    ss1 = int(cold[1], 16)
    required = [
        'RTX GA10x UEFI unlock automatic internal boot',
        'SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero',
        'SMBIOS M6501RM_product=1 BIOS_313=1', 'TARGET exact_matches=1',
        'GOP owner=16811002 independent_AMD=1',
        'AUTOBOOT: countdown complete; all hardware checks remain required.',
        'MEM_ENABLE status=0 command=0x2 attributes=0x200',
        'PROM_SHA256 dce995afb0e825c9640488b55054179ebc15c77d38c00ed45a05f7e2701433e7',
        'FUSE_PREFLIGHT booter_raw=0x1 version=1 FWSEC_raw=0x3 version=2 sig_offset=0x300 result=0',
        'WINDOWS_PRELOAD status=0 unique_GUID_match=1',
        'Bus Master enabled: command=0x6 attributes=0x600 matched=1',
        'FWSEC result: scratch=0 expected_hi16=0',
        f'SS1 preserved: actual={ss1:#x} expected={ss1:#x} (no write)',
        f'pre-FLR selectors: ss0=0x88888888 expected=0x88888888 ss1={ss1:#x} expected={ss1:#x}',
        'post-FLR GFW result: error=0 pci=0x252010de plm=0x8b8f boot=0x3ff cpuctl=0x10',
        f'post-FLR SEC2 reset released, GSP halted, BME=0 pending=0 WPR2=1ffffe00:00000000 SS0=88888888 SS1={ss1:08x}',
        'TRANSACTION result=0 contained=0 FLRs=1 maps=0 retained=0 quiesced=1 fault=0',
        f'FINAL_SELECTORS SS0=0x88888888 SS1={ss1:#x} preserved_SS1={ss1:#x}',
        'MEM_RESTORE status=0 confirmed=1 command=0',
        'HANDOFF clean resources, original PCI attributes, existing Windows Boot Manager']
    assert all(line in text for line in required), 'Incomplete successful transaction'
    assert 'STOP.' not in text and 'failure unlock_610.c:' not in text and 'selector write: SS1' not in text
    assert text.count('selector write: SS0=0x88888888') == 1
    assert text.count('PCIe FLR returned: result=0') == 1
    assert re.search(r'FWSEC halt observation: first=\w+ last=\w+ samples=\d+ observed_nonhalt=1 requested_wait_us=\d+ error=0', text)
    match = re.search(r'FWSEC WPR2: low=(0x[0-9a-f]+) high=(0x[0-9a-f]+) expected_page=(0x[0-9a-f]+) end=(0x[0-9a-f]+)', text)
    assert match, 'FWSEC range missing'
    low, high, page, end = [int(value, 16) for value in match.groups()]
    assert low >> 4 == page and page << 12 <= (high >> 4) << 12 < end
    before = ROOT/'results/uefi-readonly-20261025-161851'
    post = evidence/'trust'
    same = {name: (post/(name+'.bin')).read_bytes() == (before/(name+'.bin')).read_bytes() for name in ('PK','KEK','db','dbx')}
    mok = {entry['data'].hex() for entry in esl((post/'MokListRT.bin').read_bytes()) if entry['type'] == SHA256}
    previous = {entry['data'].hex() for entry in esl((ROOT/'results/uefi-post-unlock-B2-20261025-215254/MokListRT.bin').read_bytes()) if entry['type'] == SHA256}
    order_data = (evidence/'BootOrder.bin').read_bytes()
    order = list(struct.unpack('<'+'H'*(len(order_data)//2), order_data))
    old = read(ROOT/'results/internal-install-20261025-223906/boot-backup.json')
    activation = read(ROOT/'results/internal-install-20261025-223906/activation-state.json')
    trust = dict(secure_boot=(post/'SecureBoot.bin').read_bytes() == b'\x01',
        setup_mode_zero=(post/'SetupMode.bin').read_bytes() == b'\x00',
        shim_validation_enabled=not (post/'MokSBStateRT.bin').exists() or (post/'MokSBStateRT.bin').read_bytes() == b'\x00',
        platform_trust_unchanged=same,
        automatic_hash_present_in_MOK=manifest['candidate_pe_authenticode_sha256'] in mok,
        previous_MOK_hashes_preserved=previous <= mok,
        windows_boot_manager_entry_unchanged=bootmgr_block((post/'boot-entries.txt').read_text(encoding='utf-8-sig')) == bootmgr_block((before/'boot-entries.txt').read_text(encoding='utf-8-sig')),
        old_Boot0001_byte_identical=(evidence/'Boot0001.bin').read_bytes() == base64.b64decode(old['entries']['Boot0001']),
        automatic_Boot0000_byte_identical=(evidence/'Boot0000.bin').read_bytes() == base64.b64decode(activation['payload_base64']),
        automatic_first_windows_second=order[:2] == [0, 1],
        BootOrder=order, BootCurrent=int.from_bytes((evidence/'BootCurrent.bin').read_bytes(), 'little'))
    trust['passed'] = all(trust[key] for key in ('secure_boot','setup_mode_zero','shim_validation_enabled',
        'automatic_hash_present_in_MOK','previous_MOK_hashes_preserved','windows_boot_manager_entry_unchanged',
        'old_Boot0001_byte_identical','automatic_Boot0000_byte_identical','automatic_first_windows_second')) and all(same.values()) and trust['BootCurrent'] == 0
    result = dict(scope='Automatic boot transaction/trust evidence; live performance checked separately',
        transaction_passed=True, trust=trust, log=str(log),
        log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(), observed_automatic_logs=len(logs),
        ss1_preserved=hex(ss1), windows_return=read(evidence/'windows-return.json'),
        automatic_image_sha256=manifest['candidate_sha256'],
        evidence_is_tpm_attestation=False, current_performance_established=False)
    health = read(evidence/'health-before/boot-control.json')
    unexpected = [event for event in health['events'] if not known_network_warning(event)]
    result.update(unexpected_driver_or_WHEA_events=len(unexpected),
        known_corrected_network_events=sum(known_network_warning(event) for event in health['events']))
    assert not unexpected, 'Unexpected driver/hardware events in this Windows boot'
    if benchmark is not None:
        data = read(benchmark)
        assert datetime.fromisoformat(data['utc']) >= datetime.fromisoformat(result['windows_return']['windows_boot_utc']), 'Benchmark predates this Windows boot'
        comparison = compare(read(ROOT/'results/baseline-2026-10-25.json'), data)
        modes = {row['mode']: row for row in data['results']}
        ratios = {mode: modes[mode]['tflops']/modes['tf32']['tflops'] for mode in ('fp16','bf16')}
        performance_state=classify(data)
        result.update(benchmark=str(benchmark), comparison=comparison, tensor_to_tf32_ratios=ratios,
            current_performance_established=True,
            performance_matches_unlocked_pattern=performance_state['unlocked_performance_supported'],
            performance_state=performance_state,
            all_outputs_bit_identical=all(row['output_bit_identical'] for row in comparison),
            control_modes_within_5_percent=all(abs(row['gain_percent']) < 5 for row in comparison if row['mode'] in ('tf32','fp32')))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path)
    args = parser.parse_args()
    result = review(args.evidence.resolve(), args.benchmark)
    (args.evidence/'automatic-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['trust']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
