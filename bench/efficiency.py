"""Meter FP16/BF16 work per joule; optional bounded, temporary graphics-offset trial.

Default is read-only. --trial requires elevation and changes only the graphics
V/F offset to bounded values, restoring zero. The standard screen uses +30/+60;
the separately authorized adaptive screens can also use +90/+120/+150 MHz. No voltage, power, memory, boot or
firmware setters are used. An independent process also restores on failure.
"""
import argparse
import ctypes as ct
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import traceback

import numpy as np
from endurance import Case, ROOT, ac_power, check_health, read_health, save, utc
from gemm import Blas, smi
from nvidia_metrics import Nvml, Nvapi, ClockOffset
from performance_state import classify


def energy_metrics(start_mj, end_mj, seconds, cuda_ms, n, iterations):
    if end_mj <= start_mj or seconds <= 0 or cuda_ms <= 0 or cuda_ms / 1000 > seconds * 1.02:
        raise ValueError('Invalid or reset energy counter/timing')
    joules = (end_mj - start_mj) / 1000
    work = 2 * n**3 * iterations / 1e12
    return dict(energy_j=joules, work_tflop=work, meter_wall_seconds=seconds,
                average_power_w=joules / seconds, cuda_tflops=work / (cuda_ms / 1000),
                tflop_per_joule=work / joules)


def measured_block(case, meter, iterations):
    b, n = case.blas, case.n
    b.check(b.sync(), 'pre-meter synchronize')
    start = time.perf_counter()
    start_energy = meter.energy()
    b.check(b.event_record(case.events[0], None), 'efficiency event start')
    for _ in range(iterations):
        b.check(b.gemm(b.handle, 0, 0, n, n, n, ct.byref(case.alpha),
            case.pointers[0], case.datatype, n, case.pointers[1], case.datatype, n,
            ct.byref(case.beta), case.pointers[2], 0, n, 68, -1), 'efficiency GEMM')
    b.check(b.event_record(case.events[1], None), 'efficiency event stop')
    b.check(b.event_sync(case.events[1]), 'efficiency synchronize')
    end_energy = meter.energy()
    end = time.perf_counter()
    elapsed = ct.c_float()
    b.check(b.event_ms(ct.byref(elapsed), *case.events), 'efficiency CUDA elapsed')
    metrics = energy_metrics(start_energy, end_energy, end - start, elapsed.value, n, iterations)
    # Copy/check only after the energy window, without overwriting the measured output.
    b.check(b.copy(case.output.ctypes.data, case.pointers[2], case.output.nbytes, 2), 'efficiency output copy')
    finite = bool(np.isfinite(case.output).all())
    observed = case.output[np.ix_(case.rows, case.cols)].astype(np.float64)
    relative = float(np.linalg.norm(observed - case.reference) / case.reference_norm)
    digest = hashlib.sha256(case.output.tobytes(order='F')).hexdigest()
    passed = finite and relative < 0.0001 and digest == case.expected['output_sha256']
    return dict(mode=case.mode, iterations=iterations, cuda_ms=elapsed.value,
        start_monotonic=start, end_monotonic=end, energy_start_mj=start_energy, energy_end_mj=end_energy,
        sample_relative_l2=relative, finite_entire_output=finite, output_sha256=digest,
        output_bit_identical_to_baseline=digest == case.expected['output_sha256'],
        correctness_passed=passed, **metrics)


def set_trial_offset(meter, offset):
    if offset not in (0, 30, 60, 90, 120, 150):
        raise ValueError('Only 0/+30/+60/+90/+120/+150 MHz allowed')
    value = ClockOffset(ct.sizeof(ClockOffset) | (1 << 24), 0, 0, offset, 0, 0)
    rc = meter.bind('nvmlDeviceSetClockOffsets', [ct.c_void_p, ct.POINTER(ClockOffset)])(
        meter.device, ct.byref(value))
    meter.check(rc, 'temporary graphics offset')
    if meter.offset()['offset'] != offset or meter.offset(2)['offset'] != offset:
        raise RuntimeError('Graphics offset readback mismatch')


def restored(meter, original):
    return meter.offsets() == original


def restore_original(meter, original):
    if not restored(meter, original):
        set_trial_offset(meter, 0)
    if not restored(meter, original):
        raise RuntimeError('Restoration readback failed')


def watchdog(out, parent_id, timeout_seconds=900):
    if not 900 <= timeout_seconds <= 3600:
        raise ValueError('Watchdog deadline must be 900..3600 seconds')
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ct.c_uint, ct.c_int, ct.c_uint]
    kernel.OpenProcess.restype = ct.c_void_p
    kernel.WaitForSingleObject.argtypes = [ct.c_void_p, ct.c_uint]
    kernel.WaitForSingleObject.restype = ct.c_uint
    kernel.CloseHandle.argtypes = [ct.c_void_p]
    parent = kernel.OpenProcess(0x00100000, 0, parent_id)
    if not parent:
        raise RuntimeError('Watchdog could not open parent process')
    meter = Nvml()
    original = json.loads((out / 'inventory-before.json').read_text())['graphics_offsets']
    try:
        save(out / 'watchdog-ready.json', dict(utc=utc(), pid=os.getpid()))
        deadline = time.monotonic() + timeout_seconds
        while True:
            parent_exited = kernel.WaitForSingleObject(parent, 1000) == 0
            age = time.time() - (out / 'heartbeat').stat().st_mtime
            if (out / 'watchdog-done').exists():
                if not restored(meter, original):
                    raise RuntimeError('Parent claimed restoration but readback differs')
                save(out / 'watchdog-result.json', dict(utc=utc(), verified=True, restore_needed=False))
                return
            if parent_exited or age > 50 or time.monotonic() >= deadline:
                restore_original(meter, original)
                ok = restored(meter, original)
                save(out / 'watchdog-result.json', dict(utc=utc(), verified=ok, restore_needed=True,
                    parent_exited=parent_exited, heartbeat_age=age))
                if not ok:
                    raise RuntimeError('Watchdog restoration readback failed')
                return
    finally:
        meter.close()
        kernel.CloseHandle(parent)


def aggregate(rows):
    result = []
    for phase in dict.fromkeys(row['phase'] for row in rows):
        for mode in ('fp16', 'bf16'):
            subset = [r for r in rows if r['phase'] == phase and r['mode'] == mode]
            if not subset:
                continue
            energy = sum(r['energy_j'] for r in subset)
            seconds = sum(r['meter_wall_seconds'] for r in subset)
            work = sum(r['work_tflop'] for r in subset)
            result.append(dict(phase=phase, mode=mode, offset_mhz=subset[0]['offset_mhz'], blocks=len(subset),
                gemm_count=sum(r['iterations'] for r in subset), energy_j=energy,
                average_power_w=energy / seconds, cuda_tflops=work / (sum(r['cuda_ms'] for r in subset) / 1000),
                tflop_per_joule=work / energy,
                median_sm_clock_mhz=statistics.median(r['median_sm_clock_mhz'] for r in subset),
                median_voltage_mv=statistics.median(r['median_voltage_mv'] for r in subset if r['median_voltage_mv'] is not None)
                    if any(r['median_voltage_mv'] is not None for r in subset) else None,
                max_temperature_c=max(r['max_temperature_c'] for r in subset),
                correct=all(r['correctness_passed'] for r in subset)))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-directory', type=Path, required=True)
    p.add_argument('--reference', type=Path)
    p.add_argument('--trial', action='store_true')
    p.add_argument('--inventory-only', action='store_true')
    p.add_argument('--watchdog-parent', type=int)
    p.add_argument('--iterations', type=int, default=400)
    p.add_argument('--blocks', type=int, default=2)
    args = p.parse_args()
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT / 'results') or not out.is_dir():
        p.error('Use an existing results directory containing a fresh reference benchmark')
    if args.watchdog_parent is not None:
        watchdog(out, args.watchdog_parent)
        return 0
    if (out / 'energy-blocks.jsonl').exists() or (out / 'measurement-lock').exists():
        p.error('This directory already contains a measurement; use a fresh results directory')
    if not 100 <= args.iterations <= 500 or not 1 <= args.blocks <= 4:
        p.error('Iterations 100..500; blocks 1..4')
    reference_path = args.reference or out / 'before.json'
    if not args.inventory_only:
        (out / 'measurement-lock').open('x').close()
    meter, api, blas = None, None, None
    cases, rows, telemetry, failures = [], [], [], []
    stop = threading.Event()
    phase = ['initialization']
    trial_armed = False
    original = None
    watcher = None
    started = utc()
    state = dict(utc=started, status='initializing', completed=False, trial_requested=args.trial,
        no_voltage_power_memory_boot_changes=True, temporary_graphics_offsets_mhz=[30, 60] if args.trial else [],
        baseline=str(reference_path), gpu=smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total'),
        energy_method='NVML total-energy counter delta brackets the measured CUDA workload; CPU output validation excluded',
        limitations=['GPU counter includes other GPU work in the same interval; not wall-socket or whole-laptop energy',
                     'V/F export uses a private read-only API; captured first 80 entries, not guaranteed complete',
                     'Short trials do not certify all applications or long-term tuning stability'])
    save(out / 'efficiency-summary.json', state)

    def guard():
        (out / 'heartbeat').touch()
        if failures:
            raise RuntimeError('; '.join(failures))
        if watcher is not None and watcher.poll() is not None:
            raise RuntimeError('Restoration watchdog exited during trial')
        if (out / 'STOP').exists():
            raise RuntimeError('Stopped by local STOP marker')
        if ac_power() != 1:
            raise RuntimeError('AC disconnected')

    def monitor():
        try:
            with (out / 'energy-telemetry.jsonl').open('x', encoding='utf-8') as log:
                while not stop.is_set():
                    sample = meter.sample()
                    sample.update(monotonic=time.perf_counter(), utc=utc(), phase=phase[0], voltage_mv=api.voltage())
                    telemetry.append(sample)
                    log.write(json.dumps(sample) + '\n'); log.flush()
                    if ac_power() != 1:
                        raise RuntimeError('AC disconnected')
                    stop.wait(0.2)
        except Exception as error:
            failures.append(str(error))

    try:
        meter, api = Nvml(), Nvapi()
        original = meter.inventory()
        save(out / 'inventory-before.json', original)
        save(out / 'curve-before.json', api.curve(out / 'curve-before.bin'))
        if args.inventory_only:
            state.update(status='inventory-saved', completed=True)
            return 0
        if (out / 'energy-blocks.jsonl').exists():
            raise RuntimeError('Measured blocks already exist; use a fresh output directory')
        before = json.loads(reference_path.read_text(encoding='utf-8-sig'))
        baseline = json.loads((ROOT / 'results/baseline-2026-10-25.json').read_text(encoding='utf-8-sig'))
        reference_age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(before['utc'])).total_seconds()
        if not 0 <= reference_age <= 600:
            raise RuntimeError('Generate a fresh four-mode reference immediately before the test (maximum age 10 minutes)')
        if before['gpu'] != state['gpu'] or before['packages'] != baseline['packages']:
            raise RuntimeError('Reference GPU/libraries changed')
        diagnosis = classify(before)
        save(out / 'performance-state.json', diagnosis)
        if not diagnosis['unlocked_performance_supported']:
            raise RuntimeError('Reference does not establish unlocked performance')
        guard()
        health = read_health(before['utc'])
        save(out / 'health-before.json', health)
        check_health(health['events'])
        if args.trial:
            if not ct.windll.shell32.IsUserAnAdmin():
                raise RuntimeError('Temporary tuning requires elevation; inventory was saved')
            if any(x['offset'] != 0 for x in original['graphics_offsets'].values()) or original['memory_offset']['offset'] != 0:
                raise RuntimeError('Existing offsets are nonzero; automatic trial refused')
            if any((out / name).exists() for name in ('watchdog-ready.json', 'watchdog-done', 'watchdog-result.json')):
                raise RuntimeError('Old watchdog state exists; use a fresh results directory')
            watcher = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                '--output-directory', str(out), '--watchdog-parent', str(os.getpid())],
                creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(100):
                if (out / 'watchdog-ready.json').exists():
                    break
                if watcher.poll() is not None:
                    raise RuntimeError('Restoration watchdog exited')
                time.sleep(0.1)
            else:
                raise RuntimeError('Restoration watchdog not ready')
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Cannot inhibit idle sleep for test thread')
        blas = Blas(0)
        if blas.cublas_version.value != baseline['cublas_version']:
            raise RuntimeError('cuBLAS version changed')
        expected = {r['mode']: r for r in baseline['results']}
        for mode in ('fp16', 'bf16'):
            print('Preparing ' + mode, flush=True)
            cases.append(Case(blas, mode, expected[mode]))
            guard()
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        sequence = [('reference-0', 0), ('trial-30', 30), ('reference-1', 0),
                    ('trial-60', 60), ('reference-2', 0)] if args.trial else [('reference-0', 0)]
        state.update(status='running', sequence=sequence)
        save(out / 'efficiency-summary.json', state)
        with (out / 'energy-blocks.jsonl').open('x', encoding='utf-8') as log:
            for label, offset in sequence:
                guard()
                if args.trial:
                    trial_armed = True
                    set_trial_offset(meter, offset)
                phase[0] = label + '-warmup'
                for case in cases:
                    warmup = case.run(100)
                    if not warmup['correctness_passed']:
                        raise RuntimeError('Warmup output validation failed')
                    guard()
                phase[0] = label
                for _ in range(args.blocks):
                    for case in cases:
                        guard()
                        row = measured_block(case, meter, args.iterations)
                        selected = [s for s in telemetry if row['start_monotonic'] <= s['monotonic'] <= row['end_monotonic']]
                        active = [s for s in selected if s['utilization_percent'] >= 90]
                        if len(active) < 5:
                            raise RuntimeError('Insufficient active telemetry in energy window')
                        voltage = [s['voltage_mv'] for s in active if s['voltage_mv'] is not None]
                        row.update(phase=label, offset_mhz=offset, utc=utc(), samples=len(selected), active_samples=len(active),
                            median_sm_clock_mhz=statistics.median(s['sm_clock_mhz'] for s in active),
                            median_voltage_mv=statistics.median(voltage) if voltage else None,
                            max_temperature_c=max(s['temperature_c'] for s in selected),
                            median_enforced_limit_w=statistics.median(s['enforced_limit_w'] for s in active),
                            median_reported_power_w=statistics.median(s['power_w'] for s in active))
                        row['counter_vs_sample_power_percent'] = (row['average_power_w'] / row['median_reported_power_w'] - 1) * 100
                        if not row['correctness_passed'] or abs(row['counter_vs_sample_power_percent']) > 10:
                            raise RuntimeError('Output or energy-counter sanity validation failed: ' + json.dumps(row))
                        rows.append(row)
                        log.write(json.dumps(row) + '\n'); log.flush()
                        print(f"{label} {case.mode}: {row['cuda_tflops']:.3f} TFLOPS, {row['average_power_w']:.2f} W, {row['tflop_per_joule']:.4f} TFLOP/J", flush=True)
                        guard()
                health = read_health(before['utc'])
                save(out / 'health-after.json', health)
                check_health(health['events'])
        state.update(status='passed', completed=True)
    except BaseException as error:
        state.update(status='stopped', error=str(error), traceback=traceback.format_exc())
        print(str(error), flush=True)
    finally:
        if trial_armed:
            try:
                restore_original(meter, original['graphics_offsets'])
                if meter.offset(0, 2) != original['memory_offset']:
                    raise RuntimeError('Final offset restoration differs from original')
                state['offsets_restored_verified'] = True
            except Exception as error:
                state.update(status='restoration-failed', completed=False, restoration_error=str(error))
        elif args.trial:
            state['offsets_restored_verified'] = original is not None and restored(meter, original['graphics_offsets'])
        if watcher is not None and state.get('offsets_restored_verified'):
            (out / 'watchdog-done').touch()
            try:
                watcher.wait(timeout=10)
                state['watchdog_exit'] = watcher.returncode
                if watcher.returncode != 0:
                    state.update(status='watchdog-failed', completed=False)
            except subprocess.TimeoutExpired:
                state.update(status='watchdog-pending', completed=False)
        stop.set()
        if 'thread' in locals():
            thread.join(timeout=5)
        for case in cases:
            case.close()
        if blas is not None:
            blas.destroy(blas.handle)
        for operation in [
            lambda: save(out / 'inventory-after.json', meter.inventory()) if meter is not None else None,
            lambda: meter.close() if meter is not None else None,
            lambda: save(out / 'curve-after.json', api.curve(out / 'curve-after.bin')) if api is not None else None,
            lambda: api.close() if api is not None else None,
        ]:
            try:
                operation()
            except Exception as error:
                state.setdefault('cleanup_errors', []).append(str(error))
                state.update(status='cleanup-failed', completed=False)
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state.update(finished_utc=utc(), results=aggregate(rows), source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), Path(__file__).with_name('nvidia_metrics.py')]})
        save(out / 'efficiency-summary.json', state)
    return 0 if state['completed'] else 1


if __name__ == '__main__':
    sys.exit(main())
