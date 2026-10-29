"""Review saved normal-return evidence after a specified experimental boot.

Reads local files only. Never boots, applies an unlock or changes trust.
"""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import re

from review_probe import bootmgr_block, sha

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def expected_usb_logs(previous):
    entries=read(previous/'evidence-hashes.json')
    for row in entries:
        data=(previous/'RTX-UNLOCK'/row['file']).read_bytes()
        if len(data)!=row['bytes'] or sha(data)!=row['sha256']:
            raise ValueError('Previous archived evidence changed')
    expected={row['file'].replace('\\','/'):row['sha256'] for row in entries if row['file'].endswith('/UNLOCK.TXT')}
    inventory=previous/'usb-log-inventory.json'
    if inventory.is_file():
        rows=read(inventory)
        history={row['file'].replace('\\','/'):row['sha256'] for row in rows}
        if len(history)!=len(rows) or not history or any(history.get(k)!=v for k,v in expected.items()):
            raise ValueError('Historical inventory omits or changes the archived transaction')
        expected=history
    if not expected:
        raise ValueError('No prior USB logs')
    return expected


def validate_unchanged_logs(expected, observed):
    actual={}
    for row in observed:
        key=row.get('file')
        if key is None:
            key=PureWindowsPath(row['path']).relative_to(PureWindowsPath('F:/RTX-UNLOCK')).as_posix()
        key=key.replace('\\','/')
        if key in actual:
            raise ValueError('Duplicate observed USB log')
        actual[key]=row['sha256']
    if actual!=expected:
        raise ValueError('USB logs changed or an additional run appeared')
    return actual


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--post',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,required=True)
    p.add_argument('--stage',choices=('A2','A3','A4'),default='A2')
    p.add_argument('--previous-unlock',type=Path,default=ROOT/'results/physical-unlock-20261025-212306')
    args=p.parse_args()
    evidence=args.evidence.resolve()
    if not evidence.is_relative_to((ROOT/'results').resolve()):
        p.error('Use a saved directory under results/')
    confirmation=read(evidence/'user-boot-confirmation.json')
    health=read(evidence/'post-benchmark-health/boot-control.json')
    previous=args.previous_unlock.resolve()
    if not previous.is_relative_to((ROOT/'results').resolve()):
        p.error('Previous unlock evidence must stay under results/')
    old_review=read(previous/'unlock-review.json')
    expected_previous={'A2':'B1','A3':'B2','A4':'B3'}[args.stage]
    if (not confirmation['direct_boot_without_usb_confirmed'] or
        not old_review.get('attempt_validation_passed',old_review.get('first_boot_validation_passed',False)) or
        old_review.get('stage','B1')!=expected_previous):
        raise ValueError('Direct boot confirmation or the immediately preceding unlock review missing')
    if (datetime.fromisoformat(health['boot_utc'])<=datetime.fromisoformat(old_review['windows_boot_utc']) or
        health['boot_utc']!=confirmation['windows_boot_utc']):
        raise ValueError('Expected a new Windows boot')
    observed=read(evidence/'usb-log-inventory.json')
    actual=validate_unchanged_logs(expected_usb_logs(previous),observed)
    expected={row['file']:row['sha256'] for row in read(previous/'evidence-hashes.json')}
    usb=read(evidence/'usb-image-and-rom.json')
    if (usb['grubx64_sha256']!=old_review['candidate_file_sha256'] or
        usb['rom_sha256']!=expected['PROM00.ROM']):
        raise ValueError('USB image or original ROM changed')
    post=args.post.resolve()
    initial=ROOT/'results/uefi-readonly-20261025-161851'
    same={name:(initial/f'{name}.bin').read_bytes()==(post/f'{name}.bin').read_bytes() for name in ('PK','KEK','db','dbx')}
    boot=(post/'boot-entries.txt').read_text(encoding='utf-8-sig')
    old_boot=(initial/'boot-entries.txt').read_text(encoding='utf-8-sig')
    trust={'secure_boot':(post/'SecureBoot.bin').read_bytes().hex(),'setup_mode':(post/'SetupMode.bin').read_bytes().hex(),
           'platform_trust_unchanged':same,'windows_boot_manager_entry_unchanged':bootmgr_block(boot)==bootmgr_block(old_boot),
           'windows_boot_manager_first':bool(re.search(r'displayorder\s+\{bootmgr\}',boot)),
           'shim_runtime_MOK_list_exposed':(post/'MokListRT.bin').is_file(),
           'collection':str(post)}
    trust['passed']=(trust['secure_boot']=='01' and trust['setup_mode']=='00' and all(same.values()) and
                     trust['windows_boot_manager_entry_unchanged'] and trust['windows_boot_manager_first'])
    spec=importlib.util.spec_from_file_location('gemm_compare',ROOT/'bench/compare.py')
    compare=importlib.util.module_from_spec(spec);spec.loader.exec_module(compare)
    baseline=read(ROOT/'results/baseline-2026-10-25.json')
    experimental=read(Path(old_review['benchmark']))
    normal=read(args.benchmark)
    if datetime.fromisoformat(normal['utc'])<datetime.fromisoformat(health['boot_utc']):
        raise ValueError('Benchmark predates normal-return boot')
    control=compare.compare(baseline,normal)
    effect=compare.compare(normal,experimental)
    max_change=max(abs(x['gain_percent']) for x in control)
    finite_correct=all(x['correctness_passed'] and x['finite_entire_output'] for x in normal['results'])
    identical=all(x['output_bit_identical'] for x in control)
    identical=identical and all(x['output_bit_identical'] for x in effect)
    collection=read(post/'report.json')
    if (datetime.fromisoformat(collection['utc'])<datetime.fromisoformat(health['boot_utc']) or
        datetime.fromisoformat(health['utc'])<datetime.fromisoformat(normal['utc'])):
        raise ValueError('Trust/health collection predates this normal boot or benchmark')
    display=[x for x in health['events'] if x['provider'] in ('Display','nvlddmkm')]
    whea=[x for x in health['events'] if x['provider']=='Microsoft-Windows-WHEA-Logger']
    unexpected=[x for x in whea if not (x['id']==17 and x['fields'].get('VendorID')=='0x1022' and
        x['fields'].get('DeviceID')=='0x14ba' and x['fields'].get('Bus')=='0x0' and
        x['fields'].get('Device')=='0x2' and x['fields'].get('Function')=='0x1' and
        x['fields'].get('UncorrectableErrorStatus')=='0x0')]
    rows=[]
    for a,b,c in zip(baseline['results'],experimental['results'],normal['results']):
        if a['mode']!=b['mode'] or b['mode']!=c['mode']:
            raise ValueError('Mode order differs')
        rows.append({'mode':a['mode'],'normal_A1_tflops':a['tflops'],f'unlocked_{expected_previous}_tflops':b['tflops'],f'normal_{args.stage}_tflops':c['tflops']})
    report={'scope':f'User-confirmed direct normal boot {args.stage} after full shutdown; A1/{expected_previous}/{args.stage} GEMM comparison',
            'stage':args.stage,'previous_experimental_stage':expected_previous,'previous_unlock_evidence':str(previous),
            'normal_return_passed':trust['passed'] and finite_correct and identical and max_change<5 and not display and not unexpected,
            'new_boot_utc':health['boot_utc'],'previous_unlock_boot_utc':old_review['windows_boot_utc'],
            'usb_direct_boot_confirmed_by_user':True,'usb_logs_unchanged':True,'usb_run_count':len(actual),
            'new_unlock_attempts_observed':0,'performance_return_observed':max_change<5,
            'classification_tolerance_percent':5,'maximum_absolute_change_percent':max_change,
            f'normal_A1_vs_{args.stage}':control,f'normal_{args.stage}_vs_experimental_{expected_previous}':effect,'a_b_a_tflops':rows,
            'all_numeric_checks_passed':finite_correct,'all_outputs_bit_identical':identical,
            'uefi_trust':trust,'display_or_nvlddmkm_events':len(display),'unexpected_WHEA_events':len(unexpected),
            'known_corrected_Realtek_port_events':len(whea)-len(unexpected),'hardware_events':health['events'],
            'benchmark':str(args.benchmark.resolve()),
            'normal_boot_return_after_unlock_validated':True,'idle_sleep_resume_persistence_validated':False,
            'current_boot_unlock_executed_by_project':False,
            'limits':['Returned GEMM throughput is measured; GPU selector registers were not directly read in Windows',
                      'Normal boot does not expose shim runtime variables here; their absence does not prove persistent MOK entries were deleted',
                      'Firmware removable-device boot inventory may change automatically; Windows Boot Manager is compared separately',
                      'This normal-return report does not establish sleep/resume behavior or long-term stability']}
    if args.stage=='A2':
        report['independent_experimental_boots_validated']=1
    (evidence/'normal-return-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('normal_return_passed','maximum_absolute_change_percent','a_b_a_tflops',
                     'uefi_trust','display_or_nvlddmkm_events','unexpected_WHEA_events')},indent=2))
    return 0 if report['normal_return_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
