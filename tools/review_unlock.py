"""Review a physical unlock log, post-boot trust and matched GEMM evidence.

Reads saved files only; never runs an EFI image or modifies devices/trust.
"""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import statistics

from audit_trust import SHA256, esl, pe_hash
from review_probe import bootmgr_block, sha

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def review_authorization(evidence, stage, image_sha, auth_sha, windows):
    if stage == 'B1':
        record=evidence/'unlock-candidate-v3-authorization.json'
        authorization=read(record)
        if authorization['attempt_limit'] != 1:
            raise ValueError('B1 requires the original one-attempt authorization')
        ordinal=1
        prerequisite=None
    else:
        record=evidence/'repro-v3-authorization.json'
        if record.read_bytes() != (ROOT/'results/repro-v3-authorization.json').read_bytes():
            raise ValueError('Archived reproducibility authorization changed')
        authorization=read(record)
        context=read(evidence/'attempt-context.json')
        ordinal={'B2':1,'B3':2}[stage]
        if (authorization['attempt_limit'] != 2 or authorization['additional_attempt_limit'] != 2 or
            authorization['order'] != ['B2','A3','B3','A4'] or context['stage'] != stage or
            context['ordinal_in_authorization'] != ordinal or context['authorized_attempt_limit'] != 2):
            raise ValueError('Attempt is outside the approved sequence or allowance')
        plan=(ROOT/authorization['plan']).resolve()
        if not plan.is_relative_to(ROOT) or sha(plan.read_bytes()) != authorization['plan_sha256']:
            raise ValueError('Approved plan changed')
        prerequisite_path=(ROOT/context['preceding_review']).resolve()
        if not prerequisite_path.is_relative_to((ROOT/'results').resolve()):
            raise ValueError('Prerequisite must be saved under results/')
        prerequisite=read(prerequisite_path)
        expected_control={'B2':'A2','B3':'A3'}[stage]
        if (not prerequisite['normal_return_passed'] or
            Path(prerequisite['benchmark']).name != f'normal-return-{expected_control}-2026-10-25.json' or
            datetime.fromisoformat(windows['windows_boot_utc']) <= datetime.fromisoformat(prerequisite['new_boot_utc']) or
            datetime.fromisoformat(windows['windows_boot_utc']) <= datetime.fromisoformat(authorization['utc_recorded'])):
            raise ValueError('A passed preceding normal control and later authorized boot are required')
    if authorization['file_sha256'] != image_sha or authorization['pe_authenticode_sha256'] != auth_sha:
        raise ValueError('Authorization differs from this candidate')
    return {'stage':stage,'record':str(record),'attempt_limit':authorization['attempt_limit'],
            'ordinal_in_authorization':ordinal,'remaining_after_this_attempt':authorization['attempt_limit']-ordinal,
            'preceding_control_review':str(prerequisite_path) if prerequisite is not None else None}


def telemetry(data):
    result={}
    fields=('temperature_c','power_w','sm_clock_mhz','memory_clock_mhz','utilization_percent')
    for mode in ('fp16','bf16','tf32','fp32'):
        rows=[]
        for item in data['telemetry']:
            if item['phase']!=mode or item['returncode']:
                continue
            try:
                values=[float(x.strip()) for x in item['stdout'].split(',')[1:6]]
            except ValueError:
                continue
            if len(values)==5 and values[4]>=90:
                rows.append(values)
        result[mode]={'active_samples':len(rows),
                      'median':dict(zip(fields,[statistics.median(row[i] for row in rows) for i in range(5)])) if rows else None,
                      'max_temp_c':max((row[0] for row in rows),default=None)}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--post',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,required=True)
    p.add_argument('--stage',choices=('B1','B2','B3'),default='B1')
    p.add_argument('--paired-reference',type=Path,
                   help='Immediately preceding normal control; required for B2/B3')
    args=p.parse_args()
    evidence=args.evidence.resolve()
    if not evidence.is_relative_to((ROOT/'results').resolve()):
        p.error('Evidence must stay under results/')
    for entry in read(evidence/'evidence-hashes.json'):
        data=(evidence/'RTX-UNLOCK'/entry['file']).read_bytes()
        if len(data)!=entry['bytes'] or sha(data)!=entry['sha256']:
            raise ValueError('Archived evidence changed')
    image=(ROOT/'build/candidate-20261025-v3/M6501-UNLOCK-CANDIDATE.EFI').read_bytes()
    image_sha,auth_sha=sha(image),pe_hash(image)[0].hex()
    observed=read(evidence/'usb-image-hashes.json')
    if not any(x['name'].lower()=='grubx64.efi' and x['sha256']==image_sha for x in observed):
        raise ValueError('USB image differs from candidate v3')
    windows=read(evidence/'windows-return.json')
    authorization=review_authorization(evidence,args.stage,image_sha,auth_sha,windows)
    if args.stage != 'B1' and args.paired_reference is None:
        p.error('B2/B3 require --paired-reference')
    if args.paired_reference is not None and authorization['preceding_control_review'] is not None:
        previous=read(Path(authorization['preceding_control_review']))
        if args.paired_reference.resolve() != Path(previous['benchmark']).resolve():
            raise ValueError('Paired reference is not the passed preceding normal control')
    attempts=[]
    for path in sorted((evidence/'RTX-UNLOCK').glob('RUN[0-9][0-9]/UNLOCK.TXT')):
        if 'TRANSACTION result=' in path.read_text(encoding='ascii'):
            attempts.append(path)
    if len(attempts)!=1:
        raise ValueError('Expected exactly one authorized transaction attempt')
    log_path=attempts[0]
    text=log_path.read_text(encoding='ascii')
    cold=re.search(r'COLD chip=0xb76000a1 fb_mib=6144 ss0=0x[0-9a-f]+ ss1=(0x[0-9a-f]+)',text)
    if cold is None:
        raise ValueError('Missing exact-board cold selectors')
    ss1=int(cold[1],16)
    required=(
        'SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero',
        'SMBIOS M6501RM_product=1 BIOS_313=1','TARGET exact_matches=1',
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
        'HANDOFF clean resources, original PCI attributes, existing Windows Boot Manager')
    if any(item not in text for item in required):
        raise ValueError('Required successful-transaction evidence missing')
    if ('STOP.' in text or 'failure unlock_610.c:' in text or 'selector write: SS1' in text or
        text.count('selector write: SS0=0x88888888')!=1 or text.count('PCIe FLR returned: result=0')!=1):
        raise ValueError('Failure, unexpected selector write or reset count')
    halt=re.search(r'FWSEC halt observation: first=(\w+) last=(\w+) samples=(\d+) observed_nonhalt=1 requested_wait_us=(\d+) error=0',text)
    wpr=re.search(r'FWSEC WPR2: low=(0x[0-9a-f]+) high=(0x[0-9a-f]+) expected_page=(0x[0-9a-f]+) end=(0x[0-9a-f]+)',text)
    if halt is None or wpr is None:
        raise ValueError('Missing FWSEC execution/range evidence')
    low,high,page,end=[int(x,16) for x in wpr.groups()]
    if low>>4!=page or not page<<12 <= (high>>4)<<12 < end:
        raise ValueError('FWSEC WPR2 range invalid')
    post=args.post.resolve()
    before=ROOT/'results/uefi-readonly-20261025-161851'
    same={name:(before/f'{name}.bin').read_bytes()==(post/f'{name}.bin').read_bytes() for name in ('PK','KEK','db','dbx')}
    hashes={x['data'].hex() for x in esl((post/'MokListRT.bin').read_bytes()) if x['type']==SHA256}
    previous={x['data'].hex() for x in esl((ROOT/'results/uefi-post-capture-20261025-203931/MokListRT.bin').read_bytes()) if x['type']==SHA256}
    state_file=post/'MokSBStateRT.bin'
    validation=not state_file.exists() or state_file.read_bytes()==b'\x00'
    boot=(post/'boot-entries.txt').read_text(encoding='utf-8-sig')
    old_boot=(before/'boot-entries.txt').read_text(encoding='utf-8-sig')
    trust={'secure_boot':(post/'SecureBoot.bin').read_bytes().hex(),
           'setup_mode':(post/'SetupMode.bin').read_bytes().hex(),'shim_validation_enabled':validation,
           'platform_trust_unchanged':same,'candidate_hash_present_in_MOK':auth_sha in hashes,
           'previous_MOK_hashes_preserved':previous<=hashes,
           'windows_boot_manager_entry_unchanged':bootmgr_block(boot)==bootmgr_block(old_boot),
           'windows_boot_manager_first':bool(re.search(r'displayorder\s+\{bootmgr\}',boot)),
           'collection':str(post)}
    trust['passed']=(trust['secure_boot']=='01' and trust['setup_mode']=='00' and validation and all(same.values()) and
                     trust['candidate_hash_present_in_MOK'] and trust['previous_MOK_hashes_preserved'] and
                     trust['windows_boot_manager_entry_unchanged'] and trust['windows_boot_manager_first'])
    baseline=read(ROOT/'results/baseline-2026-10-25.json')
    benchmark=read(args.benchmark)
    if datetime.fromisoformat(benchmark['utc'])<datetime.fromisoformat(windows['windows_boot_utc']):
        raise ValueError('Benchmark predates this Windows boot')
    spec=importlib.util.spec_from_file_location('compare_gemm',ROOT/'bench/compare.py')
    compare=importlib.util.module_from_spec(spec);spec.loader.exec_module(compare)
    comparison=compare.compare(baseline,benchmark)
    paired=read(args.paired_reference) if args.paired_reference else baseline
    paired_comparison=compare.compare(paired,benchmark)
    health=read(evidence/'post-benchmark-health/boot-control.json')
    collection=read(post/'report.json')
    if (datetime.fromisoformat(health['boot_utc']) != datetime.fromisoformat(windows['windows_boot_utc']) or
        datetime.fromisoformat(health['utc']) < datetime.fromisoformat(benchmark['utc']) or
        datetime.fromisoformat(collection['utc']) < datetime.fromisoformat(windows['windows_boot_utc'])):
        raise ValueError('Health/trust collection is not from this benchmark boot')
    display=[x for x in health['events'] if x['provider'] in ('Display','nvlddmkm')]
    other_hardware=[x for x in health['events'] if x['provider']=='Microsoft-Windows-WHEA-Logger']
    unexpected_hardware=[x for x in other_hardware if not (
        x['id']==17 and x['fields'].get('VendorID')=='0x1022' and x['fields'].get('DeviceID')=='0x14ba' and
        x['fields'].get('Bus')=='0x0' and x['fields'].get('Device')=='0x2' and x['fields'].get('Function')=='0x1' and
        x['fields'].get('UncorrectableErrorStatus')=='0x0')]
    measured_gain=all(x['gain_percent']>1 for x in comparison+paired_comparison if x['mode'] in ('fp16','bf16'))
    controls_stable=all(abs(x['gain_percent'])<5 for x in comparison+paired_comparison if x['mode'] in ('tf32','fp32'))
    identical=all(x['output_bit_identical'] for x in comparison+paired_comparison)
    correct=all(x['correctness_passed'] and x['finite_entire_output'] for x in benchmark['results'])
    passed=trust['passed'] and not display and not unexpected_hardware and measured_gain and controls_stable and identical and correct
    result={'scope':f'Authorized physical unlock {args.stage} and matched GEMM in the same Windows boot; not long-term validation',
            'stage':args.stage,'attempt_validation_passed':passed,
            'transaction_passed':True,'gpu_unlock_applied':True,
            'authorization':authorization,'authorized_attempts_observed':authorization['ordinal_in_authorization'],
            'remaining_authorized_attempts':authorization['remaining_after_this_attempt'],
            'candidate_file_sha256':image_sha,'candidate_pe_authenticode_sha256':auth_sha,
            'log':str(log_path),'log_sha256':sha(log_path.read_bytes()),
            'selectors':{'ss0':'0x88888888','ss1':hex(ss1),'ss1_preserved':True},
            'flr_count':1,'dma_maps_remaining':0,'retained':False,'quiesced':True,'fault':False,
            'pci_memory_restored':True,'firmware_scratch':0,'firmware_execution_observed_nonhalt_then_halt':True,
            'windows_boot_utc':windows['windows_boot_utc'],'uefi_trust':trust,
            'benchmark':str(args.benchmark.resolve()),'comparison':comparison,
            'paired_reference':str(args.paired_reference.resolve()) if args.paired_reference else str(ROOT/'results/baseline-2026-10-25.json'),
            'paired_comparison':paired_comparison,'control_modes_stable':controls_stable,
            'control_mode_tolerance_percent':5,'all_outputs_bit_identical':identical,
            'all_numeric_checks_passed':correct,
            'display_or_nvlddmkm_events':len(display),'unexpected_WHEA_events':len(unexpected_hardware),
            'known_corrected_Realtek_port_events':len(other_hardware)-len(unexpected_hardware),
            'hardware_events':health['events'],'post_benchmark_health_utc':health['utc'],
            'this_experimental_boot_validated':passed,'normal_boot_return_after_this_unlock_validated':False,
            'idle_sleep_resume_persistence_validated':False,
            'limits':['This report validates this experimental boot; prior boots and subsequent normal controls have separate evidence',
                      'GEMM validation does not establish correctness of every application or long-term stability',
                      'This report grants no authorization; a remaining approved B3 requires a passed B2 and A3',
                      'USB logs/image snapshots are evidence, not TPM-backed execution attestation']}
    if args.stage == 'B1':
        result.update(first_boot_validation_passed=passed,independent_experimental_boots_validated=1,
                      normal_boot_return_after_unlock_validated=False)
    (evidence/'unlock-review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (evidence/'telemetry-comparison.json').write_text(json.dumps({
        'filter':'GPU utilization >=90 percent; coarse active samples include warmup, not exact GEMM intervals',
        'baseline':telemetry(baseline),'paired_reference':telemetry(paired),'experimental':telemetry(benchmark)},indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('stage','attempt_validation_passed','transaction_passed','selectors',
                     'uefi_trust','comparison','all_outputs_bit_identical','display_or_nvlddmkm_events','unexpected_WHEA_events')},indent=2))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
