"""Sustained FP16/BF16/TF32 cuBLAS workload; no device, clock or boot configuration writes.

Alternates persistent 8192-square cases. Every block checks the entire output
against the original baseline SHA256 and 2048 values against CPU FP64.
"""
import argparse
import ctypes as ct
import datetime as dt
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

import numpy as np
from gemm import Blas, smi

ROOT = Path(__file__).resolve().parents[1]


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def known_network_warning(event):
    fields = event.get('fields', {})
    return (event.get('provider') == 'Microsoft-Windows-WHEA-Logger' and event.get('id') == 17
            and all(fields.get(key, '').lower() == value for key, value in {
                'VendorID': '0x1022', 'DeviceID': '0x14ba', 'Bus': '0x0',
                'Device': '0x2', 'Function': '0x1', 'UncorrectableErrorStatus': '0x0'}.items()))


def check_health(events):
    unexpected = [event for event in events if not known_network_warning(event)]
    if unexpected:
        raise RuntimeError('Driver/hardware event during test: ' + json.dumps(unexpected))


def read_health(since):
    process = subprocess.run(['powershell.exe', '-NoProfile', '-File',
        str(ROOT / 'scripts/Read-BenchmarkHealth.ps1'), '-SinceUtc', since],
        capture_output=True, text=True, timeout=20)
    if process.returncode:
        raise RuntimeError('Cannot monitor System event log: ' + process.stderr)
    return json.loads(process.stdout)


class PowerStatus(ct.Structure):
    _fields_ = [('ac', ct.c_ubyte), ('flags', ct.c_ubyte), ('percent', ct.c_ubyte),
                ('system', ct.c_ubyte), ('life', ct.c_uint), ('full', ct.c_uint)]


def ac_power():
    value = PowerStatus()
    if not ct.windll.kernel32.GetSystemPowerStatus(ct.byref(value)):
        raise RuntimeError('Cannot read AC power status')
    return int(value.ac)


def parse_telemetry(result, device):
    if result['returncode']:
        raise RuntimeError('nvidia-smi failed: ' + result['stderr'])
    rows = [row.split(',') for row in result['stdout'].splitlines()]
    found = [row for row in rows if int(row[0].strip()) == device]
    if len(found) != 1:
        raise RuntimeError('GPU telemetry is missing or ambiguous')
    row = [value.strip() for value in found[0]]
    names = ['temperature_c', 'power_w', 'sm_clock_mhz', 'memory_clock_mhz',
             'utilization_percent', 'memory_used_mib']
    values = {name: float(value) for name, value in zip(names, row[1:7])}
    values.update(pstate=row[7], clocks_event_reasons=row[8])
    if not all(np.isfinite(values[name]) for name in names):
        raise RuntimeError('Nonfinite telemetry')
    return values


def check_limits(telemetry, temperature_limit):
    if temperature_limit is not None and telemetry['temperature_c'] >= temperature_limit:
        raise RuntimeError(f'Temperature stop: {telemetry["temperature_c"]} C >= {temperature_limit} C')
    if telemetry['ac_line_status'] != 1:
        raise RuntimeError('AC disconnected or power status unknown; workload stopped')


def cooling_requested(temperature, already_cooling, pause_temperature, resume_temperature):
    return temperature > resume_temperature if already_cooling else temperature >= pause_temperature


class Case:
    def __init__(self, blas, mode, expected):
        self.blas, self.mode, self.expected = blas, mode, expected
        self.n = n = expected['n']
        self.datatype = {'fp16': 2, 'bf16': 14, 'tf32': 0}[mode]
        self.compute = 77 if mode == 'tf32' else 68
        self.tolerance = 0.003 if mode == 'tf32' else 0.0001
        self.pointers, self.events = [], []
        self.alpha, self.beta = ct.c_float(1), ct.c_float(0)
        self.rows = np.linspace(0, n-1, 32, dtype=int)
        self.cols = np.linspace(0, n-1, 64, dtype=int)
        rng = np.random.default_rng(3060)
        arrays, needed, self.input_hashes = [], [], []
        try:
            for index in range(2):
                values = np.asfortranarray(rng.standard_normal((n, n), dtype=np.float32) / np.sqrt(np.float32(n)))
                if mode == 'fp16':
                    storage = np.asfortranarray(values.astype(np.float16))
                    quantized = np.asfortranarray(storage.astype(np.float32))
                elif mode == 'bf16':
                    bits = values.view(np.uint32)
                    rounded = bits + np.uint32(0x7fff) + ((bits >> 16) & 1)
                    storage = np.asfortranarray((rounded >> 16).astype(np.uint16))
                    quantized = np.asfortranarray((storage.astype(np.uint32) << 16).view(np.float32))
                else:
                    storage, quantized = values, values
                self.input_hashes.append(hashlib.sha256(storage.tobytes(order='F')).hexdigest())
                needed.append(quantized[self.rows, :].astype(np.float64) if index == 0 else quantized[:, self.cols].astype(np.float64))
                arrays.append(storage)
                del values, quantized
            if self.input_hashes != expected['input_sha256']:
                raise RuntimeError(mode + ': inputs differ from original baseline')
            self.reference = needed[0] @ needed[1]
            self.reference_norm = np.linalg.norm(self.reference)
            self.output = np.empty((n, n), dtype=np.float32, order='F')
            for host in (*arrays, self.output):
                pointer = ct.c_void_p()
                blas.check(blas.malloc(ct.byref(pointer), host.nbytes), 'cudaMalloc endurance')
                self.pointers.append(pointer)
            for pointer, host in zip(self.pointers, arrays):
                blas.check(blas.copy(pointer, host.ctypes.data, host.nbytes, 1), 'cudaMemcpy endurance H2D')
            for _ in range(2):
                event = ct.c_void_p()
                blas.check(blas.event_create(ct.byref(event)), 'cudaEventCreate endurance')
                self.events.append(event)
        except BaseException:
            self.close()
            raise

    def run(self, iterations):
        blas, n = self.blas, self.n
        blas.check(blas.event_record(self.events[0], None), 'event start endurance')
        for _ in range(iterations):
            blas.check(blas.gemm(blas.handle, 0, 0, n, n, n, ct.byref(self.alpha),
                self.pointers[0], self.datatype, n, self.pointers[1], self.datatype, n,
                ct.byref(self.beta), self.pointers[2], 0, n, self.compute, -1), 'cublasGemmEx endurance')
        blas.check(blas.event_record(self.events[1], None), 'event stop endurance')
        blas.check(blas.event_sync(self.events[1]), 'event synchronize endurance')
        elapsed = ct.c_float()
        blas.check(blas.event_ms(ct.byref(elapsed), *self.events), 'event elapsed endurance')
        if not np.isfinite(elapsed.value) or elapsed.value <= 0:
            raise RuntimeError('Invalid CUDA elapsed time')
        blas.check(blas.copy(self.output.ctypes.data, self.pointers[2], self.output.nbytes, 2), 'cudaMemcpy endurance D2H')
        finite = bool(np.isfinite(self.output).all())
        observed = self.output[np.ix_(self.rows, self.cols)].astype(np.float64)
        relative_l2 = float(np.linalg.norm(observed-self.reference) / self.reference_norm)
        digest = hashlib.sha256(self.output.tobytes(order='F')).hexdigest()
        correct = finite and relative_l2 < self.tolerance and digest == self.expected['output_sha256']
        return dict(mode=self.mode, iterations=iterations, cuda_ms=elapsed.value,
                    ms_per_gemm=elapsed.value/iterations, tflops=2*n**3*iterations/(elapsed.value*1e9),
                    finite_entire_output=finite, sample_relative_l2=relative_l2,
                    sample_count=int(self.reference.size), output_sha256=digest,
                    output_bit_identical_to_baseline=digest == self.expected['output_sha256'],
                    correctness_passed=correct)

    def close(self):
        for event in self.events:
            self.blas.event_destroy(event)
        for pointer in self.pointers:
            self.blas.free(pointer)
        self.events.clear()
        self.pointers.clear()


def summarize(rows, modes=('fp16', 'bf16')):
    result = {}
    for mode in modes:
        samples = [row for row in rows if row['mode'] == mode]
        if not samples:
            continue
        rates = [row['tflops'] for row in samples]
        part = max(1, len(samples)//4)
        first, last = statistics.median(rates[:part]), statistics.median(rates[-part:])
        result[mode] = dict(blocks=len(samples), gemm_count=sum(row['iterations'] for row in samples),
            cuda_seconds=sum(row['cuda_ms'] for row in samples)/1000,
            median_tflops=statistics.median(rates), min_tflops=min(rates), max_tflops=max(rates),
            p5_tflops=float(np.percentile(rates, 5)), p95_tflops=float(np.percentile(rates, 95)),
            first_quarter_median_tflops=first, last_quarter_median_tflops=last,
            last_vs_first_quarter_percent=(last/first-1)*100,
            all_numeric_checks_passed=all(row['correctness_passed'] for row in samples),
            max_sample_relative_l2=max(row['sample_relative_l2'] for row in samples))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=1200, help='Wall seconds under alternating load, excluding setup')
    parser.add_argument('--iterations', type=int, default=100, help='GEMMs per validated block')
    parser.add_argument('--temperature-limit', type=int, default=None, help='Optional application cutoff; disabled unless explicitly supplied')
    parser.add_argument('--thermal-pacing', action='store_true', help='Pause at 79 C, resume at 74 C; report time under actual GPU load separately')
    parser.add_argument('--device', type=int, default=0)
    parser.add_argument('--baseline', type=Path, default=ROOT/'results/baseline-2026-10-25.json')
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--modes', nargs='+', choices=('fp16','bf16','tf32'), default=['fp16','bf16'],
                        help='Persistent modes to alternate; default remains FP16/BF16')
    args = parser.parse_args()
    if len(set(args.modes)) != len(args.modes):
        parser.error('Repeated workload modes are not allowed')
    if not 10 <= args.seconds <= 3600 or not 1 <= args.iterations <= 100 or (args.temperature_limit is not None and not 60 <= args.temperature_limit <= 82):
        parser.error('Duration 10..3600 s, iterations 1..100; optional temperature cutoff 60..82 C')
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT/'results') or out.exists():
        parser.error('Use a new directory under project results')
    out.mkdir(parents=True)
    baseline = json.loads(args.baseline.read_text(encoding='utf-8-sig'))
    expected = {row['mode']: row for row in baseline['results']}
    packages = {name: metadata.version(name) for name in baseline['packages']}
    gpu = smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total')
    environment = {name: os.environ.get(name) for name in baseline['environment']}
    if (packages != baseline['packages'] or gpu != baseline['gpu'] or environment != baseline['environment']
            or baseline['configuration']['n'] != 8192):
        raise RuntimeError('Baseline libraries, environment, matrix size or GPU identity changed')
    state = dict(schema=1, utc=utc(), benchmark='persistent-dense-'+'-'.join(args.modes),
        configuration={**vars(args), 'baseline': str(args.baseline), 'output_directory': str(out)},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(), packages=packages,
        environment=environment, gpu=gpu, n=8192, accumulation='FP32', output='FP32',
        math_mode='DEFAULT | DISALLOW_REDUCED_PRECISION_REDUCTION (16)',
        no_configuration_changes=True, status='initializing', completed=False,
        load_policy='thermal-paced' if args.thermal_pacing else 'continuous',
        pause_temperature_c=79 if args.thermal_pacing else None,
        resume_temperature_c=74 if args.thermal_pacing else None,
        limits=['Fixed GEMM inputs; this is not all-application or sleep/resume validation',
                'Per-block hashes cover final GEMM outputs, not every intermediate multiply',
                'CUDA event timings exclude output validation and telemetry overhead'])
    save(out/'summary.json', state)
    stop, abort = threading.Event(), threading.Event()
    failures, rows, telemetry_rows, health_rows = [], [], [], []
    phase = ['initialization']
    heartbeat = [time.monotonic(), time.monotonic()]
    started = state['utc']

    def fail(error):
        failures.append(str(error))
        abort.set()

    def monitor_gpu():
        with (out/'telemetry.jsonl').open('x', encoding='utf-8') as log:
            while not stop.is_set():
                try:
                    row = parse_telemetry(smi('index,temperature.gpu,power.draw,clocks.sm,clocks.mem,utilization.gpu,memory.used,pstate,clocks_event_reasons.active'), args.device)
                    row.update(utc=utc(), phase=phase[0], ac_line_status=ac_power())
                    telemetry_rows.append(row)
                    log.write(json.dumps(row)+'\n'); log.flush()
                    heartbeat[0] = time.monotonic()
                    check_limits(row, args.temperature_limit)
                except Exception as error:
                    fail(error)
                    return
                stop.wait(1)

    def monitor_health():
        with (out/'health.jsonl').open('x', encoding='utf-8') as log:
            while not stop.is_set():
                try:
                    row = read_health(started)
                    health_rows.append(row)
                    log.write(json.dumps(row)+'\n'); log.flush()
                    heartbeat[1] = time.monotonic()
                    check_health(row['events'])
                except Exception as error:
                    fail(error)
                    return
                stop.wait(25)

    def guard():
        if abort.is_set():
            raise RuntimeError('; '.join(failures))
        if (out/'STOP').exists():
            raise RuntimeError('Stopped by local STOP marker')
        if time.monotonic()-heartbeat[0] > 15 or time.monotonic()-heartbeat[1] > 50:
            raise RuntimeError('Monitoring heartbeat expired')

    threads = [threading.Thread(target=monitor_gpu, daemon=True), threading.Thread(target=monitor_health, daemon=True)]
    blas, cases = None, []
    load_start = None
    cooling_pauses, cooling_seconds = 0, 0.0
    code = 1
    try:
        # Per-thread, reversible idle-sleep inhibition; no persistent power settings.
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Could not inhibit idle sleep for this benchmark thread')
        check_health(read_health(started)['events'])
        for worker in threads:
            worker.start()
        guard()
        blas = Blas(args.device)
        if blas.cublas_version.value != baseline['cublas_version']:
            raise RuntimeError('cuBLAS version changed')
        state['cublas_version'] = blas.cublas_version.value
        for mode in args.modes:
            print('Preparing persistent ' + mode + ' matrices', flush=True)
            cases.append(Case(blas, mode, expected[mode]))
            guard()
        load_start = time.monotonic()
        state.update(status='running', load_started_utc=utc())
        next_progress = 0
        with (out/'blocks.jsonl').open('x', encoding='utf-8') as log:
            while time.monotonic()-load_start < args.seconds:
                for case in cases:
                    guard()
                    if args.thermal_pacing and telemetry_rows and cooling_requested(telemetry_rows[-1]['temperature_c'], False, 79, 74):
                        cooling_pauses += 1
                        cooling_start = time.monotonic()
                        phase[0] = 'cooling'
                        while (time.monotonic()-load_start < args.seconds and
                               cooling_requested(telemetry_rows[-1]['temperature_c'], True, 79, 74)):
                            guard()
                            save(out/'progress.json', dict(status='cooling', elapsed_seconds=time.monotonic()-load_start,
                                target_seconds=args.seconds, blocks=len(rows), cooling_pauses=cooling_pauses,
                                latest_telemetry=telemetry_rows[-1]))
                            stop.wait(0.5)
                        cooling_seconds += time.monotonic()-cooling_start
                    if time.monotonic()-load_start >= args.seconds:
                        break
                    phase[0] = case.mode
                    row = case.run(args.iterations)
                    row.update(utc=utc(), elapsed_seconds=time.monotonic()-load_start)
                    rows.append(row)
                    log.write(json.dumps(row)+'\n'); log.flush()
                    if not row['correctness_passed']:
                        raise RuntimeError('Full output/reference validation failed: ' + case.mode)
                    guard()
                    progress = dict(status='running', elapsed_seconds=row['elapsed_seconds'],
                        target_seconds=args.seconds, blocks=len(rows), last_block=row,
                        latest_telemetry=telemetry_rows[-1] if telemetry_rows else None)
                    save(out/'progress.json', progress)
                    if row['elapsed_seconds'] >= next_progress:
                        print(json.dumps(progress), flush=True)
                        next_progress = row['elapsed_seconds'] + 30
        guard()
        final_health = read_health(started)
        health_rows.append(final_health)
        check_health(final_health['events'])
        # Prevent sleep, idle gaps or validation overhead from being reported as sustained load.
        measured_cuda_seconds = sum(row['cuda_ms'] for row in rows)/1000
        minimum_fraction = 0.25 if args.thermal_pacing else 0.70
        if measured_cuda_seconds < args.seconds*minimum_fraction:
            raise RuntimeError('Insufficient measured GPU load for the requested test duration')
        for mode in args.modes:
            if sum(row['cuda_ms'] for row in rows if row['mode'] == mode)/1000 < args.seconds*((0.20 if args.thermal_pacing else 0.60)/len(args.modes)):
                raise RuntimeError('Insufficient measured GPU time for ' + mode)
        state.update(status='passed', completed=True)
        code = 0
    except BaseException as error:
        state.update(status='stopped', error=str(error), traceback=traceback.format_exc())
        print('STOPPED: ' + str(error), flush=True)
    finally:
        state['load_wall_seconds'] = time.monotonic()-load_start if load_start is not None else 0
        phase[0] = 'cleanup'
        for case in cases:
            case.close()
        if blas is not None:
            blas.destroy(blas.handle)
        stop.set()
        for worker in threads:
            if worker.ident is not None:
                worker.join(timeout=22)
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        if abort.is_set():
            state.update(status='stopped', completed=False, monitor_failures=failures)
            code = 1
        state.update(finished_utc=utc(), results=summarize(rows,args.modes), validated_blocks=len(rows),
            cooling_pauses=cooling_pauses, cooling_seconds=cooling_seconds,
            minimum_cuda_load_fraction=0.25 if args.thermal_pacing else 0.70,
            telemetry_samples=len(telemetry_rows), health_polls=len(health_rows),
            maximum_temperature_c=max((row['temperature_c'] for row in telemetry_rows), default=None))
        state['cuda_seconds'] = sum(row['cuda_ms'] for row in rows)/1000
        state['cuda_load_fraction'] = state['cuda_seconds']/state['load_wall_seconds'] if state['load_wall_seconds'] else 0
        state['hardware_events'] = health_rows[-1]['events'] if health_rows else None
        save(out/'summary.json', state)
        save(out/'progress.json', {key: state[key] for key in ('status', 'completed', 'load_wall_seconds', 'validated_blocks', 'maximum_temperature_c')})
        print(json.dumps({key: state[key] for key in ('status', 'completed', 'load_wall_seconds', 'cuda_seconds', 'validated_blocks', 'maximum_temperature_c', 'results')}, indent=2), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
