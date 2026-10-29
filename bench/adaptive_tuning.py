"""Bounded GPU-offset efficiency experiments; always restore original zero.

Raise the next offset only after a positive comparison against both neighboring
zero-offset controls. No persistent tuning, voltage, power, memory or boot writes.
"""
import argparse
import ctypes as ct
import hashlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import traceback

from efficiency import measured_block, aggregate, set_trial_offset, restore_original, restored, watchdog
from endurance import ROOT, Case, ac_power, check_health, read_health, save, utc
from gemm import Blas, smi
from nvidia_metrics import Nvml, Nvapi
from performance_state import classify


def screen_plan(offsets):
    offsets=tuple(offsets)
    if offsets not in ((60,90,120),(120,150)):
        raise ValueError('Use the original 60/90/120 plan or the separately authorized 120/150 comparison')
    return offsets


def totals(rows):
    work = sum(r['work_tflop'] for r in rows)
    energy = sum(r['energy_j'] for r in rows)
    cuda = sum(r['cuda_ms'] for r in rows) / 1000
    wall = sum(r['meter_wall_seconds'] for r in rows)
    if not rows or min(work, energy, cuda, wall) <= 0:
        raise ValueError('Missing or invalid measurement windows')
    return dict(tflops=work / cuda, efficiency=work / energy, power_w=energy / wall,
                max_temperature_c=max(r['max_temperature_c'] for r in rows), blocks=len(rows), cuda_seconds=cuda)


def assess(rows, phase, neighbors, previous=None):
    modes = {}
    for mode in ('fp16', 'bf16'):
        current_rows = [r for r in rows if r['phase'] == phase and r['mode'] == mode]
        controls = [[r for r in rows if r['phase'] == name and r['mode'] == mode] for name in neighbors]
        current, before, after = [totals(rs) for rs in (current_rows, *controls)]
        combined = totals(controls[0] + controls[1])
        gains = [(current['efficiency'] / c['efficiency'] - 1) * 100 for c in (before, after)]
        speed_gains = [(current['tflops'] / c['tflops'] - 1) * 100 for c in (before, after)]
        power_ok = all(abs(current['power_w'] / c['power_w'] - 1) <= .03 for c in (before, after))
        temperature_ok = all(abs(current['max_temperature_c'] - c['max_temperature_c']) <= 3 for c in (before, after))
        enough = min(current['blocks'], before['blocks'], after['blocks']) >= 3
        correct = all(r['correctness_passed'] for rs in (current_rows, *controls) for r in rs)
        normalized = current['efficiency'] / combined['efficiency']
        marginal = (normalized / previous['modes'][mode]['normalized_efficiency'] - 1) * 100 if previous else None
        worth = enough and correct and power_ok and temperature_ok and min(gains) > 1 and min(speed_gains) > .5
        modes[mode] = dict(current=current, controls=[before, after], combined_control=combined,
            efficiency_gain_each_percent=gains, throughput_gain_each_percent=speed_gains,
            normalized_efficiency=normalized, efficiency_gain_percent=(normalized - 1) * 100,
            marginal_efficiency_percent=marginal, comparable_power=power_ok,
            comparable_temperature=temperature_ok, enough_blocks=enough, all_correct=correct,
            worth_testing_further=worth)
    worthwhile = all(m['worth_testing_further'] for m in modes.values())
    improvement = worthwhile and (previous is None or all(m['marginal_efficiency_percent'] > .5 for m in modes.values()))
    return dict(phase=phase, neighbors=list(neighbors), modes=modes, worth=worthwhile,
                better_than_previous=improvement, allow_next_step=improvement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', required=True, type=Path)
    parser.add_argument('--watchdog-parent', type=int)
    parser.add_argument('--screen-offsets',type=int,nargs='+',default=[60,90,120])
    args = parser.parse_args()
    try:
        offsets=screen_plan(args.screen_offsets)
    except ValueError as error:
        parser.error(str(error))
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT / 'results') or not out.is_dir():
        parser.error('Use a new project results directory containing before.json')
    if args.watchdog_parent is not None:
        watchdog(out, args.watchdog_parent, 3600)
        return 0
    if (out / 'adaptive-summary.json').exists():
        parser.error('Existing experiment; choose a fresh directory')
    if not ct.windll.shell32.IsUserAnAdmin():
        parser.error('Temporary clock tuning requires UAC elevation')
    state = dict(utc=utc(), status='initializing', completed=False, maximum_offset_mhz=max(offsets),
        policy={'warmup_cuda_seconds':180, 'reference_cuda_seconds':90, 'screen_60_cuda_seconds':180,
                'higher_screen_cuda_seconds':120, 'validation_cuda_seconds':600,
                'final_reference_cuda_seconds':120, 'minimum_gain_each_control_percent':1,
                'minimum_marginal_gain_each_mode_percent':.5,'screen_offsets_mhz':list(offsets)},
        persistent_tuning_applied=False, no_voltage_power_memory_boot_writes=True,
        phases=[], decisions=[], selected_offset_mhz=0,
        measurement_scope='Dense 8192 GEMM, fixed inputs, GPU energy counter; not all applications or wall-socket energy')
    save(out / 'adaptive-summary.json', state)
    meter = api = blas = watcher = None
    original = None
    cases, rows, telemetry, failures = [], [], [], []
    stop = threading.Event()
    phase = ['initialization']
    current_offset = [0]
    armed = False
    health_since = state['utc']
    last_health = [0.]

    def health():
        result = read_health(health_since)
        save(out / 'health-after.json', result)
        check_health(result['events'])
        last_health[0] = time.monotonic()

    def guard():
        (out / 'heartbeat').touch()
        if failures:
            raise RuntimeError('; '.join(failures))
        if watcher is not None and watcher.poll() is not None:
            raise RuntimeError('Restoration watchdog exited')
        if (out / 'STOP').exists():
            raise RuntimeError('Stopped by STOP marker')
        if ac_power() != 1:
            raise RuntimeError('AC disconnected')
        if time.monotonic() - last_health[0] > 25:
            health()

    def monitor():
        try:
            with (out / 'energy-telemetry.jsonl').open('x', encoding='utf-8') as log:
                while not stop.is_set():
                    sample = meter.sample()
                    sample.update(utc=utc(), monotonic=time.perf_counter(), phase=phase[0],
                                  offset_mhz=current_offset[0], voltage_mv=api.voltage())
                    telemetry.append(sample)
                    log.write(json.dumps(sample) + '\n'); log.flush()
                    if ac_power() != 1:
                        raise RuntimeError('AC disconnected')
                    stop.wait(.2)
        except Exception as error:
            failures.append(str(error))

    def run_phase(label, offset, cuda_seconds, log):
        nonlocal armed
        guard()
        armed = True
        set_trial_offset(meter, offset)
        current_offset[0] = offset
        with (out / 'offset-events.jsonl').open('a', encoding='utf-8') as event_log:
            event_log.write(json.dumps(dict(utc=utc(), phase=label, requested_mhz=offset,
                p0=meter.offset(0), p2=meter.offset(2), memory=meter.offset(0, 2))) + '\n')
        phase[0] = label + '-settling'
        for case in cases:
            if not case.run(100)['correctness_passed']:
                raise RuntimeError('Settling output incorrect')
            guard()
        phase[0] = label
        start = time.perf_counter()
        elapsed = 0.
        phase_rows = []
        print(f'PHASE {label}: offset {offset}, target CUDA {cuda_seconds}s', flush=True)
        while elapsed < cuda_seconds:
            for case in cases:
                guard()
                row = measured_block(case, meter, 400)
                samples = [t for t in telemetry if row['start_monotonic'] <= t['monotonic'] <= row['end_monotonic']]
                active = [t for t in samples if t['utilization_percent'] >= 90]
                if len(active) < 5:
                    raise RuntimeError('Too few active telemetry samples')
                voltages = [t['voltage_mv'] for t in active if t['voltage_mv'] is not None]
                row.update(utc=utc(), phase=label, offset_mhz=offset, active_samples=len(active),
                    median_sm_clock_mhz=statistics.median(t['sm_clock_mhz'] for t in active),
                    median_voltage_mv=statistics.median(voltages) if voltages else None,
                    max_temperature_c=max(t['temperature_c'] for t in samples),
                    median_reported_power_w=statistics.median(t['power_w'] for t in active),
                    median_enforced_limit_w=statistics.median(t['enforced_limit_w'] for t in active))
                row['counter_vs_sample_power_percent'] = (row['average_power_w'] / row['median_reported_power_w'] - 1) * 100
                rows.append(row); phase_rows.append(row)
                log.write(json.dumps(row) + '\n'); log.flush()
                if not row['correctness_passed'] or abs(row['counter_vs_sample_power_percent']) > 10:
                    raise RuntimeError('Numerical or energy sanity check failed')
                elapsed += row['cuda_ms'] / 1000
                save(out / 'progress.json', dict(utc=utc(), phase=label, offset_mhz=offset,
                    phase_cuda_seconds=elapsed, target_cuda_seconds=cuda_seconds, total_blocks=len(rows),
                    last_tflops=row['cuda_tflops'], last_efficiency=row['tflop_per_joule'],
                    latest_telemetry=telemetry[-1] if telemetry else None))
                guard()
                if elapsed >= cuda_seconds:
                    break
        health()
        entry = dict(label=label, offset_mhz=offset, target_cuda_seconds=cuda_seconds,
            measured_cuda_seconds=elapsed, wall_seconds=time.perf_counter() - start,
            blocks=len(phase_rows), modes={mode:totals([r for r in phase_rows if r['mode']==mode])
                for mode in ('fp16','bf16')})
        state['phases'].append(entry)
        save(out / 'adaptive-summary.json', state)
        print(json.dumps(entry), flush=True)

    try:
        meter, api = Nvml(), Nvapi()
        original = meter.inventory()
        save(out / 'inventory-before.json', original)
        save(out / 'curve-before.json', api.curve(out / 'curve-before.bin'))
        if any(v['offset'] != 0 for v in original['graphics_offsets'].values()) or original['memory_offset']['offset'] != 0:
            raise RuntimeError('Initial offsets must be zero')
        before = json.loads((out / 'before.json').read_text(encoding='utf-8-sig'))
        baseline = json.loads((ROOT / 'results/baseline-2026-10-25.json').read_text(encoding='utf-8-sig'))
        gpu = smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total')
        if gpu != before['gpu'] or {name:metadata.version(name) for name in baseline['packages']} != baseline['packages']:
            raise RuntimeError('GPU or installed libraries changed')
        diagnosis = classify(before)
        save(out / 'performance-state.json', diagnosis)
        if not diagnosis['unlocked_performance_supported']:
            raise RuntimeError('Reference does not establish unlocked performance')
        health_since = before['utc']
        guard()
        watcher = subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),
            '--output-directory',str(out),'--watchdog-parent',str(os.getpid())],creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            if (out / 'watchdog-ready.json').exists():
                break
            if watcher.poll() is not None:
                raise RuntimeError('Watchdog startup failed')
            time.sleep(.1)
        else:
            raise RuntimeError('Watchdog startup timed out')
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Cannot inhibit idle sleep')
        blas = Blas(0)
        if blas.cublas_version.value != baseline['cublas_version']:
            raise RuntimeError('cuBLAS version mismatch')
        expected = {r['mode']:r for r in baseline['results']}
        for mode in ('fp16','bf16'):
            cases.append(Case(blas,mode,expected[mode])); guard()
        worker = threading.Thread(target=monitor,daemon=True); worker.start()
        state['status'] = 'running'
        save(out/'adaptive-summary.json',state)
        with (out / 'energy-blocks.jsonl').open('x',encoding='utf-8') as log:
            run_phase('warmup-0',0,180,log)
            run_phase('reference-0',0,90,log)
            previous = None
            best = 0
            reference = 'reference-0'
            for index,offset in enumerate(offsets,1):
                label,after = f'trial-{offset}',f'reference-{index}'
                run_phase(label,offset,180 if offset==60 else 120,log)
                run_phase(after,0,90,log)
                decision = assess(rows,label,(reference,after),previous)
                decision['offset_mhz'] = offset
                state['decisions'].append(decision)
                save(out / 'adaptive-summary.json',state)
                print('DECISION '+json.dumps(decision),flush=True)
                reference = after
                if not decision['allow_next_step']:
                    break
                best,previous = offset,decision
            state['selected_offset_mhz'] = best
            save(out/'adaptive-summary.json',state)
            if best:
                label = f'validation-{best}'
                run_phase(label,best,600,log)
                run_phase('reference-final',0,120,log)
                final = assess(rows,label,(reference,'reference-final'))
                for mode in ('fp16','bf16'):
                    rates = [r['cuda_tflops'] for r in rows if r['phase']==label and r['mode']==mode]
                    quarter = max(1,len(rates)//4)
                    final['modes'][mode]['last_vs_first_quarter_percent'] = (statistics.median(rates[-quarter:])/statistics.median(rates[:quarter])-1)*100
                final['stable_throughput'] = all(m['last_vs_first_quarter_percent'] >= -3 for m in final['modes'].values())
                state['long_validation'] = final
            state.update(status='passed',completed=True)
    except BaseException as error:
        state.update(status='stopped',error=str(error),traceback=traceback.format_exc())
        print('STOPPED: '+str(error),flush=True)
    finally:
        if meter is not None and original is not None:
            try:
                if armed:
                    restore_original(meter,original['graphics_offsets'])
                ok = restored(meter,original['graphics_offsets']) and meter.offset(0,2)==original['memory_offset']
                if not ok:
                    raise RuntimeError('Original offsets not restored')
                state['original_offsets_restored_verified'] = True
            except Exception as error:
                state.update(status='restoration-failed',completed=False,restoration_error=str(error))
        if watcher is not None and state.get('original_offsets_restored_verified'):
            (out / 'watchdog-done').touch()
            try:
                watcher.wait(timeout=10)
                if watcher.returncode:
                    raise RuntimeError('Watchdog verification failed')
            except Exception as error:
                state.update(status='watchdog-failed',completed=False,watchdog_error=str(error))
        stop.set()
        if 'worker' in locals():
            worker.join(timeout=5)
        for case in cases:
            case.close()
        if blas is not None:
            blas.destroy(blas.handle)
        for operation in [lambda:save(out/'inventory-after.json',meter.inventory()) if meter else None,
            lambda:meter.close() if meter else None,
            lambda:save(out/'curve-after.json',api.curve(out/'curve-after.bin')) if api else None,
            lambda:api.close() if api else None]:
            try:
                operation()
            except Exception as error:
                state.setdefault('cleanup_errors',[]).append(str(error));state.update(status='cleanup-failed',completed=False)
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state.update(finished_utc=utc(),gemm_count=sum(r['iterations'] for r in rows),blocks=len(rows),
            max_temperature_c=max((r['temperature_c'] for r in telemetry),default=None),
            measured_cuda_seconds=sum(r['cuda_ms'] for r in rows)/1000,
            source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),
                Path(__file__).with_name('efficiency.py'),Path(__file__).with_name('nvidia_metrics.py')]})
        save(out/'adaptive-summary.json',state)
    return 0 if state['completed'] else 1


if __name__=='__main__':
    sys.exit(main())
