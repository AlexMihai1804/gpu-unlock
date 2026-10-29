"""Review saved long-test evidence. Never starts workloads or changes configuration."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from compare import compare
from endurance import known_network_warning
from performance_state import classify
from limiter_analysis import analyze as analyze_limiters


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def stopped_report(out):
    summary=read(out/'endurance/summary.json')
    if summary['completed'] or summary['status']!='stopped':
        raise ValueError('Stopped report requires a stopped, incomplete run')
    launch=read(out/'launch.json')
    initial=read(out/'health-before/boot-control.json')
    health=read(out/'health-after/boot-control.json')
    baseline=read(Path(__file__).resolve().parents[1]/'results/baseline-2026-10-25.json')
    expected={row['mode']:row['output_sha256'] for row in baseline['results']}
    rows=[json.loads(line) for line in (out/'endurance/blocks.jsonl').read_text().splitlines() if line.strip()]
    assert len(rows)==summary['validated_blocks'], 'Block count changed'
    correct=bool(rows) and all(row['correctness_passed'] and row['finite_entire_output'] and
        row['sample_relative_l2']<0.0001 and row['output_sha256']==expected[row['mode']] for row in rows)
    unexpected=[event for event in health['events'] if not known_network_warning(event)]
    during=[event for event in unexpected if datetime.fromisoformat(event['utc'])>=datetime.fromisoformat(summary['utc'])]
    earlier=[event for event in unexpected if datetime.fromisoformat(event['utc'])<datetime.fromisoformat(summary['utc'])]
    gpu_port_earlier=[event for event in earlier if event.get('id')==17 and
        event.get('fields',{}).get('VendorID')=='0x1022' and event['fields'].get('DeviceID')=='0x14b8' and
        event['fields'].get('Bus')=='0x0' and event['fields'].get('Device')=='0x1' and
        event['fields'].get('Function')=='0x1' and event['fields'].get('UncorrectableErrorStatus')=='0x0']
    benchmark=read(out/'before.json')
    rates={row['mode']:row['tflops'] for row in benchmark['results']}
    ratios={mode:rates[mode]/rates['tf32'] for mode in ('fp16','bf16')}
    performance_state=classify(benchmark)
    result=dict(passed=False,status='stopped',completed_requested_duration=False,
        scope='Current Windows session without restart; interrupted workload',
        reason=summary.get('error'),wall_seconds=summary['load_wall_seconds'],
        requested_seconds=summary['configuration']['seconds'],cuda_seconds=summary['cuda_seconds'],
        cuda_load_fraction=summary['cuda_load_fraction'],load_policy=summary.get('load_policy','continuous'),
        cooling_pauses=summary.get('cooling_pauses',0),cooling_seconds=summary.get('cooling_seconds',0),
        maximum_temperature_c=summary['maximum_temperature_c'],validated_blocks=len(rows),
        gemm_count=sum(row['iterations'] for row in rows),all_recorded_numeric_checks_passed=correct,
        results=summary['results'],unexpected_driver_or_hardware_events=unexpected,
        unexpected_driver_or_hardware_events_during_test=during,
        preexisting_unexpected_driver_or_hardware_events=earlier,
        preexisting_corrected_GPU_root_port_events=gpu_port_earlier,
        display_or_nvlddmkm_errors=sum(event['provider'] in ('Display','nvlddmkm') for event in health['events']),
        known_corrected_network_events=sum(known_network_warning(event) for event in health['events']),
        same_boot=datetime.fromisoformat(health['boot_utc'])==datetime.fromisoformat(initial['boot_utc'])==datetime.fromisoformat(launch['boot_utc']),
        secure_boot_registry_before_after=[initial['secure_boot_registry_value'],health['secure_boot_registry_value']],
        tensor_to_tf32_ratios_before=ratios,performance_matches_unlocked_pattern_before=performance_state['unlocked_performance_supported'],
        performance_state_before=performance_state,
        post_short_benchmark_performed=False,fresh_firmware_trust_collection=False,
        no_persistent_configuration_changes=True,
        limitations=summary['limits']+['Requested duration not completed; no PASS for the full requested test'])
    result['evidence_sha256']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in
        ('launch.json','before.json','endurance/summary.json','endurance/blocks.jsonl','endurance/telemetry.jsonl',
         'endurance/health.jsonl','health-before/boot-control.json','health-after/boot-control.json')}
    (out/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    minutes,seconds=divmod(round(result['wall_seconds']),60)
    lines=['# Test FP16/BF16 fără restart: oprit','',
        f"Durată efectivă: **{minutes} min {seconds} s**, cu pauze termice; timp CUDA măsurat **{result['cuda_seconds']/60:.2f} minute** ({100*result['cuda_load_fraction']:.1f}% din durată).",
        f"Motivul opririi: **{result['reason']}**. Temperatura maximă: {result['maximum_temperature_c']}°C. **Durata planificată nu a fost completată; nu se acordă PASS pentru durata completă.**",'',
        '| Mod | TFLOPS mediană în blocurile active | P5–P95 | Ultimul vs primul sfert |',
        '|---|---:|---:|---:|']
    for mode,row in result['results'].items():
        lines.append(f"| {mode.upper()} | {row['median_tflops']:.3f} | {row['p5_tflops']:.3f}–{row['p95_tflops']:.3f} | {row['last_vs_first_quarter_percent']:+.2f}% |")
    lines+=['',f"Au fost efectuate {result['gemm_count']} GEMM, în {result['validated_blocks']} blocuri. Toate verificările numerice: **{'PASS' if correct else 'FAIL'}**. Hashurile acoperă ultima ieșire completă din fiecare bloc; cele 2.048 de elemente CPU FP64/bloc au trecut verificarea.",
        f"Erori Display/nvlddmkm în această pornire: **{result['display_or_nvlddmkm_errors']}**. Evenimente hardware neașteptate noi în timpul testului: **{len(during)}**. Evenimente anterioare testului: **{len(earlier)}**. Avertismentele corectate cunoscute ale portului de rețea în această pornire: {result['known_corrected_network_events']}.",
        f"Pauze de răcire: {result['cooling_pauses']}; timp în pauze: {result['cooling_seconds']/60:.2f} minute.",
        '', f"Avertismente WHEA 17 corectate, anterioare testului, pe root port-ul AMD 1022:14b8, 00:01.1, din amonte de GPU: **{len(gpu_port_earlier)}**. Nu sunt asimilate avertismentului cunoscut de rețea. Cauza lor nu este stabilită; detaliile și momentele sunt în review.json.",
        '', 'Clasificare benchmark inițial, ținând cont de frecvența SM: '+performance_state['classification']+'. Este o inferență din măsurători, nu o citire directă a selectorilor. Nu se presupune că această rulare este după standby; contextul exact este în launch.json și test-context.json, dacă există.',
        'Secure Boot din Windows: 1 înainte și după. Nu s-au modificat driverul, limita de putere, frecvențele, firmware-ul, cheile sau ordinea de boot. Exportul firmware/MOK anterior rămâne o verificare la momentul său.',
        '', 'Benchmarkul scurt final a fost omis după oprirea termică. Datele brute și hashurile dovezilor sunt în review.json și endurance/.', '']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--current-state', action='store_true',
                        help='Review stability of the existing session; no fresh boot or unlocked-pattern requirement')
    parser.add_argument('--stopped', action='store_true', help='Report a stopped run without fabricating a post-test benchmark')
    args=parser.parse_args()
    out=args.directory.resolve()
    if args.stopped:
        return stopped_report(out)
    before, after=read(out/'before.json'), read(out/'after.json')
    summary=read(out/'endurance/summary.json')
    boot, pre, post=(None, None, None) if args.current_state else [read(out/name) for name in ('review-boot.json','review-before.json','review-after.json')]
    health=read(out/'health-after/boot-control.json')
    comparison=compare(before, after)
    unexpected=[event for event in health['events'] if not known_network_warning(event)]
    checks=dict(
        completed=summary['completed'] and summary['status']=='passed',
        requested_duration_met=summary['load_wall_seconds'] >= summary['configuration']['seconds'],
        minimum_requested_load=summary['cuda_load_fraction'] >= summary.get('minimum_cuda_load_fraction',0.70),
        numeric_checks=all(row['all_numeric_checks_passed'] for row in summary['results'].values()),
        both_modes=set(summary['results'])=={'fp16','bf16'},
        full_outputs_identical_before_after=all(row['output_bit_identical'] for row in comparison),
        no_unexpected_driver_hardware_events=not unexpected,
        temperature_below_stop=summary['configuration']['temperature_limit'] is None or summary['maximum_temperature_c'] < summary['configuration']['temperature_limit'])
    def ratios(data):
        modes={row['mode']:row['tflops'] for row in data['results']}
        return {mode:modes[mode]/modes['tf32'] for mode in ('fp16','bf16')}
    tensor_ratios={'before':ratios(before),'after':ratios(after)}
    performance_states={'before':classify(before),'after':classify(after)}
    unlocked_pattern=all(value['unlocked_performance_supported'] for value in performance_states.values())
    if args.current_state:
        launch=read(out/'launch.json')
        initial=read(out/'health-before/boot-control.json')
        checks.update(
            same_boot=datetime.fromisoformat(health['boot_utc'])==datetime.fromisoformat(initial['boot_utc'])==datetime.fromisoformat(launch['boot_utc']),
            secure_boot_registry_before_after=initial['secure_boot_registry_value']==health['secure_boot_registry_value']==1)
    else:
        checks.update(trust=all(review['trust']['passed'] for review in (boot,pre,post)),
            unlocked_performance_before_after=all(review['performance_matches_unlocked_pattern'] for review in (pre,post)),
            same_boot=health['boot_utc']==pre['windows_return']['windows_boot_utc']==post['windows_return']['windows_boot_utc'])
    result=dict(passed=all(checks.values()),checks=checks,results=summary['results'],
        wall_seconds=summary['load_wall_seconds'],cuda_seconds=summary['cuda_seconds'],
        maximum_temperature_c=summary['maximum_temperature_c'],validated_blocks=summary['validated_blocks'],
        matched_before_after=comparison,unexpected_events=unexpected,
        known_corrected_network_events=sum(known_network_warning(event) for event in health['events']),
        limitations=summary['limits'],
        scope='Current Windows session stability without restart' if args.current_state else 'Fresh automatic unlocked session stability',
        tensor_to_tf32_ratios=tensor_ratios,performance_matches_unlocked_pattern_before_after=unlocked_pattern,
        performance_states=performance_states,
        fresh_firmware_trust_collection=not args.current_state)
    result.update(load_policy=summary.get('load_policy','continuous'),
        application_temperature_stop_enabled=summary['configuration']['temperature_limit'] is not None,
        sustained_70_percent_load_met=summary['cuda_load_fraction']>=0.70,
        cuda_load_fraction=summary['cuda_load_fraction'],
        cooling_pauses=summary.get('cooling_pauses',0),cooling_seconds=summary.get('cooling_seconds',0))
    result['limiting_factors']=analyze_limiters(out)
    context=read(out/'test-context.json') if (out/'test-context.json').exists() else {}
    if context.get('fresh_boot_evidence'):
        evidence=Path(context['fresh_boot_evidence']).resolve()
        root=Path(__file__).resolve().parents[1]
        if not evidence.is_relative_to(root/'results'):
            raise ValueError('Firmware evidence must stay inside project results')
        reviewed=read(evidence/'automatic-review.json')
        checks['fresh_boot_trust']=reviewed['trust']['passed']
        checks['firmware_evidence_same_boot']=datetime.fromisoformat(reviewed['windows_return']['windows_boot_utc'])==datetime.fromisoformat(health['boot_utc'])
        checks['unlocked_performance_before_after']=unlocked_pattern
        result.update(scope='Performance profile after user restart; continuous workload',
            fresh_firmware_trust_collection=True,firmware_evidence=str(evidence),user_selected_performance=True)
        result['passed']=all(checks.values())
    (out/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['# Test lung FP16/BF16', '', 'Rezultat: **'+('PASS' if result['passed'] else 'FAIL')+'**.', '',
        'Scop: '+result['scope']+'.',
        'Profil de performanță deblocat înainte și după: '+('DA' if unlocked_pattern else 'NECONFIRMAT')+'.',
        f"Regim: {result['load_policy']}; timp CUDA: {100*result['cuda_load_fraction']:.1f}% din durată; pauze termice: {result['cooling_pauses']}.",
        f"Durată: {result['wall_seconds']/60:.2f} minute; timp CUDA măsurat: {result['cuda_seconds']/60:.2f} minute.",
        f"Temperatura maximă: {result['maximum_temperature_c']:.0f}°C. Blocuri cu verificarea întregii ieșiri: {result['validated_blocks']}.", '',
        '| Mod | TFLOPS mediană | TFLOPS P5–P95 | Ultimul vs primul sfert |', '|---|---:|---:|---:|']
    for mode,row in result['results'].items():
        lines.append(f"| {mode.upper()} | {row['median_tflops']:.3f} | {row['p5_tflops']:.3f}–{row['p95_tflops']:.3f} | {row['last_vs_first_quarter_percent']:+.2f}% |")
    limits=result['limiting_factors'];proportions=limits['limiter_sample_percent']
    lines+=['', 'Limitări raportate de NVIDIA, în eșantioanele cu utilizare GPU ≥90%:', '',
        f"- Putere: {proportions['sw_power_cap']:.2f}% din eșantioane.",
        f"- Limitare termică software: {proportions['sw_thermal_slowdown']:.2f}%; hardware: {proportions['hw_thermal_slowdown']:.2f}%.",
        f"- Power brake hardware: {proportions['hw_power_brake']:.2f}%.",
        'Procentele descriu eșantioane de telemetrie, nu o împărțire exactă a timpului CUDA.']
    if limits['observed_current_power_limit_w']:
        cap=limits['observed_current_power_limit_w']
        lines.append(f"Limita de putere curentă observată în snapshoturi: {cap['min']:.2f}–{cap['max']:.2f} W; mediană {cap['median']:.2f} W.")
    lines+=['', 'Datele brute și verificările sunt în review.json, before.json, after.json și endurance/.', '',
            'Rezultatul acoperă GEMM dens cu intrări fixe și această pornire; nu certifică toate aplicațiile sau persistența după sleep/resume.', '']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
