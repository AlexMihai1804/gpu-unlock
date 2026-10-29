"""Compare 0/+150/+150/0 MHz with all four precision modes; restore zero.

Reuses the existing bounded setter and independent restoration watchdog.
No voltage, power, memory, firmware, boot or persistent profile setters.
"""
import argparse
import ctypes as ct
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import traceback

from efficiency import restore_original, restored, set_trial_offset, watchdog
from endurance import ROOT, ac_power, check_health, read_health, save, utc
from gemm import Blas, smi
from nvidia_metrics import Nvml
from performance_state import classify

MODES = ('fp16', 'bf16', 'tf32', 'fp32')
OFFSETS = (0, 150, 150, 0)


def summarize(rounds):
    if [r['offset_mhz'] for r in rounds] != list(OFFSETS):
        raise ValueError('Four complete ABBA rounds required')
    output = {}
    for mode in MODES:
        modes = {}
        for offset in (0, 150):
            rows = [next(r for r in item['results'] if r['mode'] == mode)
                    for item in rounds if item['offset_mhz'] == offset]
            if not all(r['correctness_passed'] and r['output_bit_identical_to_baseline']
                       and r['inputs_identical_to_baseline'] for r in rows):
                raise ValueError('Numerical/input identity failure')
            samples = [x for r in rows for x in r['sample_ms']]
            if len(samples) != 14 or any(x <= 0 for x in samples):
                raise ValueError('Missing or invalid CUDA samples')
            median_ms = statistics.median(samples)
            modes[str(offset)] = dict(tflops=2 * 8192**3 / (median_ms * 1e9),
                median_ms=median_ms, sample_ms=samples,
                round_tflops=[r['tflops'] for r in rows],
                maximum_temperature_c=max(r['telemetry_summary']['maximum_temperature_c'] for r in rows),
                active_power_w_by_round=[r['telemetry_summary']['median_power_w'] for r in rows],
                active_sm_mhz_by_round=[r['telemetry_summary']['median_sm_mhz'] for r in rows])
        output[mode] = dict(offsets=modes,
            gain_percent=(modes['150']['tflops'] / modes['0']['tflops'] - 1) * 100,
            zero_last_vs_first_percent=(modes['0']['round_tflops'][1] / modes['0']['round_tflops'][0] - 1) * 100)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-directory', type=Path, required=True)
    p.add_argument('--watchdog-parent', type=int)
    args = p.parse_args()
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT / 'results') or not out.is_dir():
        p.error('Existing project results directory required')
    if args.watchdog_parent is not None:
        watchdog(out, args.watchdog_parent, 1800)
        return 0
    if not ct.windll.shell32.IsUserAnAdmin():
        p.error('UAC elevation required for the temporary offset')
    if (out / 'comparison-summary.json').exists():
        p.error('Use a fresh output directory')
    state = dict(utc=utc(), status='initializing', completed=False,
        stock_definition='0 MHz graphics offset, existing SS0+SS1 unlock retained',
        offset_plan_mhz=list(OFFSETS), configuration=dict(n=8192, warmup_seconds=6,
        samples=7, iterations=30, modes=list(MODES)), rounds=[],
        persistent_tuning_applied=False, no_voltage_power_memory_boot_writes=True,
        temperature_stop=None, limits=[
            'Same-boot fixed-input dense GEMM comparison; not all-application stability certification',
            'Telemetry includes warmup and validation; power is not event-aligned energy per GEMM',
            'Entire final output checked per mode/round, not every intermediate result'])
    save(out / 'comparison-summary.json', state)
    meter = blas = watcher = None
    original = None
    stop = threading.Event()
    phase = ['initialization', 0]
    samples, failures = [], []
    worker = None
    armed = False
    last_health = [0.0]

    def health():
        result = read_health(state['utc'])
        save(out / 'health-after.json', result)
        check_health(result['events'])
        last_health[0] = time.monotonic()

    def guard():
        (out / 'heartbeat').touch()
        if failures:
            raise RuntimeError('; '.join(failures))
        if watcher is not None and watcher.poll() is not None:
            raise RuntimeError('Restoration watchdog exited')
        if (out / 'STOP').exists() or ac_power() != 1:
            raise RuntimeError('STOP marker or AC disconnected')
        if time.monotonic() - last_health[0] > 25:
            health()

    def monitor():
        try:
            with (out / 'telemetry.jsonl').open('x', encoding='utf-8') as log:
                while not stop.is_set():
                    label, offset = phase[:]
                    sample = meter.sample()
                    sample.update(utc=utc(), phase=label, offset_mhz=offset)
                    samples.append(sample)
                    log.write(json.dumps(sample) + '\n'); log.flush()
                    (out / 'heartbeat').touch()
                    if ac_power() != 1:
                        raise RuntimeError('AC disconnected')
                    stop.wait(.2)
        except BaseException as error:
            failures.append(str(error))

    try:
        meter = Nvml()
        original = meter.inventory()
        save(out / 'inventory-before.json', original)
        if any(v['offset'] != 0 for v in original['graphics_offsets'].values()) or original['memory_offset']['offset'] != 0:
            raise RuntimeError('Initial graphics and memory offsets must be zero')
        before = json.loads((out / 'before.json').read_text(encoding='utf-8-sig'))
        baseline = json.loads((ROOT / 'results/baseline-2026-10-25.json').read_text())
        if smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total') != before['gpu']:
            raise RuntimeError('GPU identity changed')
        if {key: metadata.version(key) for key in before['packages']} != before['packages'] or before['packages'] != baseline['packages']:
            raise RuntimeError('CUDA/NumPy packages changed')
        diagnosis = classify(before)
        save(out / 'performance-state-before.json', diagnosis)
        if not diagnosis['unlocked_performance_supported'] or not diagnosis['tf32_unlocked_performance_supported']:
            raise RuntimeError('Fresh control does not confirm full FP16/BF16/TF32 unlock')
        guard()
        watcher = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
            '--output-directory', str(out), '--watchdog-parent', str(os.getpid())],
            creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            if (out / 'watchdog-ready.json').exists():
                break
            if watcher.poll() is not None:
                raise RuntimeError('Watchdog initialization failed')
            time.sleep(.1)
        else:
            raise RuntimeError('Watchdog initialization timeout')
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Cannot inhibit idle sleep')
        blas = Blas(0)
        if blas.cublas_version.value != before['cublas_version']:
            raise RuntimeError('cuBLAS version changed')
        worker = threading.Thread(target=monitor, daemon=True)
        worker.start()
        expected = {r['mode']: r for r in baseline['results']}
        state['status'] = 'running'
        for index, offset in enumerate(OFFSETS):
            guard()
            armed = True
            set_trial_offset(meter, offset)
            if meter.offset(0, 2) != original['memory_offset']:
                raise RuntimeError('Memory offset changed')
            event = dict(utc=utc(), round=index, requested_mhz=offset,
                p0=meter.offset(0), p2=meter.offset(2), memory=meter.offset(0, 2))
            with (out / 'offset-events.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(event) + '\n')
            entry = dict(round=index, offset_mhz=offset, utc=utc(), results=[])
            for mode in MODES:
                guard()
                phase[:] = [f'round-{index}-{mode}', offset]
                print(f'ROUND {index+1}/4 offset={offset:+d} {mode}', flush=True)
                row = blas.run(mode, 8192, 6, 7, 30)
                guard()
                row['output_bit_identical_to_baseline'] = row['output_sha256'] == expected[mode]['output_sha256']
                row['inputs_identical_to_baseline'] = row['input_sha256'] == expected[mode]['input_sha256']
                active = [s for s in samples if s['phase'] == phase[0] and s['utilization_percent'] >= 90]
                if len(active) < 5:
                    raise RuntimeError('Insufficient active telemetry')
                row['telemetry_summary'] = dict(active_samples=len(active),
                    maximum_temperature_c=max(s['temperature_c'] for s in active),
                    median_power_w=statistics.median(s['power_w'] for s in active),
                    median_sm_mhz=statistics.median(s['sm_clock_mhz'] for s in active))
                entry['results'].append(row)
                save(out / f'round-{index}.json', entry)
                if not row['correctness_passed'] or not row['output_bit_identical_to_baseline'] or not row['inputs_identical_to_baseline']:
                    raise RuntimeError('Numerical/input identity failed')
                save(out / 'progress.json', dict(utc=utc(), round=index+1, offset_mhz=offset,
                    mode=mode, tflops=row['tflops'], telemetry=row['telemetry_summary']))
                print(f"{mode}: {row['tflops']:.3f} TFLOPS, full output identical", flush=True)
            state['rounds'].append(entry)
            save(out / 'comparison-summary.json', state)
        state['comparison'] = summarize(state['rounds'])
        health()
        state.update(status='passed', completed=True)
    except BaseException as error:
        state.update(status='stopped', completed=False, error=str(error), traceback=traceback.format_exc())
        print('STOPPED: ' + str(error), flush=True)
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=5)
        if meter is not None and original is not None:
            try:
                if armed:
                    restore_original(meter, original['graphics_offsets'])
                if not restored(meter, original['graphics_offsets']) or meter.offset(0, 2) != original['memory_offset']:
                    raise RuntimeError('Offset restoration readback failed')
                state['original_offsets_restored_verified'] = True
                save(out / 'inventory-after.json', meter.inventory())
            except BaseException as error:
                state.update(status='restoration-failed', completed=False, restoration_error=str(error))
        if watcher is not None and state.get('original_offsets_restored_verified'):
            (out / 'watchdog-done').touch()
            try:
                watcher.wait(timeout=10)
                result = json.loads((out / 'watchdog-result.json').read_text())
                if watcher.returncode or not result['verified']:
                    raise RuntimeError('Watchdog verification failed')
            except BaseException as error:
                state.update(status='watchdog-failed', completed=False, watchdog_error=str(error))
        if blas is not None:
            blas.destroy(blas.handle)
        if meter is not None:
            meter.close()
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state.update(finished_utc=utc(), maximum_temperature_c=max((s['temperature_c'] for s in samples), default=None),
            source_sha256={name:hashlib.sha256((ROOT / 'bench' / name).read_bytes()).hexdigest()
                for name in ('compare_offset150.py','gemm.py','efficiency.py','nvidia_metrics.py','performance_state.py')})
        save(out / 'comparison-summary.json', state)
    return 0 if state['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
