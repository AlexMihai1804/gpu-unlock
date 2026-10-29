"""Review the physical automatic SS1=8 boot and matched numerical benchmarks."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from audit_trust import SHA256, esl, pe_hash

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bench'))
from compare import compare
from endurance import known_network_warning
from performance_state import active_modes


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition,message):
    if not condition:
        raise ValueError(message)


def validate_log(text):
    required=(
        'AUTOMATIC TF32 / SS1 FULL EXPERIMENT',
        'SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero',
        'SMBIOS M6501RM_product=1 BIOS_313=1','TARGET exact_matches=1',
        'GOP owner=16811002 independent_AMD=1',
        'AUTOBOOT: countdown complete; all hardware checks remain required.',
        'PROM_SHA256 dce995afb0e825c9640488b55054179ebc15c77d38c00ed45a05f7e2701433e7',
        'FUSE_PREFLIGHT booter_raw=0x1 version=1 FWSEC_raw=0x3 version=2 sig_offset=0x300 result=0',
        'FWSEC result: scratch=0 expected_hi16=0',
        'selector read: SS1=0x3 expected_unlock=0x8',
        'pre-FLR selectors: ss0=0x88888888 expected=0x88888888 ss1=0x8 expected=0x8',
        'post-FLR GFW result: error=0 pci=0x252010de plm=0x8b8f boot=0x3ff cpuctl=0x10',
        'post-FLR SEC2 reset released, GSP halted, BME=0 pending=0 WPR2=1ffffe00:00000000 SS0=88888888 SS1=00000008',
        'TRANSACTION result=0 contained=0 FLRs=1 maps=0 retained=0 quiesced=1 fault=0',
        'FINAL_SELECTORS SS0=0x88888888 SS1=0x8 target_SS1=8 entry_SS1=0x3 EXPERIMENT=1',
        'MEM_RESTORE status=0 confirmed=1 command=0',
        'HANDOFF clean resources, original PCI attributes, existing Windows Boot Manager')
    require(all(item in text for item in required),'Incomplete successful SS1=8 transaction')
    require('STOP.' not in text and 'failure ' not in text,'Failure/STOP in boot log')
    for line in ('selector write: SS0=0x88888888','selector write: SS1=0x8','PCIe FLR returned: result=0'):
        require(text.count(line)==1,'Missing or repeated transaction: '+line)
    require(bool(re.search(r'FWSEC halt observation: .*observed_nonhalt=1 .*error=0',text)),
            'FWSEC execution was not observed')
    return dict(passed=True,ss0='0x88888888',entry_ss1='0x3',final_ss1='0x8',FLRs=1,
                dma_mappings_remaining=0,pci_attributes_restored=True)


def review(evidence,benchmark):
    ready=read(ROOT/'results/automatic-tf32-ready.json')
    manifest=read(ROOT/ready['package']/'MANIFEST.json')
    image=ROOT/ready['build']/'M6501-AUTOMATIC-TF32.EFI'
    require(sha(image)==ready['file_sha256']==manifest['candidate_sha256'],'Image hash mismatch')
    require(pe_hash(image.read_bytes())[0].hex()==ready['pe_authenticode_sha256'],'PE digest mismatch')
    installed=read(evidence/'installed-files.json')
    require({row['file']:row['sha256'] for row in installed}==manifest['files'],'Installed files differ')
    archive=read(evidence/'evidence-hashes.json')
    archive=[archive] if isinstance(archive,dict) else archive
    for row in archive:
        path=(evidence/'RTX-UNLOCK'/row['file']).resolve()
        require(path.is_relative_to(evidence.resolve()) and sha(path)==row['sha256'], 'Log archive hash mismatch')
    logs=sorted((evidence/'RTX-UNLOCK').glob('RUN[0-9][0-9][0-9][0-9]/UNLOCK.TXT'))
    require(bool(logs),'No physical boot log')
    log=logs[-1]
    transaction=validate_log(log.read_text(encoding='ascii'))
    post=evidence/'trust'
    before=ROOT/ready['preflight']/'trust'
    same={name:(post/(name+'.bin')).read_bytes()==(before/(name+'.bin')).read_bytes()
          for name in ('PK','KEK','db','dbx')}
    mok={row['data'].hex() for row in esl((post/'MokListRT.bin').read_bytes()) if row['type']==SHA256}
    previous={row['data'].hex() for row in esl((before/'MokListRT.bin').read_bytes()) if row['type']==SHA256}
    install=Path((ROOT/'results/latest-automatic-tf32-install.txt').read_text(encoding='utf-8-sig').strip())
    activation=read(install/'activation-state.json')
    trust=dict(secure_boot=(post/'SecureBoot.bin').read_bytes()==b'\x01',
        setup_mode_zero=(post/'SetupMode.bin').read_bytes()==b'\x00',
        shim_validation_enabled=not (post/'MokSBStateRT.bin').exists() or (post/'MokSBStateRT.bin').read_bytes()==b'\x00',
        platform_keys_and_revocations_unchanged=same,
        new_automatic_hash_in_MOK=ready['pe_authenticode_sha256'] in mok,
        previous_MOK_hashes_preserved=previous<=mok,
        old_automatic_entry_unchanged=(evidence/'Boot0000.bin').read_bytes()==base64.b64decode(ready['preflight_entries']['Boot0000']),
        windows_entry_unchanged=(evidence/'Boot0001.bin').read_bytes()==base64.b64decode(ready['preflight_entries']['Boot0001']),
        tf32_entry_matches_installed=(evidence/'Boot0006.bin').read_bytes()==base64.b64decode(activation['payload_base64']))
    require(all(value for value in trust.values() if isinstance(value,bool)) and all(same.values()),'Trust/entry verification failed')
    raw=(evidence/'BootOrder.bin').read_bytes()
    order=list(struct.unpack('<'+'H'*(len(raw)//2),raw))
    current=int.from_bytes((evidence/'BootCurrent.bin').read_bytes(),'little')
    require(current==6,'Current Windows boot was not through the TF32 entry')
    health=read(evidence/'health-before/boot-control.json')
    unexpected=[event for event in health['events'] if not known_network_warning(event)]
    require(not unexpected,'Unexpected boot driver/hardware events')
    data=read(benchmark)
    windows=read(evidence/'windows-return.json')
    require(datetime.fromisoformat(data['utc'])>=datetime.fromisoformat(windows['windows_boot_utc']),'Stale benchmark')
    stock=read(ROOT/'results/baseline-2026-10-25.json')
    recent=read(ROOT/'results/tf32-before-automatic-20261026-1926.json')
    stock_comparison=compare(stock,data)
    recent_comparison=compare(recent,data)
    require(all(row['output_bit_identical'] for row in stock_comparison),'Full output differs from stock')
    modes,normal=active_modes(data),active_modes(stock)
    for name,row in modes.items():
        require(row['active_samples']>=5,'Insufficient clock samples: '+name)
        row['normalized_vs_stock']=row['tflops_per_ghz']/normal[name]['tflops_per_ghz']
    require(set(modes)=={'fp16','bf16','tf32','fp32'},'Missing benchmark modes')
    tf32_gain=next(row['gain_percent'] for row in recent_comparison if row['mode']=='tf32')
    supported=(tf32_gain>10 and all(modes[name]['normalized_vs_stock']>1.5 for name in ('fp16','bf16','tf32'))
               and 0.9<modes['fp32']['normalized_vs_stock']<1.1)
    return dict(passed=supported,transaction=transaction,trust=trust,boot_current=current,
        boot_order_at_collection=order,tf32_first_at_collection=order[0]==6,
        windows_boot_utc=windows['windows_boot_utc'],log=str(log),log_sha256=sha(log),
        evidence_is_tpm_attestation=False,comparison_vs_stock=stock_comparison,
        comparison_vs_recent_ss0_only=recent_comparison,coarse_per_clock_modes=modes,
        all_full_outputs_bit_identical=True,tf32_acceleration_supported=supported,
        unexpected_driver_or_hardware_events=unexpected,
        known_corrected_network_events=sum(known_network_warning(event) for event in health['events']),
        limits=['One physical boot; separate sustained validation and later reboot/sleep persistence',
                'Clock normalization uses active phase samples, not exact CUDA event windows'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,required=True)
    args=p.parse_args()
    result=review(args.evidence.resolve(),args.benchmark.resolve())
    (args.evidence/'physical-tf32-review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
